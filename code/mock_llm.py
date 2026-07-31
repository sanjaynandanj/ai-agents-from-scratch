"""MockLLM: a deterministic stand-in for a chat-completion API.

Key insight: an agent framework only depends on the LLM's *interface*
(messages in -> text or tool_call out), not on its intelligence. By scripting
or rule-matching responses we can build and test every agent pattern with
zero API calls and perfectly reproducible runs.
"""

import random
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional


@dataclass
class Tool:
    """A capability advertised to the model, shaped like real function-calling APIs."""
    name: str
    description: str
    params: Dict[str, Any]  # JSON-schema-ish: {"properties": {...}, "required": [...]}
    fn: Callable[..., Any]

    def spec(self) -> Dict[str, Any]:
        return {"name": self.name, "description": self.description,
                "parameters": self.params}


class MockLLM:
    """Deterministic chat model.

    Modes (checked in order):
      1. scripted - a list of canned responses consumed one per call.
         Items may be callables (messages -> response) for late binding.
      2. rules    - list of (keyword, response); first keyword found in the
         conversation text wins. Good for flexible, reusable demos.

    Responses normalize to {"type": "text", "content": ...} or
    {"type": "tool_call", "name": ..., "arguments": {...}}, optionally
    carrying a "thought" (the ReAct reasoning trace).
    """

    def __init__(self, script: Optional[List[Any]] = None,
                 rules: Optional[List[tuple]] = None,
                 seed: int = 0, flakiness: float = 0.0):
        self.script = list(script) if script else []
        self.rules = list(rules) if rules else []
        self.rng = random.Random(seed)
        self.flakiness = flakiness  # chance of a degraded answer, for eval demos
        self.calls = 0

    def complete(self, messages: List[Dict[str, Any]],
                 tools: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        self.calls += 1
        if self.script:
            resp = self.script.pop(0)
        else:
            resp = self._match_rules(messages)
        if callable(resp):
            resp = resp(messages)
        resp = self._normalize(resp)
        # Seeded "temperature": occasionally degrade a text answer so eval
        # harnesses have real variance to measure (pass@k).
        if (resp["type"] == "text" and self.flakiness > 0
                and self.rng.random() < self.flakiness):
            resp = {"type": "text", "content": "Hmm, I am not sure about that."}
        return resp

    def _match_rules(self, messages):
        haystack = " ".join(str(m.get("content", "")) for m in messages).lower()
        for keyword, resp in self.rules:
            if keyword.lower() in haystack:
                return resp
        return {"type": "text", "content": "I do not have enough information."}

    @staticmethod
    def _normalize(resp) -> Dict[str, Any]:
        if isinstance(resp, str):
            return {"type": "text", "content": resp}
        if isinstance(resp, dict):
            if "type" in resp:
                return dict(resp)
            if "name" in resp:  # bare tool call shorthand
                return {"type": "tool_call", **resp}
        raise ValueError("Unsupported mock response: %r" % (resp,))


if __name__ == "__main__":
    print("=== MockLLM demo ===\n")

    print("-- Scripted mode: responses come back in order, like a rehearsed actor --")
    llm = MockLLM(script=[
        {"type": "tool_call", "thought": "Need the weather first.",
         "name": "get_weather", "arguments": {"city": "Toronto"}},
        "It is 22C and sunny in Toronto.",
    ])
    msgs = [{"role": "user", "content": "Weather in Toronto?"}]
    r1 = llm.complete(msgs, tools=[{"name": "get_weather"}])
    print("call 1 ->", r1)
    msgs += [{"role": "assistant", "content": str(r1)},
             {"role": "tool", "content": "22C, sunny"}]
    r2 = llm.complete(msgs)
    print("call 2 ->", r2)

    print("\n-- Rule mode: keyword -> response, order matters (first match wins) --")
    rule_llm = MockLLM(rules=[
        ("invoice", {"type": "tool_call", "name": "lookup_invoice",
                     "arguments": {"id": "INV-7"}}),
        ("hello", "Hello! How can I help?"),
    ])
    for prompt in ["hello there", "find invoice INV-7", "what is love?"]:
        out = rule_llm.complete([{"role": "user", "content": prompt}])
        print("%-22s -> %s" % (repr(prompt), out))

    print("\nSame seeds, same script, same rules => identical runs every time.")
