# Phase 08 — 🌐 Protocols: MCP & Friends

> Tools were bespoke. Then MCP made them USB.

Every agent needs tools; every tool used to need custom glue for every agent. This phase is about the protocols that ended the glue era: MCP for tools and context, A2A for agent-to-agent talk, OpenAPI as a tool source, and computer use as the protocol of last resort. You'll finish by writing an MCP server from scratch — raw JSON-RPC over stdio, no SDK — so the "magic" is permanently demystified.

## 01. Why Protocols: The N×M Integration Problem

**MOTTO:** N agents × M tools = N×M adapters. Protocols make it N+M.

### The Problem
You wrote a GitHub tool for your OpenAI agent. Now you want it in your Claude agent — rewrite. Now Cursor — rewrite. Every agent framework speaks its own tool dialect, so every integration is bespoke, and the ecosystem drowns in duplicated adapters.

### The Concept
The classic interoperability fix: a standard interface in the middle.

```
Without protocol:            With protocol:
 A1──T1  A1──T2  A1──T3       A1──┐         ┌──T1
 A2──T1  A2──T2  A2──T3       A2──┼──[MCP]──┼──T2
 A3──T1  A3──T2  A3──T3       A3──┘         └──T3
 9 adapters                   6 adapters (N+M)
```

USB did this for peripherals, LSP did it for editor-language integrations, HTTP did it for everything. A protocol succeeds when both sides win: tool authors write once and reach every client; agent authors integrate once and reach every tool.

### Build It
Nothing to code yet — build the judgment. Checklist for evaluating any agent protocol: What's standardized (transport? schema? discovery? auth?)? Who bears the migration cost? Is there a spec or just a vendor's SDK? Who else has adopted it?

### Use It
| Protocol | Solves N×M for |
|---|---|
| MCP | Agents ↔ tools/context |
| A2A | Agents ↔ agents |
| OpenAPI | Clients ↔ HTTP APIs (pre-dates agents, still central) |

### War Story
OpenAI's ChatGPT plugins (March 2023) were the first big swing at this problem — OpenAPI manifests as a universal tool layer. They were sunset in April 2024 in favor of GPTs' Actions. Seven months later Anthropic open-sourced MCP (November 2024), and within months it did what plugins didn't: cross-vendor adoption. The difference wasn't the idea; it was being an open protocol rather than one vendor's product feature.

### Checkpoint
1. Show the adapter arithmetic for 5 agents and 20 tools, with and without a protocol.
2. Why did LSP succeed at a structurally identical problem?
3. What made MCP's fate differ from ChatGPT plugins'?

## 02. MCP Architecture: Hosts, Clients, Servers

**MOTTO:** Three roles, one wire format, zero bespoke glue.

### The Problem
"Connect my agent to my tools" hides real questions: who spawns what, who holds credentials, who approves a dangerous call, what happens when there are five tool sources at once? A protocol needs named roles with defined responsibilities.

### The Concept
MCP defines three:
- **Host**: the LLM application (Claude Desktop, an IDE, your agent). Owns the model, the user, and the security decisions.
- **Client**: a connector object *inside* the host — one client per server connection, maintaining a stateful 1:1 session.
- **Server**: a program exposing capabilities (tools, resources, prompts) — often small, single-purpose.

```
┌────────────── HOST (e.g., Claude Desktop) ──────────────┐
│   LLM ⟷ [client A] ⟷ [client B] ⟷ [client C]            │
└─────────────│────────────│────────────│─────────────────┘
              ▼            ▼            ▼
        [server:git]  [server:db]  [server:slack]
```

Sessions start with a handshake: `initialize` exchanges protocol versions and *capability flags*, so both sides know what the other supports. The wire format throughout is JSON-RPC 2.0 — the same choice LSP made.

### Build It
- Config-level first: register a server in a host's config (command + args for stdio, or a URL) and watch its tools appear.
- Note who holds secrets: the *server* holds its API tokens; the host never sees them. That boundary is a feature.

