# Project: MCP Toolbox

Build a working MCP-style tool server and a client that drives it — from raw
JSON-RPC 2.0 frames up. Two files, zero dependencies, and by the end you will
have watched every byte of an `initialize` handshake, a `tools/list`
discovery, and a batch of `tools/call` invocations scroll past, annotated.

This is the protocol layer that every "my agent can use tools" product sits
on. Once you have hand-rolled it, MCP stops being magic and starts being
plumbing you can debug.

## MCP in five minutes

The Model Context Protocol connects an AI application (the **host**, running a
**client**) to a **server** that exposes capabilities — most famously tools.
The wire format is **JSON-RPC 2.0**:

- Every request: `{"jsonrpc": "2.0", "id": N, "method": "...", "params": {...}}`
- Every response: same `id`, plus either `"result"` or `"error"`.
- **Notifications** have no `id` and get no response.

The lifecycle we implement, in order:

1. `initialize` — client sends its protocol version and info; server replies
   with *its* version, capabilities (`{"tools": {}}`), and `serverInfo`.
2. `notifications/initialized` — client fires a notification saying "ready".
3. `tools/list` — server returns each tool's `name`, `description`, and a
   JSON Schema `inputSchema` (this is what an LLM reads to pick tools).
4. `tools/call` — invoke by name with `arguments`; result is a `content`
   array of `{"type": "text", "text": ...}` blocks plus an `isError` flag.
5. Shutdown — for the stdio transport there is no shutdown *method*: the
   client closes the server's stdin, and the server exits on EOF.

### How faithful is this to the real spec?

Faithful where it teaches, simplified where it distracts:

| Real MCP                              | This project                        |
|---------------------------------------|-------------------------------------|
| stdio transport, newline-delimited    | same (one JSON message per line)    |
| initialize / initialized lifecycle    | same                                |
| tools/list with JSON Schema           | same shape                          |
| tools/call content blocks + isError   | same shape                          |
| tool errors are results, not RPC errors | same (try it: `1 / 0`)           |
| resources, prompts, sampling, capabilities negotiation | omitted        |
| pagination, progress, cancellation    | omitted                             |

## Architecture

```
  +--------------------+     stdin (JSON-RPC lines)     +------------------+
  |     client.py      | -----------------------------> |     server.py    |
  |  spawns subprocess |                                |  4 real tools:   |
  |  reader thread +   | <----------------------------- |   calculator     |
  |  queue w/ timeout  |     stdout (JSON-RPC lines)    |   unit_converter |
  |  (can never hang)  |                                |   text_stats     |
  +--------------------+                                |   todo_store     |
                                                        +------------------+
```

The client's no-hang guarantee is worth studying: a daemon thread does the
blocking `readline` and feeds a `queue.Queue`; the main thread only ever does
`queue.get(timeout=5)`. If the server wedges, the client kills it and exits 1
instead of freezing your terminal. (`proc.stdout.readline` with a timeout is
not portable to Windows; the thread+queue trick is.)

## Milestones

1. **Echo server.** Read lines from stdin, parse JSON, write back a valid
   JSON-RPC response with the same `id`. Handle a parse error with code
   `-32700` and unknown methods with `-32601`.
2. **Handshake.** Implement `initialize` and accept the `initialized`
   notification (no response! notifications never get one).
3. **Tools registry.** A dict of `{name: {fn, description, inputSchema}}`.
   Implement `tools/list` from it, sorted for determinism.
4. **tools/call + the error rule.** Dispatch to the function. A *tool* failure
   (bad expression, divide by zero) must come back as a normal result with
   `isError: true` — only protocol-level problems use JSON-RPC `error`.
5. **The client.** Spawn with `[sys.executable, "server.py"]` (Windows-safe —
   never rely on shebangs), do the full sequence, print annotated `C->S` /
   `S->C` frames, and shut down by closing stdin.
6. **Timeout guard.** Reader thread + queue, kill-on-timeout. Prove it by
   temporarily making the server sleep.

## Run it

```
python client.py --demo
```

Exits by itself. You should see five phases: handshake, discovery, a
round-robin calling all four tools (todo_store gets three calls: add, add,
list), a deliberate `1 / 0` returning `isError=true`, and a clean shutdown
with the server's exit code.

You can also talk to the server by hand:

```
python server.py
{"jsonrpc":"2.0","id":1,"method":"tools/list"}
```

(then Ctrl+Z Enter on Windows / Ctrl+D on Unix to send EOF and end it).

## What "done" looks like

- Every frame on the wire is valid JSON-RPC 2.0, one per line.
- `notifications/initialized` produces no response and nothing blocks on it.
- `1 / 0` yields `isError: true`, not a protocol error.
- Killing the demo mid-run never leaves a zombie python process.

## Extension ideas

- **Capability honesty:** advertise `listChanged` and send a
  `notifications/tools/list_changed` when a fifth tool registers at runtime.
- **Schema validation:** validate `arguments` against `inputSchema` before
  dispatch and return `-32602` on mismatch (write a mini validator: `type`,
  `required` is plenty).
- **Persistence:** back `todo_store` with a JSON file so todos survive
  restarts — congratulations, you now have state and all its problems.
- **Second transport:** wrap the same `handle()` function in an HTTP POST
  endpoint using `http.server` — one brain, two transports, exactly how the
  real spec splits protocol from transport.
- **Plug it in:** point a real MCP host at your server and see how far the
  handshake gets; every gap it hits is a lesson.
