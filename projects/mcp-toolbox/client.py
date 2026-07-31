#!/usr/bin/env python3
"""mcp-toolbox client: spawns server.py as a subprocess, performs the MCP-style
initialize handshake, lists tools, calls each one, and prints every raw
JSON-RPC frame with annotations. Windows-safe; a timeout guard on every read
means it can never hang.

Usage:  python client.py --demo
"""

import argparse
import json
import os
import queue
import subprocess
import sys
import threading

TIMEOUT_S = 5.0
SERVER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server.py")

class McpClient:
    def __init__(self):
        # sys.executable keeps this working on Windows (no shebang reliance).
        self.proc = subprocess.Popen(
            [sys.executable, SERVER],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, bufsize=1,
        )
        self.next_id = 0
        self.inbox = queue.Queue()
        t = threading.Thread(target=self._pump, daemon=True)
        t.start()

    def _pump(self):
        """Reader thread: blocking readline is fine here; the main thread only
        ever waits on the queue, with a timeout. This is the no-hang guarantee."""
        for line in self.proc.stdout:
            self.inbox.put(line.strip())

    def _send(self, frame, note):
        raw = json.dumps(frame)
        print("--> C->S  %-28s %s" % (note, raw))
        self.proc.stdin.write(raw + "\n")
        self.proc.stdin.flush()

    def _recv(self, note):
        try:
            raw = self.inbox.get(timeout=TIMEOUT_S)
        except queue.Empty:
            print("!! timeout after %.0fs waiting for %r -- killing server" % (TIMEOUT_S, note))
            self.proc.kill()
            sys.exit(1)
        print("<-- S->C  %-28s %s" % (note, raw))
        return json.loads(raw)

    def request(self, method, params=None, note=""):
        self.next_id += 1
        frame = {"jsonrpc": "2.0", "id": self.next_id, "method": method}
        if params is not None:
            frame["params"] = params
        self._send(frame, note or method)
        resp = self._recv("response to %s" % (note or method))
        assert resp.get("id") == self.next_id, "out-of-order response"
        return resp

    def notify(self, method, note=""):
        self._send({"jsonrpc": "2.0", "method": method}, note or method)
        # Notifications get no response; nothing to read.

    def shutdown(self):
        # MCP stdio lifecycle: close the server's stdin, it exits on EOF.
        self.proc.stdin.close()
        try:
            code = self.proc.wait(timeout=TIMEOUT_S)
            print("\nserver exited cleanly with code %s" % code)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            print("\nserver did not exit in time; killed")

def call_tool(client, name, arguments):
    resp = client.request("tools/call", {"name": name, "arguments": arguments},
                          note="tools/call %s" % name)
    result = resp.get("result", {})
    if "error" in resp:
        text, flag = resp["error"]["message"], " (protocol error)"
    else:
        text = result["content"][0]["text"]
        flag = " (isError=true)" if result.get("isError") else ""
    print("    => %s%s\n" % (text, flag))
    return text

def main(argv=None):
    ap = argparse.ArgumentParser(description="Drive the mcp-toolbox server.")
    ap.add_argument("--demo", action="store_true", help="run the scripted demo")
    ap.parse_args(argv)  # --demo is the only mode; flag kept for convention

    print("mcp-toolbox client :: annotated JSON-RPC session")
    print("=" * 64)
    c = McpClient()

    # --- Phase 1: handshake ------------------------------------------------
    print("\n[1] initialize handshake")
    resp = c.request("initialize", {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "toolbox-client", "version": "1.0.0"},
    })
    info = resp["result"]["serverInfo"]
    print("    => connected to %s v%s\n" % (info["name"], info["version"]))
    c.notify("notifications/initialized")

    # --- Phase 2: discovery ------------------------------------------------
    print("\n[2] tools/list discovery")
    resp = c.request("tools/list")
    tools = resp["result"]["tools"]
    for t in tools:
        print("    => %-15s %s" % (t["name"], t["description"]))
    print()

    # --- Phase 3: call every tool -----------------------------------------
    print("[3] tools/call round-robin")
    call_tool(c, "calculator", {"expression": "(3 + 4) * 12 / 2"})
    call_tool(c, "unit_converter", {"value": 42.195, "from_unit": "km", "to_unit": "mi"})
    call_tool(c, "text_stats", {"text": "The spice must flow. The spice extends life."})
    call_tool(c, "todo_store", {"action": "add", "item": "read the MCP spec"})
    call_tool(c, "todo_store", {"action": "add", "item": "build a real server"})
    call_tool(c, "todo_store", {"action": "list"})

    # --- Phase 4: an error, on purpose ------------------------------------
    print("[4] error handling (division by zero -> isError result)")
    call_tool(c, "calculator", {"expression": "1 / 0"})

    # --- Phase 5: clean shutdown ------------------------------------------
    print("[5] shutdown (close stdin, server exits on EOF)")
    c.shutdown()
    print("demo complete: %d tools exercised, 0 hangs, 0 regrets" % len(tools))
    return 0

if __name__ == "__main__":
    sys.exit(main())