### Use It
Hosts today: Claude Desktop and Claude Code, Cursor, Windsurf, VS Code (GitHub Copilot), ChatGPT, and the OpenAI Agents SDK — all speak the same servers.

### War Story
Anthropic released MCP on November 25, 2024. In March 2025 Sam Altman announced OpenAI would adopt it across its products, and in April 2025 Demis Hassabis said Google DeepMind would too — direct competitors adopting a rival's protocol within five months. That's the strongest possible signal a standard has escaped its creator.

### Checkpoint
1. Distinguish host, client, and server — and why client is a separate concept from host.
2. What does the `initialize` handshake negotiate?
3. Why is "the server holds its own credentials" a security feature?

## 03. MCP Tools, Resources, and Prompts

**MOTTO:** Verbs, nouns, and scripts — know which one you're shipping.

### The Problem
"Expose my stuff to the model" flattens three different things: actions the model can take, data the app can supply, and workflows the user can invoke. Mash them into one mechanism and you get tool lists cluttered with things that were never actions.

### The Concept
MCP's three primitives, distinguished by *who controls them*:

| Primitive | Nature | Controlled by | Example |
|---|---|---|---|
| Tool | Verb — do something | Model decides to call | `create_issue(title)` |
| Resource | Noun — readable data | Application attaches | `file:///repo/README.md` |
| Prompt | Script — a workflow | User invokes | `/summarize-thread` |

A tool is a function with a JSON Schema. A resource is content addressed by URI. A prompt is a parameterized template surfaced in the host's UI (slash-command style). Servers can also *ask the host* for things: sampling (request an LLM completion) and elicitation (request user input) — capabilities flowing in reverse.

### Build It
Sorting exercise for a database MCP server: `run_query` → tool. Table schemas → resources (`db://schema/users`). "Explain this week's slow queries" → prompt. If you'd shipped all three as tools, the model would "decide" to read schemas at random and users could never invoke the workflow directly.

### Use It
Anthropic's launch-day reference servers showed the split: Filesystem and Postgres servers lean on resources + tools; GitHub and Slack servers are tool-heavy; prompt-centric servers power slash commands in hosts like Claude Code.

### War Story
MCP launched in November 2024 with a suite of open-source reference servers — including Filesystem, GitHub, Git, Postgres, Slack, and Puppeteer — precisely so the three-primitive model had running examples on day one. Early adopters named at launch included Block and Apollo, with Zed, Replit, Codeium, and Sourcegraph working on integrations. Reference implementations, not spec prose, taught the ecosystem the tool/resource/prompt split.

### Checkpoint
1. Assign controller (model/app/user) to each of the three primitives.
2. Why shouldn't readable data be exposed as a tool?
3. What are sampling and elicitation, and which direction do they flow?

## 04. Building an MCP Server

**MOTTO:** One decorator per capability. The SDK does the wire; you do the value.

### The Problem
You have an internal API, a database, a pile of scripts. Every agent in the company wants access. Time to write the adapter *once* — as an MCP server — instead of once per agent framework.

### The Concept
With the official Python SDK (`FastMCP`), a server is decorated functions. Type hints become the JSON Schema; docstrings become the descriptions the model reads:

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("ticket-server")

@mcp.tool()
def search_tickets(query: str, limit: int = 10) -> str:
    """Search support tickets by keyword. Returns matching summaries."""
    return do_search(query, limit)          # your existing code

@mcp.resource("tickets://open")
def open_tickets() -> str:
    """All currently open tickets as JSON."""
    return json.dumps(load_open())

if __name__ == "__main__":
    mcp.run()                                # stdio by default
