"""The ReAct loop: Thought -> Action -> Observation, repeated until done.

Key insight: an "agent" is just a while-loop around an LLM. The model picks
a tool, the runtime executes it, and the result is appended to the message
list so the next call can see it. The stop condition (a plain-text answer)
and a max-turn budget are what keep the loop from running forever.
"""

import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ast
import operator

from mock_llm import MockLLM, Tool

# --- Tool 1: calculator via safe AST evaluation (never eval() raw strings) ---
_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.Pow: operator.pow, ast.USub: operator.neg,
        ast.Mod: operator.mod}


def safe_eval(expression: str):
    """Evaluate arithmetic only: numbers, + - * / % ** and unary minus."""
    def walk(node):
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](walk(node.left), walk(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](walk(node.operand))
        raise ValueError("Disallowed expression element: %s" % type(node).__name__)
    return walk(ast.parse(expression, mode="eval"))


# --- Tool 2: knowledge-base lookup over a small dict ---
KB = {
    "mars_base_alpha_crew": "26 crew members",
    "mars_base_alpha_modules": "4 habitat modules",
    "acme_ceo": "Dana Reyes",
    "acme_founded": "2011",
}


def kb_lookup(key: str) -> str:
    return KB.get(key, "NOT FOUND: no entry for %r" % key)


def make_tools():
    return [
        Tool("calculator", "Evaluate an arithmetic expression.",
             {"properties": {"expression": {"type": "string"}},
              "required": ["expression"]},
             lambda expression: safe_eval(expression)),
        Tool("kb_lookup", "Look up a fact by key in the knowledge base.",
             {"properties": {"key": {"type": "string"}},
              "required": ["key"]},
             lambda key: kb_lookup(key)),
    ]


class ReActAgent:
    def __init__(self, llm: MockLLM, tools, max_turns: int = 6):
        self.llm = llm
        self.tools = {t.name: t for t in tools}
        self.max_turns = max_turns

    def run(self, task: str, verbose: bool = True):
        messages = [{"role": "user", "content": task}]
        specs = [t.spec() for t in self.tools.values()]
        for turn in range(1, self.max_turns + 1):
            resp = self.llm.complete(messages, tools=specs)
            if verbose:
                print("--- Turn %d ---" % turn)
                if resp.get("thought"):
                    print("Thought:     %s" % resp["thought"])
            if resp["type"] == "text":  # stop condition: model answered in prose
                if verbose:
                    print("Final:       %s" % resp["content"])
                return resp["content"]
            name, args = resp["name"], resp.get("arguments", {})
            if verbose:
                print("Action:      %s(%s)" % (name, args))
            try:
                observation = str(self.tools[name].fn(**args))
            except Exception as exc:  # errors go back to the model, not the user
                observation = "ERROR: %s" % exc
            if verbose:
                print("Observation: %s" % observation)
            messages.append({"role": "assistant", "content": "call %s(%s)" % (name, args)})
            messages.append({"role": "tool", "content": "%s -> %s" % (name, observation)})
        if verbose:
            print("Budget of %d turns exhausted; stopping." % self.max_turns)
        return None


if __name__ == "__main__":
    task = ("How many crew live on Mars Base Alpha, and what is that number "
            "multiplied by the number of habitat modules?")
    print("=== ReAct agent demo ===")
    print("Task: %s\n" % task)

    # Scripted model: two tool calls, then a grounded final answer.
    llm = MockLLM(script=[
        {"type": "tool_call", "thought": "I need the crew count from the KB.",
         "name": "kb_lookup", "arguments": {"key": "mars_base_alpha_crew"}},
        {"type": "tool_call", "thought": "Now the module count.",
         "name": "kb_lookup", "arguments": {"key": "mars_base_alpha_modules"}},
        {"type": "tool_call", "thought": "26 crew x 4 modules -> multiply.",
         "name": "calculator", "arguments": {"expression": "26 * 4"}},
        {"type": "text", "thought": "I have every fact I need; answer directly.",
         "content": "Mars Base Alpha houses 26 crew across 4 modules; 26 x 4 = 104."},
    ])
    agent = ReActAgent(llm, make_tools(), max_turns=6)
    answer = agent.run(task)
    print("\nAnswer returned to caller: %s" % answer)
    print("\nNote how each Observation lands in the message list, so the next")
    print("model call reasons over everything gathered so far. That feedback")
    print("wire IS the agent.")
