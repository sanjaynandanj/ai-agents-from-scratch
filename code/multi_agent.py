"""Orchestrator-worker multi-agent pattern, plus an explicit handoff.

Key insight: multi-agent systems are function composition with LLMs at the
nodes. An orchestrator decomposes the task and routes subtasks to workers
that each carry their own model, tools, and context; a handoff is just a
worker returning "route this to X" instead of an answer.
"""

import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mock_llm import MockLLM, Tool
from agent_loop import ReActAgent, safe_eval

MARKET_KB = {
    "ev_sales_2024": "1.2 million EVs sold (region: North America, 2024)",
    "ev_sales_2023": "0.9 million EVs sold (region: North America, 2023)",
}


class Worker:
    """A specialist: its own LLM script, its own tools, its own context."""

    def __init__(self, name, llm, tools):
        self.name = name
        self.agent = ReActAgent(llm, tools, max_turns=4)

    def run(self, subtask):
        print("  [%s] received: %s" % (self.name, subtask))
        result = self.agent.run(subtask, verbose=False)
        print("  [%s] returned: %s" % (self.name, result))
        return result


class Orchestrator:
    def __init__(self, llm, workers):
        self.llm = llm
        self.workers = {w.name: w for w in workers}

    def run(self, task):
        print("[orchestrator] task: %s\n" % task)
        plan = self.llm.complete([{"role": "user", "content": task}])["content"]
        print("[orchestrator] decomposition:\n%s\n" % plan)
        results = {}
        # Each plan line: "worker_name :: subtask"
        queue = [tuple(s.strip() for s in line.split("::", 1))
                 for line in plan.splitlines() if "::" in line]
        while queue:
            worker_name, subtask = queue.pop(0)
            result = self.workers[worker_name].run(subtask)
            # Handoff: a worker may punt to a peer instead of answering.
            if result and result.startswith("HANDOFF"):
                _, target, forwarded = result.split("::", 2)
                print("  [%s] hands off to %s: %s\n"
                      % (worker_name, target.strip(), forwarded.strip()))
                queue.insert(0, (target.strip(), forwarded.strip()))
                continue
            results[worker_name + ": " + subtask] = result
            print()
        synthesis = self.llm.complete([
            {"role": "user", "content": task},
            {"role": "tool", "content": "worker results: %s" % results}])
        print("[orchestrator] synthesis: %s" % synthesis["content"])
        return synthesis["content"]


if __name__ == "__main__":
    researcher = Worker("researcher", MockLLM(script=[
        {"type": "tool_call", "name": "kb_lookup",
         "arguments": {"key": "ev_sales_2024"}},
        "1.2 million EVs were sold in North America in 2024.",
        {"type": "tool_call", "name": "kb_lookup",
         "arguments": {"key": "ev_sales_2023"}},
        # The researcher can fetch numbers but not do math: it hands off.
        "HANDOFF :: analyst :: compute percent growth from 0.9 to 1.2 million",
    ]), [Tool("kb_lookup", "look up market facts",
              {"properties": {"key": {"type": "string"}}, "required": ["key"]},
              lambda key: MARKET_KB.get(key, "NOT FOUND"))])

    analyst = Worker("analyst", MockLLM(script=[
        {"type": "tool_call", "name": "calculator",
         "arguments": {"expression": "(1.2 - 0.9) / 0.9 * 100"}},
        "EV sales grew about 33.3 percent year over year.",
    ]), [Tool("calculator", "arithmetic",
              {"properties": {"expression": {"type": "string"}},
               "required": ["expression"]},
              lambda expression: round(safe_eval(expression), 1))])

    orchestrator = Orchestrator(MockLLM(script=[
        "researcher :: find 2024 EV sales for North America\n"
        "researcher :: find 2023 EV sales and derive year-over-year growth",
        "North American EV sales hit 1.2M in 2024, up from 0.9M in 2023 -- "
        "roughly 33.3 percent growth. Sourced by the researcher, computed by "
        "the analyst.",
    ]), [researcher, analyst])

    print("=== Orchestrator-worker demo ===\n")
    orchestrator.run("Summarize the North American EV market's growth.")
    print("\nNotice the handoff: the researcher recognized a subtask outside")
    print("its skill set and routed it to the analyst -- no central logic")
    print("needed to anticipate that; the protocol allowed it.")