```

Descriptions are prompt engineering: the model chooses tools by reading them. "Search support tickets by keyword" beats "search function" — vague descriptions are the #1 cause of wrong-tool-chosen bugs.

### Build It
- Wrap 2–3 real functions; run with `mcp dev server.py` (MCP Inspector) to poke tools interactively before any LLM is involved.
- Register in Claude Code (`claude mcp add`) or Claude Desktop config; watch the model discover and call your tools.
- Return errors as *useful text* — the model reads them and adapts; a bare stack trace wastes the turn.

### Use It
| SDK | Language |
|---|---|
| `mcp` (FastMCP) | Python — official |
| `@modelcontextprotocol/sdk` | TypeScript — official |
| Community SDKs | Go, Rust, Java, C#, Kotlin |

### War Story
Within months of the November 2024 launch, community MCP servers numbered in the thousands, with registries like mcp.so and Smithery springing up to index them, and companies from Cloudflare to Stripe shipping official servers. The bar to entry — a decorated function — is exactly why the catalog exploded.

### Checkpoint
1. What do your type hints and docstring become on the wire?
2. Why test with MCP Inspector before connecting an LLM?
3. Why should tool errors be descriptive text rather than raw exceptions?

## 05. MCP Transports: stdio, HTTP, SSE

**MOTTO:** Same messages, different pipes. Choose the pipe for the deployment.

### The Problem
A local file server and a SaaS-hosted CRM server can't ship messages the same way: one is a subprocess on your laptop, the other is a URL serving thousands of users. The protocol messages are identical — the transport must differ.

### The Concept
```
stdio:              host spawns server as subprocess
   host ──stdin──▶ server           one user, local, trivial auth
   host ◀─stdout── server           (inherits your OS permissions)

Streamable HTTP:    server is a web service
   client ──POST /mcp──▶ server     remote, multi-user, OAuth
   client ◀── JSON or SSE stream ── (response can stream via SSE)
```

- **stdio**: newline-delimited JSON-RPC over the subprocess's stdin/stdout. Rule one: never `print()` to stdout in a stdio server — you'll corrupt the protocol stream. Log to stderr.
- **Streamable HTTP**: POST each message; the server replies with plain JSON or upgrades to an SSE stream for progressive/server-initiated messages.
- **HTTP+SSE** (the original remote transport, separate `/sse` + `/messages` endpoints): deprecated, still seen in the wild.

### Build It
- Ship local/personal tools as stdio (default in FastMCP).
- Ship shared/hosted tools as Streamable HTTP: `mcp.run(transport="streamable-http")`, put OAuth in front, treat it like any production web service.
- Debug tip: stdio servers can be tested with a hand-typed JSON-RPC line piped to the process — lesson 12 exploits this.

### Use It
| Deployment | Transport |
|---|---|
| Laptop dev tools, IDE integrations | stdio |
| Company-hosted tool gateway | Streamable HTTP + OAuth |
| Legacy remote servers | HTTP+SSE (migrate) |

### War Story
The MCP spec's March 2025 revision (2025-03-26) replaced the original HTTP+SSE transport with Streamable HTTP — the two-endpoint SSE design required long-lived connections that fought serverless platforms and load balancers, a lesson learned only after real deployments. Protocols are software: they ship bugs and ship fixes.

### Checkpoint
1. Why does `print()` break a stdio MCP server, and what's the fix?
2. What deployment realities killed the original HTTP+SSE transport?
3. Which transport for: a personal note-taking tool vs. a company CRM connector?

## 06. MCP Security: The Confused Deputy and Beyond

**MOTTO:** Every tool description is a prompt. Every prompt is an attack surface.

### The Problem
An MCP-enabled agent runs with *your* permissions — your files, your GitHub, your Slack. The classic confused deputy: a privileged intermediary tricked into using its authority for an attacker. With LLMs the trick doesn't need a buffer overflow; it needs a persuasive sentence.

### The Concept
The lethal trifecta: private data access + exposure to untrusted content + an exfiltration channel. MCP setups routinely have all three. Attack classes:

```
Tool poisoning     malicious instructions hidden in a tool's
                   description — the model reads and obeys them
Rug pull           server is benign at install, swaps tool
                   definitions after you've approved it
