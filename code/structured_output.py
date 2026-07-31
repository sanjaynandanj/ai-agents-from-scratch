"""Structured output: validate model JSON against a schema, then self-repair.

Key insight: you cannot trust a model to emit valid JSON on the first try,
but you can make invalidity cheap. Validate, append the exact validator
errors to the conversation, and ask again -- the errors act as a corrective
prompt, and one repair round fixes the vast majority of failures.
"""

import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import json

from mock_llm import MockLLM

_TYPES = {"string": str, "integer": int, "number": (int, float),
          "boolean": bool, "array": list, "object": dict}


def validate(instance, schema, path="$"):
    """Minimal JSON-Schema subset: type, required, properties, enum."""
    errors = []
    want = schema.get("type")
    if want:
        py = _TYPES[want]
        # bool is a subclass of int in Python; exclude it for integer/number.
        if not isinstance(instance, py) or (want != "boolean"
                                            and isinstance(instance, bool)):
            errors.append("%s: expected %s, got %s"
                          % (path, want, type(instance).__name__))
            return errors  # wrong type; deeper checks would be nonsense
    if "enum" in schema and instance not in schema["enum"]:
        errors.append("%s: %r not in enum %s" % (path, instance, schema["enum"]))
    if want == "object":
        for req in schema.get("required", []):
            if req not in instance:
                errors.append("%s: missing required property %r" % (path, req))
        for key, subschema in schema.get("properties", {}).items():
            if key in instance:
                errors.extend(validate(instance[key], subschema, path + "." + key))
    return errors


def extract_json(text):
    """Pull the first JSON object out of prose (models love to add prose)."""
    start = text.find("{")
    if start < 0:
        return None, "no JSON object found"
    try:
        obj, _ = json.JSONDecoder().raw_decode(text[start:])
        return obj, None
    except json.JSONDecodeError as exc:
        return None, "JSON parse error: %s" % exc


def get_structured(llm, schema, task, max_repairs=2):
    messages = [{"role": "user", "content":
                 "%s\nRespond with JSON matching: %s" % (task, json.dumps(schema))}]
    for round_no in range(1 + max_repairs):
        raw = llm.complete(messages)["content"]
        print("[round %d] model output: %s" % (round_no + 1, raw))
        obj, parse_err = extract_json(raw)
        errors = [parse_err] if parse_err else validate(obj, schema)
        if not errors:
            print("[round %d] validation: PASS" % (round_no + 1))
            return obj
        print("[round %d] validation errors:" % (round_no + 1))
        for e in errors:
            print("    - %s" % e)
        # The repair prompt: the errors themselves, verbatim.
        messages.append({"role": "assistant", "content": raw})
        messages.append({"role": "user", "content":
                         "Your JSON was invalid: %s. Emit corrected JSON only."
                         % "; ".join(errors)})
    raise ValueError("could not obtain valid output in %d rounds" % (1 + max_repairs))


if __name__ == "__main__":
    schema = {
        "type": "object",
        "required": ["name", "priority", "estimate_hours"],
        "properties": {
            "name": {"type": "string"},
            "priority": {"type": "string", "enum": ["low", "medium", "high"]},
            "estimate_hours": {"type": "number"},
            "blocked": {"type": "boolean"},
        },
    }
    # First attempt: prose wrapper, bad enum value, and a string where a
    # number belongs. Second attempt: corrected.
    llm = MockLLM(script=[
        'Sure! Here is the ticket: {"name": "Fix login bug", '
        '"priority": "urgent", "estimate_hours": "three"}',
        '{"name": "Fix login bug", "priority": "high", '
        '"estimate_hours": 3, "blocked": false}',
    ])

    print("=== Structured output repair demo ===\n")
    print("Target schema: %s\n" % json.dumps(schema))
    ticket = get_structured(llm, schema, "Create a ticket for the login bug.")
    print("\nFinal validated object: %s" % ticket)
    print("\nThe validator's error strings became the repair prompt -- no")
    print("hand-written correction logic, just a feedback loop around a schema.")
