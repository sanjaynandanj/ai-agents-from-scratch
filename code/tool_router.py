"""Tool router: validate arguments, dispatch, and feed errors back as data.

Key insight: tool errors should never crash the agent. Validation failures
and runtime exceptions are captured and returned as observations, giving the
model a chance to repair its own call. Independent calls can also be batched
and run in parallel, exactly like modern parallel function calling.
"""

import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from concurrent.futures import ThreadPoolExecutor

from mock_llm import MockLLM, Tool

_TYPES = {"string": str, "integer": int, "number": (int, float),
          "boolean": bool, "array": list, "object": dict}


def validate_args(args: dict, schema: dict):
    """Return a list of human-readable errors ([] means valid)."""
    errors = []
    props = schema.get("properties", {})
    for req in schema.get("required", []):
        if req not in args:
            errors.append("missing required argument %r" % req)
    for key, value in args.items():
        if key not in props:
            errors.append("unexpected argument %r" % key)
            continue
        spec = props[key]
        want = spec.get("type")
        if want and not isinstance(value, _TYPES[want]):
            errors.append("argument %r must be %s, got %s"
                          % (key, want, type(value).__name__))
        if "enum" in spec and value not in spec["enum"]:
            errors.append("argument %r must be one of %s" % (key, spec["enum"]))
    return errors


class ToolRouter:
    def __init__(self):
        self._tools = {}

    def register(self, tool: Tool):
        self._tools[tool.name] = tool

    def dispatch(self, name: str, args: dict) -> dict:
        """Always returns an observation dict; never raises to the caller."""
        if name not in self._tools:
            return {"ok": False, "error": "unknown tool %r" % name}
        tool = self._tools[name]
        errors = validate_args(args, tool.params)
        if errors:
            return {"ok": False, "error": "invalid arguments: " + "; ".join(errors)}
        try:
            return {"ok": True, "result": tool.fn(**args)}
        except Exception as exc:
            return {"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)}

    def dispatch_batch(self, calls):
        """Run independent calls concurrently, preserving input order."""
        with ThreadPoolExecutor(max_workers=max(1, len(calls))) as pool:
            futures = [pool.submit(self.dispatch, c["name"], c["arguments"])
                       for c in calls]
            return [f.result() for f in futures]


if __name__ == "__main__":
    router = ToolRouter()
    router.register(Tool(
        "convert_temp", "Convert a temperature between units.",
        {"properties": {"value": {"type": "number"},
                        "to": {"type": "string", "enum": ["celsius", "fahrenheit"]}},
         "required": ["value", "to"]},
        lambda value, to: round(value * 9 / 5 + 32, 1) if to == "fahrenheit"
        else round((value - 32) * 5 / 9, 1)))
    router.register(Tool(
        "word_count", "Count words in a text.",
        {"properties": {"text": {"type": "string"}}, "required": ["text"]},
        lambda text: len(text.split())))

    print("=== Tool router demo ===\n")
    print("-- 1. Valid call --")
    call = {"name": "convert_temp", "arguments": {"value": 20, "to": "fahrenheit"}}
    print("call:        ", call)
    print("observation: ", router.dispatch(call["name"], call["arguments"]))

    print("\n-- 2. Invalid call, repaired via error feedback --")
    # The model first sends a bad enum value; the validation error is fed back
    # as an observation, and its scripted second attempt fixes the call.
    llm = MockLLM(script=[
        {"type": "tool_call", "name": "convert_temp",
         "arguments": {"value": 20, "to": "kelvin"}},
        {"type": "tool_call", "name": "convert_temp",
         "arguments": {"value": 20, "to": "celsius"}},
    ])
    messages = [{"role": "user", "content": "Convert 20F for me."}]
    for attempt in (1, 2):
        resp = llm.complete(messages)
        obs = router.dispatch(resp["name"], resp["arguments"])
        print("attempt %d call: %s" % (attempt, resp["arguments"]))
        print("attempt %d obs:  %s" % (attempt, obs))
        messages.append({"role": "tool", "content": str(obs)})
        if obs["ok"]:
            break

    print("\n-- 3. Parallel batch (independent calls fan out together) --")
    batch = [
        {"name": "convert_temp", "arguments": {"value": 0, "to": "fahrenheit"}},
        {"name": "word_count", "arguments": {"text": "tools are just functions"}},
        {"name": "word_count", "arguments": {"text": 42}},  # type error captured
    ]
    for c, r in zip(batch, router.dispatch_batch(batch)):
        print("%-60s -> %s" % (str(c), r))
    print("\nEvery failure came back as data the model can react to. No crashes.")