Cross-server       evil server's tool description instructs the
shadowing          model to misuse a *trusted* server's tools
Data-borne         injection arrives in tool RESULTS (an email
injection          body, a webpage) and steers later calls
```

### Build It
Defenses, layered (Phase 7 lesson 06 déjà vu):
- Pin and review: hash/version-pin server tool definitions; alert on changes.
- Least privilege: read-only tokens where possible; separate identities per server.
- Human-in-the-loop for irreversible actions — enforced by the *host*, not by prompts.
- Treat all tool results as untrusted input; never let "just text" reach another tool call unexamined.

### Use It
Host-level approval prompts (Claude Desktop/Code confirm tool calls), MCP gateways/proxies that scan and pin tool definitions, and OAuth resource-scoping in the 2025 spec revisions are the current defense stack.

### War Story
In April 2025, Invariant Labs published tool-poisoning attacks against real MCP setups — including a demo where a malicious server's tool description induced exfiltration of WhatsApp message history through a legitimate WhatsApp MCP server, invisible in the UI. In May 2025 they showed a GitHub MCP scenario where a poisoned public issue steered an agent into leaking private-repo data into a public PR. Months into the ecosystem, the deputy was already confused.

### Checkpoint
1. Map the confused deputy onto an MCP agent: who's the deputy, who's the attacker, what's the authority?
2. Why does the rug pull defeat one-time install review, and what defends against it?
3. Name the lethal trifecta and remove one leg for a concrete deployment.

## 07. A2A: Agent-to-Agent Communication

**MOTTO:** MCP gives agents hands. A2A gives them colleagues.

### The Problem
MCP connects an agent to *tools* — but a tool call is one shot: request, result, done. Delegating to another *agent* is different: tasks run for minutes or days, need progress updates, clarifying questions, and rich artifacts — and the two agents belong to different companies that won't share internals.

### The Concept
A2A (Agent2Agent), announced by Google in April 2025, standardizes peer delegation:
- **Agent Card**: a JSON discovery document (`/.well-known/agent.json`) advertising identity, skills, endpoint, auth requirements.
- **Task**: the unit of work, with a lifecycle (`submitted → working → input-required → completed/failed`) — inherently long-running.
- **Messages & Artifacts**: multi-turn dialogue within a task; typed outputs (text, files, structured data).
- Built on HTTP + JSON-RPC with SSE streaming and push notifications; agents stay *opaque* — capabilities are advertised, internals are not.

```
[client agent] ──discover card──▶ [remote agent]
       │──── task: "audit these invoices" ───▶│
       │◀─── status: working (stream) ────────│
       │◀─── input-required: "which FY?" ─────│
       │──── "FY2025" ────────────────────────▶│
       │◀─── artifact: audit_report.json ─────│
