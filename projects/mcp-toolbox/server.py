#!/usr/bin/env python3
"""mcp-toolbox server: an MCP-style tool server speaking JSON-RPC 2.0 over
stdio (one JSON message per line in, one per line out).

Pure Python 3 stdlib. Run it directly and type JSON-RPC frames, or drive it
with client.py, which is how it is meant to be used.
"""

import ast
import json
import operator
import sys

PROTOCOL_VERSION = "2025-06-18"
SERVER_INFO = {"name": "mcp-toolbox", "version": "1.0.0"}

# ---------------------------------------------------------------------------
# Tool implementations (real, working, boring on purpose)
# ---------------------------------------------------------------------------

_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
    ast.USub: operator.neg, ast.UAdd: operator.pos, ast.FloorDiv: operator.floordiv,
}

def _safe_eval(node):
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_safe_eval(node.operand))
    raise ValueError("unsupported expression element: %s" % type(node).__name__)

def tool_calculator(args):
    expr = args["expression"]
    result = _safe_eval(ast.parse(expr, mode="eval"))
    return "%s = %s" % (expr, round(result, 10))

_LINEAR = {  # (from, to): factor
    ("km", "mi"): 0.621371, ("mi", "km"): 1.609344,
    ("kg", "lb"): 2.204623, ("lb", "kg"): 0.453592,
    ("m", "ft"): 3.280840, ("ft", "m"): 0.304800,
}

def tool_unit_converter(args):
    value, src, dst = float(args["value"]), args["from_unit"], args["to_unit"]
    if (src, dst) in _LINEAR:
        out = value * _LINEAR[(src, dst)]
    elif (src, dst) == ("c", "f"):
        out = value * 9 / 5 + 32
    elif (src, dst) == ("f", "c"):
        out = (value - 32) * 5 / 9
    else:
        raise ValueError("unsupported conversion %s->%s" % (src, dst))
    return "%g %s = %g %s" % (value, src, round(out, 4), dst)

def tool_text_stats(args):
    text = args["text"]
    words = [w.strip(".,;:!?\"'()").lower() for w in text.split()]
    words = [w for w in words if w]
    sentences = sum(text.count(p) for p in ".!?") or (1 if words else 0)
    freq = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1
    top = sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
    return json.dumps({
        "chars": len(text), "words": len(words), "sentences": sentences,
        "top_words": ["%s x%d" % (w, n) for w, n in top],
    })

_TODOS = []

def tool_todo_store(args):
    action = args["action"]
    if action == "add":
        _TODOS.append(args["item"])
        return "added #%d: %s" % (len(_TODOS), args["item"])
    if action == "list":
        if not _TODOS:
            return "(empty list)"
        return "; ".join("#%d %s" % (i + 1, t) for i, t in enumerate(_TODOS))
    raise ValueError("unknown action %r (use add|list)" % action)

TOOLS = {
    "calculator": {
        "fn": tool_calculator,
        "description": "Evaluate an arithmetic expression (+ - * / ** % //).",
        "inputSchema": {"type": "object", "required": ["expression"],
                        "properties": {"expression": {"type": "string"}}},
    },
    "unit_converter": {
        "fn": tool_unit_converter,
        "description": "Convert km/mi, kg/lb, m/ft, c/f.",
        "inputSchema": {"type": "object",
                        "required": ["value", "from_unit", "to_unit"],
                        "properties": {"value": {"type": "number"},
                                       "from_unit": {"type": "string"},
                                       "to_unit": {"type": "string"}}},
    },
    "text_stats": {
        "fn": tool_text_stats,
        "description": "Count chars, words, sentences and top words in text.",
        "inputSchema": {"type": "object", "required": ["text"],
                        "properties": {"text": {"type": "string"}}},
    },
    "todo_store": {
        "fn": tool_todo_store,
        "description": "In-memory todo list. Actions: add (with item), list.",
        "inputSchema": {"type": "object", "required": ["action"],
                        "properties": {"action": {"type": "string"},
                                       "item": {"type": "string"}}},
    },
}

# ---------------------------------------------------------------------------
# JSON-RPC 2.0 plumbing
# ---------------------------------------------------------------------------

def reply(id_, result):
    return {"jsonrpc": "2.0", "id": id_, "result": result}

def error(id_, code, message):
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}

def handle(msg):
    """Return a response dict, or None for notifications."""
    method, id_ = msg.get("method"), msg.get("id")
    params = msg.get("params") or {}
    if method == "initialize":
        return reply(id_, {"protocolVersion": PROTOCOL_VERSION,
                           "capabilities": {"tools": {}},
                           "serverInfo": SERVER_INFO})
    if method == "notifications/initialized":
        return None  # notification: no id, no response
    if method == "ping":
        return reply(id_, {})
    if method == "tools/list":
        listing = [{"name": n, "description": t["description"],
                    "inputSchema": t["inputSchema"]}
                   for n, t in sorted(TOOLS.items())]
        return reply(id_, {"tools": listing})
    if method == "tools/call":
        name = params.get("name")
        if name not in TOOLS:
            return error(id_, -32602, "unknown tool: %r" % name)
        try:
            text = TOOLS[name]["fn"](params.get("arguments") or {})
            return reply(id_, {"content": [{"type": "text", "text": text}],
                               "isError": False})
        except Exception as exc:  # tool errors are results, not protocol errors
            return reply(id_, {"content": [{"type": "text",
                                            "text": "tool error: %s" % exc}],
                               "isError": True})
    if id_ is None:
        return None  # unknown notification: ignore per spec
    return error(id_, -32601, "method not found: %r" % method)

def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            print(json.dumps(error(None, -32700, "parse error")), flush=True)
            continue
        resp = handle(msg)
        if resp is not None:
            print(json.dumps(resp), flush=True)
    # EOF on stdin means the client hung up: exit cleanly (MCP stdio lifecycle).

if __name__ == "__main__":
    main()
