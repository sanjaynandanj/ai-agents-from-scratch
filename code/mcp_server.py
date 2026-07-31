"""A minimal MCP-style server: JSON-RPC 2.0 with initialize / tools/list / tools/call.

Key insight: MCP is not magic -- it is a tiny JSON-RPC vocabulary that lets
any client discover and invoke any server's tools without knowing them at
compile time. The transport (in-process, stdio, socket) is interchangeable;
the frames are the protocol.
"""

import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import json

from mock_llm import Tool

PROTOCOL_VERSION = "2025-03-26"


class MCPServer:
    def __init__(self, name, tools):
        self.name = name
        self.tools = {t.name: t for t in tools}

    def handle(self, raw: str) -> str:
        """One JSON-RPC request frame in, one response frame out."""
        try:
            req = json.loads(raw)
        except json.JSONDecodeError:
            return self._err(None, -32700, "parse error")
        rid, method, params = req.get("id"), req.get("method"), req.get("params", {})
        if method == "initialize":
            result = {"protocolVersion": PROTOCOL_VERSION,
                      "serverInfo": {"name": self.name, "version": "0.1"},
                      "capabilities": {"tools": {}}}
        elif method == "tools/list":
            result = {"tools": [{"name": t.name, "description": t.description,
                                 "inputSchema": t.params}
                                for t in self.tools.values()]}
        elif method == "tools/call":
            name = params.get("name")
            if name not in self.tools:
                return self._err(rid, -32602, "unknown tool %r" % name)
            try:
                out = self.tools[name].fn(**params.get("arguments", {}))
                result = {"content": [{"type": "text", "text": str(out)}],
                          "isError": False}
            except Exception as exc:  # tool errors are results, not protocol errors
                result = {"content": [{"type": "text", "text": str(exc)}],
                          "isError": True}
        else:
            return self._err(rid, -32601, "method not found: %r" % method)
        return json.dumps({"jsonrpc": "2.0", "id": rid, "result": result})

    @staticmethod
    def _err(rid, code, message):
        return json.dumps({"jsonrpc": "2.0", "id": rid,
                           "error": {"code": code, "message": message}})

    def serve_stdio(self):  # optional transport: one frame per line
        for line in sys.stdin:
            if line.strip():
                print(self.handle(line), flush=True)


class MCPClient:
    """Talks to any MCPServer through a transport function (str -> str)."""

    def __init__(self, transport, verbose=True):
        self.transport = transport
        self.verbose = verbose
        self._id = 0

    def request(self, method, params=None):
        self._id += 1
        frame = json.dumps({"jsonrpc": "2.0", "id": self._id,
                            "method": method, "params": params or {}})
        if self.verbose:
            print("  -> %s" % frame)
        raw = self.transport(frame)
        if self.verbose:
            print("  <- %s" % raw)
        resp = json.loads(raw)
        if "error" in resp:
            raise RuntimeError(resp["error"]["message"])
        return resp["result"]

    def initialize(self):
        return self.request("initialize", {"protocolVersion": PROTOCOL_VERSION})

    def list_tools(self):
        return self.request("tools/list")["tools"]

    def call_tool(self, name, arguments):
        return self.request("tools/call", {"name": name, "arguments": arguments})


if __name__ == "__main__":
    server = MCPServer("demo-utils", [
        Tool("slugify", "Turn a title into a URL slug.",
             {"type": "object", "properties": {"title": {"type": "string"}},
              "required": ["title"]},
             lambda title: "-".join(title.lower().split())),
        Tool("char_stats", "Count characters and words in text.",
             {"type": "object", "properties": {"text": {"type": "string"}},
              "required": ["text"]},
             lambda text: {"chars": len(text), "words": len(text.split())}),
    ])
    # In-process transport: the simplest possible wire.
    client = MCPClient(server.handle)

    print("=== MCP demo: every frame on the wire ===\n")
    print("[handshake]")
    info = client.initialize()
    print("connected to %(name)s v%(version)s" % info["serverInfo"], "\n")

    print("[discovery]")
    tools = client.list_tools()
    print("discovered %d tools: %s\n" % (len(tools), [t["name"] for t in tools]))

    print("[call 1: slugify]")
    r1 = client.call_tool("slugify", {"title": "AI Agents From Scratch"})
    print("result text: %s\n" % r1["content"][0]["text"])

    print("[call 2: char_stats]")
    r2 = client.call_tool("char_stats", {"text": "protocols beat plugins"})
    print("result text: %s\n" % r2["content"][0]["text"])

    print("[error path: unknown tool]")
    try:
        client.call_tool("rm_rf", {})
    except RuntimeError as exc:
        print("client saw JSON-RPC error: %s" % exc)
    print("\nSwap server.handle for a stdio pipe (serve_stdio) and nothing else")
    print("changes -- discovery and invocation ride the same three methods.")