```

Complement, not competitor: MCP for agent→tool, A2A for agent→agent. Your agent might use both in one workflow.

### Build It
Serve an Agent Card, accept task submissions, emit status events, return artifacts — SDKs exist, but the mental model is "async job API with discovery and streaming."

### Use It
Cross-vendor delegation (your procurement agent hiring a supplier's quoting agent), and intra-enterprise meshes where teams ship agents as opaque services.

### War Story
Google announced A2A in April 2025 with 50+ named partners (Salesforce, SAP, Atlassian, LangChain among them), and in June 2025 donated the protocol to the Linux Foundation — with the announcement stressing MCP-complementarity rather than rivalry. The ecosystem visibly did not want another VHS-vs-Betamax.

### Checkpoint
1. Why is a tool-call abstraction wrong for delegating to another agent?
2. What does an Agent Card contain, and how is it discovered?
3. Why does agent opacity matter for cross-company delegation?

## 08. Function-Calling Dialects: OpenAI vs Anthropic vs Gemini

**MOTTO:** Same idea, three accents. Your abstraction layer is the translator.

### The Problem
Below the protocol layer, each provider's native API speaks its own function-calling dialect. Port an agent across providers and everything breaks at once: where schemas go, how calls come back, how results go in.

### The Concept
The differences that bite:

| | OpenAI | Anthropic | Gemini |
|---|---|---|---|
| Declare | `tools: [{type: "function", function: {...}}]` | `tools: [{name, description, input_schema}]` | `tools: [{function_declarations: [...]}]` |
| Call arrives | `tool_calls` on assistant msg; **args = JSON string** | `tool_use` content block; **input = object** | `functionCall` part; **args = object** |
| Result returns | `role: "tool"` message + `tool_call_id` | `role: "user"` msg with `tool_result` block | `functionResponse` part |
| Force a tool | `tool_choice: "required"` / named | `tool_choice: {type: "tool", name}` | `function_calling_config` mode `ANY` |

The classic porting bug: OpenAI's arguments arrive as a *string* needing `json.loads`; Anthropic's and Gemini's arrive parsed. Anthropic's "tool result goes in a user message" trips up everyone at least once.

### Build It
- Write a translation layer once: internal canonical `ToolCall {id, name, args: dict}` / `ToolResult {id, content}`, plus per-provider adapters ~30 lines each.
- Or adopt one: LiteLLM normalizes everything to OpenAI's dialect; Vercel AI SDK and LangChain do their own normalization.
- Test the seams: argument parsing, parallel calls, and forced tool choice differ most.

### Use It
LiteLLM, OpenRouter, and the OpenAI-compatible endpoints most providers now ship exist because of this lesson; MCP sits *above* all three dialects — the host translates MCP tools into its model's native dialect.

### War Story
OpenAI shipped function calling in June 2023 (gpt-4-0613); Anthropic's tool use went GA in May 2024; Gemini's arrived with its own conventions — three deliberate, incompatible designs for the same concept in under a year. The ecosystem's answer was translation layers: LiteLLM's pitch is literally "call 100+ LLMs in the OpenAI format." Dialects didn't converge; adapters won.

### Checkpoint
1. Which provider returns tool arguments as an unparsed string, and what bug does that cause?
2. How do tool results return to the model in Anthropic's dialect?
3. Where does MCP sit relative to these dialects?

## 09. OpenAPI as a Tool Source

**MOTTO:** The world's APIs already wrote their own tool definitions. Read them.

### The Problem
Thousands of services already publish machine-readable API descriptions — OpenAPI specs with paths, parameters, schemas, and docs. Hand-writing LLM tool definitions for an API that *already describes itself* is duplicated effort and instant drift.

### The Concept
Mechanical transformation:

```
OpenAPI operation                LLM tool
  operationId: createInvoice  →  name: "createInvoice"
  summary + description       →  description (what the model reads)
  parameters + requestBody    →  input JSON Schema
  the actual endpoint         →  executor: build & send HTTP request
```

One generic executor handles every generated tool: fill path params, set query/body, attach auth, call, return the response body as the tool result.

The catch: specs are written for developers, not models. A 300-operation spec flattened to 300 tools drowns the model — real pipelines *curate* (expose 10 relevant operations), *rewrite* descriptions that say useless things like "the id parameter is the id," and *summarize* elephantine response schemas.

### Build It
- Parse a small spec (petstore is tradition), generate tool defs, wire the generic HTTP executor, let the model book a pet.
- Add an allowlist of operationIds — curation as config.
- Handle auth outside the model: the executor injects keys; the model never sees them.

### Use It
| Tool | OpenAPI → agent |
|---|---|
| LangChain OpenAPI toolkit | Spec → toolkit |
| Custom GPTs "Actions" | Spec pasted into config |
| Speakeasy / Stainless-style gens | Spec → typed SDK → tools |
| MCP wrappers | Spec → generated MCP server |

### War Story
ChatGPT plugins (March 2023) bet everything on this: a plugin *was* an OpenAPI spec plus a manifest, model-facing descriptions and all. The plugins program was sunset in April 2024, but the mechanism survived intact inside GPTs' Actions — and the same year, the Gorilla paper (Patil et al., 2023) showed LLMs could be trained specifically to emit correct API calls from large API collections. The spec-as-tool-source idea outlived its first vehicle.

### Checkpoint
1. Which OpenAPI fields map to a tool's name, description, and schema?
2. Why does exposing all 300 operations of a spec hurt more than help?
3. Why must auth live in the executor rather than the tool schema?

## 10. Computer Use: Screenshots and Clicks as a Protocol

**MOTTO:** When there's no API, the screen is the API.

### The Problem
Legacy desktop apps, internal web tools, third-party sites with no public API — a huge share of real work lives behind interfaces built for eyeballs and mice. No MCP server, no OpenAPI spec, no function calls. Yet the work must flow.

### The Concept
Computer use turns the GUI itself into a tool interface — the universal fallback protocol:

```
loop:
  screenshot ──▶ model looks, reasons
  model emits ──▶ {action: "left_click", coordinate: [512, 384]}
                  {action: "type", text: "Q3 report"}
                  {action: "key", text: "Return"}
  execute in sandbox ──▶ new screenshot ──▶ repeat
```

The action vocabulary is tiny (screenshot, click, type, key, scroll); the intelligence is all in visual grounding — mapping "the Submit button" to pixel coordinates. It's slow (a screenshot round-trip per action), brittle (UIs change), and expensive (images are tokens) — which is why it's the *last resort* protocol, not the first.

### Build It
- Always sandbox: a VM or container the agent can't escape — it's clicking with your authority (lesson 06's deputy, now armed with a mouse).
- Cap actions per task; screenshot-diff to detect "nothing happened" loops.
- Prefer hybrid: API/MCP for everything that has one, computer use only for the gap.

### Use It
| System | Notes |
|---|---|
| Anthropic computer use (Oct 2024) | API tool: screenshot/click/type loop |
| OpenAI Operator → agent mode (Jan 2025) | Hosted browser agent (CUA model) |
| Browser-use, Playwright-MCP | Browser control, DOM or vision based |

### War Story
Anthropic shipped computer use in public beta in October 2024 — Claude 3.5 Sonnet scored 14.9% on the OSWorld benchmark (screenshot-only), roughly double the next best system's result but far below the ~72% human baseline, and Anthropic said so in the announcement. OpenAI's Operator followed in January 2025. Everyone shipped it humble; the gap to human is the roadmap.

### Checkpoint
1. Why is computer use the fallback protocol rather than the default?
2. What sandboxing and budget controls are non-negotiable, and why?
3. What is visual grounding, and why is it the hard part?

## 11. Skills and Slash Commands: Packaged Capabilities

**MOTTO:** Don't paste the runbook into every chat. Ship it as a file.

### The Problem
Your team's deploy procedure, your PDF-report style, your code-review checklist — this knowledge gets re-pasted into prompts daily, drifting with every copy. Tools (MCP) package *actions*; nothing so far packages *procedures and expertise*.

### The Concept
A **skill** is a folder of instructions the agent loads on demand:

```
pdf-reports/
├── SKILL.md        # name + description (always in context)
│                   # + full instructions (loaded when triggered)
├── template.html   # supporting files, read as needed
└── make_pdf.py     # scripts the agent can run
```

The key design is *progressive disclosure*: only each skill's name and one-line description sit in context permanently; the body loads when relevant. Fifty skills cost dozens of tokens until one fires. **Slash commands** are the manual-trigger cousin: user types `/deploy`, a stored prompt template expands — user-controlled, like MCP prompts, versus model-triggered skills.

Placement in the capability stack: MCP = *what the agent can touch*; skills = *what the agent knows how to do*; slash commands = *what the user can invoke by name*.

### Build It
- Write a SKILL.md for a real procedure: crisp trigger description up top ("Use when the user asks for a release"), then steps, edge cases, and a checklist.
- Add a script for the deterministic parts — instructions for judgment, code for mechanics (Phase 7 lesson 09, again).
- Version it in git; skills are prompts that finally get code review.

### Use It
| Mechanism | Trigger |
|---|---|
| Claude Agent Skills (SKILL.md) | Model-invoked by description match |
| Claude Code slash commands | User-typed `/name` |
| MCP prompts | User-invoked via host UI |
| Custom GPTs / Gems | Packaged persona + instructions |

### War Story
Anthropic launched Agent Skills in October 2025 — folders of markdown, scripts, and resources with progressive disclosure as the headline design, and its own anthropic/skills repo of examples. Claude Code's slash commands had already proven the pattern: capabilities as reviewable files in your repo beat capabilities as tribal prompt lore.

### Checkpoint
1. How does progressive disclosure keep 50 installed skills affordable?
2. Skills vs MCP tools: which packages knowledge, which packages access?
3. Why does "skills in git" improve on "prompts in a wiki"?

## 12. Build an MCP Server From Scratch

**MOTTO:** No SDK. Just you, stdin, and the JSON-RPC spec.

### The Problem
FastMCP's decorators are lovely and opaque. To *trust* the protocol — and debug it when a host misbehaves — you should speak it raw once: initialize handshake, `tools/list`, `tools/call`, over stdio, by hand.

### The Concept
An MCP server is a loop: read a JSON-RPC line from stdin, dispatch on `method`, write a JSON-RPC line to stdout. That's the whole trick.

### Build It
```python
#!/usr/bin/env python3
"""Minimal MCP server: JSON-RPC 2.0 over stdio. No SDK."""
import json, sys

TOOLS = [{
    "name": "add",
    "description": "Add two numbers and return the sum.",
    "inputSchema": {
        "type": "object",
        "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
        "required": ["a", "b"],
    },
}]

def handle(req):
    method, params = req.get("method"), req.get("params", {})
    if method == "initialize":
        return {"protocolVersion": "2025-03-26",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "scratch-server", "version": "0.1.0"}}
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "tools/call":
        if params.get("name") == "add":
            args = params.get("arguments", {})
            total = args["a"] + args["b"]
            return {"content": [{"type": "text", "text": str(total)}]}
        raise ValueError(f"unknown tool: {params.get('name')}")
    raise ValueError(f"unknown method: {method}")

def main():
    for line in sys.stdin:                      # newline-delimited JSON-RPC
        if not line.strip():
            continue
        req = json.loads(line)
        if "id" not in req:                     # notification (e.g. initialized)
            continue                            # no response allowed
        try:
            resp = {"jsonrpc": "2.0", "id": req["id"], "result": handle(req)}
        except Exception as e:
            resp = {"jsonrpc": "2.0", "id": req["id"],
                    "error": {"code": -32603, "message": str(e)}}
        sys.stdout.write(json.dumps(resp) + "\n")
        sys.stdout.flush()                      # unbuffered, or the host hangs
        print(f"handled {req['method']}", file=sys.stderr)   # logs → stderr!

if __name__ == "__main__":
    main()
```

Test it with no host at all:

```bash
printf '%s\n' \
 '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \
 '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
 '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"add","arguments":{"a":2,"b":40}}}' \
 | python server.py
```

Then register it in a real host (`claude mcp add scratch -- python server.py`) and watch an actual model call your forty lines. Exercises: (a) add a second tool with a `required` field, send a bad call, return a proper error; (b) break it on purpose — `print()` to stdout mid-loop — and observe the host-side failure; (c) forget `flush()` and watch it hang.

### Use It
Everything FastMCP generates is this file with more armor. When a server "doesn't show up" in a host, you can now bisect: handshake? capability flags? notification mishandled? stdout polluted? You've touched every failure point.

### War Story
MCP's choice of JSON-RPC 2.0 over stdio wasn't novel — it's the exact architecture of the Language Server Protocol, which Microsoft released in 2016 and which killed the N×M problem for editors and languages. Anthropic has been explicit about the LSP inspiration. You just rebuilt the pattern that standardized two ecosystems a decade apart.

### Checkpoint
1. Why must a server never respond to a request without an `id`?
2. Walk the full message sequence from host launch to a tool result.
3. What are the three ways this server can silently break a host, and the fix for each?
