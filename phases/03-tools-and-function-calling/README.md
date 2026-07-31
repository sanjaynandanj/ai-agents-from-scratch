# Phase 03 — 🔧 Tools & Function Calling

> A model that can only talk is a consultant. Give it hands.

Everything before this phase produced text. Useful text, sometimes — but text nonetheless. This phase is where your agent stops describing actions and starts taking them: calling APIs, running code, editing files, searching the web. The mechanism underneath is almost embarrassingly simple — the model emits structured JSON, your code executes it, and you feed the result back — but the engineering around that loop (schemas, dispatch, errors, sandboxing, tool design) is where real agents are won or lost.

## 01. Tool Schemas: Describing Functions to a Model

**MOTTO:** A tool schema is a job posting — write a vague one and you'll hire the wrong call.

### The Problem
You have a `get_weather(city, units)` function. The model has never seen your code, can't import your module, and only consumes tokens. If you just say "you can check the weather," the model will invent a calling convention: `weather("Paris, please, in celsius")`. You need a contract, not a vibe.

### The Concept
A tool schema is a machine-readable job posting: name, description, and typed parameters, almost always expressed as JSON Schema. The model reads the posting and emits a structured application (a JSON object) that your code can validate and execute.

```
  You define:                      Model emits:
  {                                {
    "name": "get_weather",           "name": "get_weather",
    "description": "...",     ──►    "arguments": {
    "parameters": {                     "city": "Paris",
      "city": string (req),            "units": "celsius"
      "units": enum[c,f]             }
    }                              }
  }
```

The schema goes into the prompt (providers inject it into a system-level block); the model's "function call" is just constrained text generation shaped like your schema.

### Build It
1. Write your function normally in Python.
2. Derive a schema dict: name, description, and a JSON Schema `parameters` object with `type`, `enum`, `required`.
3. Serialize the schema into the request alongside the messages.
4. Parse the model's output as JSON; validate against the schema before executing.

```python
def schema_from(fn):
    import inspect
    sig = inspect.signature(fn)
    props = {p: {"type": "string"} for p in sig.parameters}
    return {"name": fn.__name__,
            "description": fn.__doc__ or "",
            "parameters": {"type": "object", "properties": props,
                           "required": list(sig.parameters)}}
```

Real frameworks do exactly this with type hints and docstrings — nothing magic.

### Use It
| Approach | Tradeoff |
|---|---|
| Hand-written JSON Schema | Full control, verbose, drifts from code |
| Pydantic / `TypeAdapter` | Schema auto-derived, validation free, Python-only |
| OpenAI/Anthropic tool params | Native, provider-validated; formats differ slightly |
| MCP (Model Context Protocol) | Tools as portable servers; extra moving part |

### War Story
The Toolformer paper (Meta AI, February 2023) showed a model could teach *itself* when to call APIs — calculator, search, translation — by self-annotating training data with API calls that reduced loss. Four months later, in June 2023, OpenAI shipped function calling as a first-class API feature, and hand-parsing "please respond in JSON" prompts became legacy code overnight.

### Checkpoint
1. Why does the model need a JSON Schema rather than just your function's source code?
2. What happens if two tools have similar descriptions and overlapping parameters?
3. Where does the schema physically live from the model's point of view?

## 02. Tool Choice: Auto, Required, Forced, None

**MOTTO:** Deciding *whether* to call a tool is a decision you can take away from the model.

### The Problem
User asks "what's 2+2?" and your agent solemnly calls the calculator API. User asks "what's our refund policy?" and the agent freelances an answer instead of calling the docs search. The model's judgment about *when* to use tools is good but not free — and sometimes you know better.

### The Concept
Tool choice is a dial with four positions, set per-request by *you*, not the model:

```
  none ──── auto ──── required ──── forced("get_weather")
   │          │           │              │
  never    model      must call       must call
  calls    decides    some tool       THIS tool
```

Think of it as delegation levels for a new employee: "don't touch anything," "use your judgment," "you must use a tool for this," "use exactly this tool."

### Build It
1. `none`: don't include tool schemas in the request (or include them but instruct text-only) — model can only answer in prose.
2. `auto`: include schemas; model picks tool-call or text per its judgment.
3. `required`: include schemas and reject/retry any response that isn't a tool call.
4. `forced`: include only one schema, or constrain decoding to that tool's name.

```python
def enforce(response, mode, tool=None):
    if mode == "required" and not response.tool_calls:
        return retry_with_hint("You must call a tool.")
    if mode == "forced" and response.tool_calls[0].name != tool:
        return retry_with_hint(f"You must call {tool}.")
    return response
```

Forcing on the first turn is a common trick for extraction pipelines: force a `record_result` tool and you get guaranteed structured output.

### Use It
| Mode | Use when |
|---|---|
| `auto` | General agents; default |
| `required` | Router turns where "just chat" is never valid |
| `forced` | Structured extraction; guaranteed first-step tools |
| `none` | Final summarization turn after tool results are in |

OpenAI calls this `tool_choice`; Anthropic uses `tool_choice: {type: auto|any|tool}` — `any` is their "required."

### War Story
Before native structured output existed, forced tool calling was *the* trick for reliable JSON extraction — you defined a dummy tool whose parameters were your output schema and forced it. OpenAI later formalized this pattern as Structured Outputs (August 2024) with constrained decoding that guarantees schema-valid JSON, essentially productizing what everyone was already doing with forced tools.

### Checkpoint
1. What's the difference between `required` and forcing a specific tool?
2. Why might you set `tool_choice: none` on the final turn of an agent loop?
3. How can forced tool calling give you guaranteed structured output?

## 03. Parallel Tool Calls

**MOTTO:** If the model asks three independent questions, don't answer them one at a time.

### The Problem
Your travel agent needs weather in Paris, weather in Rome, and flight prices between them. Sequential tool calls mean three full model round-trips: call, wait, respond, call, wait, respond... Each round-trip costs a model invocation (dollars) and seconds of latency. The user watches a spinner while your agent plays twenty questions with itself.

### The Concept
Modern models can emit *multiple* tool calls in a single response when the calls are independent. Your executor fans out, runs them concurrently, and returns all results in one batch:

```
  Model turn:  [call get_weather(Paris), call get_weather(Rome), call get_flights(P,R)]
                     │                        │                       │
                     ▼                        ▼                       ▼
               ┌──────────┐            ┌──────────┐            ┌──────────┐
               │ executor │            │ executor │            │ executor │   (concurrent)
               └────┬─────┘            └────┬─────┘            └────┬─────┘
                    └───────────┬───────────┴───────────────────────┘
                                ▼
               One follow-up turn with all three results
```

One model turn instead of three. The catch: results must be matched back to calls by ID, and order of completion is not order of issue.

### Build It
1. Parse *all* tool calls from the response, each with its unique `id`.
2. Execute concurrently (`asyncio.gather` or a thread pool for blocking I/O).
3. Return one result message per call, tagged with the matching `id` — providers require every call to get an answer, even if it's an error.

```python
import asyncio

async def run_all(tool_calls, registry):
    async def one(call):
        try:
            out = await registry[call.name](**call.args)
        except Exception as e:
            out = f"ERROR: {e}"
        return {"tool_call_id": call.id, "content": str(out)}
    return await asyncio.gather(*(one(c) for c in tool_calls))
```

4. Never parallelize calls with ordering dependencies (write-then-read). If the model does it anyway, execute serially or reject.

### Use It
| Concern | Practice |
|---|---|
| Blocking Python tools | `ThreadPoolExecutor`, cap workers |
| Rate limits | Semaphore per external API |
| One call fails | Return error for that ID, real results for the rest |
| Side-effecting tools | Consider disabling parallel for writes |

OpenAI shipped parallel function calling at DevDay in November 2023; Anthropic models emit multiple `tool_use` blocks in one message.

### War Story
OpenAI introduced parallel function calling alongside GPT-4 Turbo at its first DevDay (November 6, 2023). Early adopters immediately hit the classic bug: answering only the first tool call and dropping the rest, which the API rejects — every tool_call ID in the assistant message must receive a corresponding result message.

### Checkpoint
1. Why must every tool call ID receive a result message, even for failed calls?
2. When is parallel execution of tool calls actively dangerous?
3. What does parallel calling save compared to sequential calls — tokens, latency, or model invocations?

## 04. Tool Errors: Retry, Explain, or Give Up

**MOTTO:** An error message is just another observation — feed it back and let the model debug itself.

### The Problem
The model calls `get_user(id="bob")` but the API wants an integer. Your executor throws, your agent crashes, and the user sees a stack trace. Or worse: you silently swallow the error, and the model confidently continues as if the call succeeded, hallucinating the data it never got.

### The Concept
Errors are information. The same feedback loop that makes agents work on success makes them work on failure — return the error *as the tool result* and the model usually fixes its own call:

```
  call: get_user(id="bob")
   └─► TOOL ERROR: "id must be an integer. Got str 'bob'.
        Hint: use search_users(name=...) to find an id."
        └─► model: calls search_users(name="bob") → gets id 42
             └─► calls get_user(id=42) ✓
```

Three escalation levels: (1) retry silently for transient faults (network blips, 429s) — the model never needs to know; (2) explain — return a descriptive error and let the model adapt; (3) give up — after N failures, stop and tell the user honestly.

### Build It
1. Wrap every tool execution in try/except. Never let a tool exception kill the loop.
2. Classify: transient (timeout, 429, 503) → auto-retry with exponential backoff, invisible to the model.
3. Permanent (validation, 404, permission) → format a *helpful* error string: what failed, why, and what to try instead.
4. Count failures per tool per task. At the cap, return "this tool is unavailable, proceed without it or report failure."

```python
def execute(call, registry, attempts=3):
    for i in range(attempts):
        try:
            return registry[call.name](**call.args)
        except TransientError:
            time.sleep(2 ** i)
        except Exception as e:
            return f"ERROR calling {call.name}: {e}. Check argument types and retry, or use a different tool."
    return f"ERROR: {call.name} failed {attempts} times; treat it as unavailable."
```

### Use It
| Error type | Strategy |
|---|---|
| 429 / timeout | Silent retry + backoff, never shown to model |
| Bad arguments | Explain with a hint; model self-corrects well |
| Auth / permission | Don't retry; surface to user |
| Repeated identical failure | Circuit-break: mark tool dead for this task |

Good error messages are prompt engineering — "Invalid input" teaches the model nothing; "expected ISO date, got 'tomorrow'" fixes the next call.

### War Story
The ReAct paper (Yao et al., 2022) demonstrated the core insight formally: interleaving reasoning with environment observations — including error observations — let models recover from failed actions instead of compounding them, beating action-only baselines on ALFWorld and WebShop. Every "feed the traceback back to the model" pattern in modern coding agents is this loop.

### Checkpoint
1. Why should transient errors be retried *without* telling the model, while validation errors should be shown to it?
2. What makes a tool error message "good" from the model's perspective?
3. What failure mode does a per-task retry cap prevent?

## 05. Sandboxing Code Execution

**MOTTO:** The model writes the code; you decide what universe it runs in.

### The Problem
Code execution is the most powerful tool you can give an agent — and `exec(model_output)` on your laptop is a security incident with extra steps. The code might `rm -rf` something, exfiltrate your `.env`, loop forever, or allocate 60 GB of RAM. And the model doesn't have to be malicious — prompt injection means *someone else's text* can steer what code gets written.

### The Concept
A sandbox is a blast radius you choose in advance. Layers, from paper walls to bank vaults:

```
  exec() in-process        ← no wall at all
  subprocess + rlimits     ← time/memory fences, same filesystem
  container (Docker)       ← own filesystem, drop network, read-only mounts
  microVM (Firecracker)    │
  Wasm / gVisor            ← hardware-grade isolation
```

The prison-workshop analogy: the inmate can build anything with the tools inside the room, but the room has no windows, a timed door, and nothing valuable stored in it.

### Build It
A minimal-but-honest subprocess sandbox:
1. Write the model's code to a temp file in an empty working directory.
2. Run it as a subprocess with a hard wall-clock timeout.
3. Apply resource limits (`resource.setrlimit` on Unix: CPU seconds, address space, file size, no core dumps).
4. Capture stdout/stderr (truncated), return both plus the exit code as the tool result.

```python
import subprocess, tempfile, os

def run_code(code, timeout=10):
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "snippet.py")
        open(path, "w").write(code)
        try:
            p = subprocess.run(["python", "-I", path], cwd=d,
                               capture_output=True, text=True, timeout=timeout)
            return f"exit={p.returncode}\nstdout:\n{p.stdout[:4000]}\nstderr:\n{p.stderr[:2000]}"
        except subprocess.TimeoutExpired:
            return "ERROR: execution timed out after 10s"
```

This stops accidents, not attackers — a real adversary needs container/VM isolation and a denied-by-default network.

### Use It
| Option | Isolation | Cold start | Notes |
|---|---|---|---|
| subprocess + rlimits | Weak | ~0 | Fine for trusted, local dev |
| Docker (no net, RO rootfs) | Good | ~100ms–1s | The pragmatic default |
| Firecracker microVMs | Strong | ~125ms | What serverless sandboxes build on |
| Hosted (E2B, Modal, Daytona) | Strong | varies | Someone else's blast radius |

### War Story
When OpenAI shipped Code Interpreter for ChatGPT (announced March 2023 as a plugin, broadly released to Plus users July 2023), it ran Python in a firewalled, network-disabled sandbox with an ephemeral filesystem — and users immediately probed it, listing installed packages and exploring the container from inside. The sandbox held precisely because it assumed hostile code from day one.

### Checkpoint
1. Why is prompt injection a reason to sandbox even a "trusted" model's code?
2. Which threats do rlimits address, and which do they not?
3. Why should a code sandbox's network access be denied by default?

## 06. Search Tools: Web, Docs, and Grep

**MOTTO:** An agent that can search doesn't need to know everything — it needs to know how to look.

### The Problem
Your model's weights froze months ago. It doesn't know today's library version, your internal wiki, or which file in this repo defines `PaymentProcessor`. Without search tools it guesses — fluently, confidently, wrongly. With them, "I don't know" becomes "give me a second."

### The Concept
Three search tools, three worlds, one shape (`query in → ranked snippets out`):

```
  web search   ──►  the internet     (fresh, noisy, slow, untrusted)
  docs search  ──►  your corpus      (curated, semantic or keyword)
  grep         ──►  the codebase     (exact, instant, regex-precise)
```

The librarian analogy: web search is asking the whole city, docs search is asking your own library, grep is `Ctrl+F` on a book you're holding. Good agents pick the right one — grep for "where is this function defined," docs for "what's our retry policy," web for "what changed in Python 3.13."

### Build It
1. Grep tool: shell out to `ripgrep` (or Python `re` over files); return `file:line: match` lines, capped at ~50 results.
2. Docs tool: keyword index (or embeddings — Phase 5) over your corpus; return top-k snippets with source paths.
3. Web tool: hit a search API, return titles + URLs + snippets — then let the model choose which URL to fetch (lesson 08).
4. Critical detail: truncate. A 200-result grep dump destroys the context window. Return counts + top hits + "refine your pattern."

```python
def grep_tool(pattern, path=".", max_results=50):
    out = subprocess.run(["rg", "-n", "--max-count", "5", pattern, path],
                         capture_output=True, text=True, timeout=15)
    lines = out.stdout.splitlines()
    body = "\n".join(lines[:max_results])
    more = f"\n... {len(lines)-max_results} more (refine pattern)" if len(lines) > max_results else ""
    return body + more if lines else "No matches."
```

### Use It
| Tool | Backed by | Tradeoff |
|---|---|---|
| Web search | Tavily, Brave, Exa, Bing APIs | Fresh but injectable (untrusted text!) |
| Docs search | BM25 / vector index | Setup cost; only as good as the corpus |
| Grep | ripgrep | Exact-match only; misses synonyms |

Treat all web results as untrusted input — a search result page can contain instructions aimed at your agent.

### War Story
The WebGPT paper (OpenAI, December 2021) fine-tuned GPT-3 to answer questions by operating a text-based browser — searching, clicking, quoting sources — and found its long-form answers were preferred to human demonstrators' more than half the time. It was an early, verifiable demonstration that "model + search tool" beats "bigger model alone" for factual, current questions.

### Checkpoint
1. When should an agent grep instead of doing semantic search over the same codebase?
2. Why is truncating search results a correctness issue, not just a cost issue?
3. Why must web search results be treated as untrusted input?

## 07. File Tools: Read, Write, Edit Safely

**MOTTO:** Give the agent a filesystem, not *the* filesystem.

### The Problem
Coding agents live and die by file operations. Naive implementations fail in colorful ways: the agent overwrites a 2,000-line file with a 40-line "summary" of it, edits a file it never read, path-traverses to `../../.ssh/`, or clobbers your uncommitted changes. Files are state, and state loss is the unforgivable agent sin.

### The Concept
Three primitives with guardrails, plus a fence:

```
  ┌── workspace root (jail) ─────────────────────┐
  │  read(path, offset, limit)  → numbered lines │
  │  write(path, content)       → whole file     │
  │  edit(path, old, new)       → exact-match    │
  │                                surgical swap │
  └── everything outside: ACCESS DENIED ─────────┘
```

The key insight behind `edit`: don't ask the model to reproduce a whole file (it will drop lines); ask it for an *anchored diff* — "replace exactly this snippet with that snippet." If the anchor isn't found, or is found twice, refuse. That turns silent corruption into a loud, fixable error.

### Build It
1. Path jail: resolve every path and verify it's under the workspace root.
2. Read-before-edit: track read files per session; refuse to edit a file the agent hasn't read (it would be editing from imagination).
3. Exact-match edit: require `old` to appear exactly once; error otherwise.

```python
from pathlib import Path
ROOT = Path("/workspace").resolve()

def safe(p):
    full = (ROOT / p).resolve()
    if not full.is_relative_to(ROOT):
        raise ValueError(f"Path escapes workspace: {p}")
    return full

def edit(path, old, new):
    f = safe(path); text = f.read_text()
    n = text.count(old)
    if n == 0: return "ERROR: old_string not found. Re-read the file."
    if n > 1:  return f"ERROR: old_string appears {n} times. Add context to make it unique."
    f.write_text(text.replace(old, new, 1)); return "OK"
```

4. Safety nets: back up before overwrite, or better — require a git repo and let commits be your undo.

### Use It
| Guardrail | Prevents |
|---|---|
| Path jail | Reading secrets, writing outside project |
| Read-before-edit | Editing hallucinated file contents |
| Unique-anchor edits | Silent wrong-location patches |
| Git as undo | Irreversible destruction |
| Numbered-line reads | Off-by-N confusion in edits |

Claude Code, Aider, and Cursor all converged on variants of anchored/search-replace edits over whole-file rewrites — independently, because whole-file rewrites truncate.

### War Story
Aider, the open-source coding agent, publicly benchmarked edit formats and found models are dramatically more reliable emitting search/replace-style diff blocks than regenerating whole files — its leaderboard tracks "correct edit format" as its own metric precisely because malformed edits, not bad reasoning, were a dominant failure mode. Tool format *is* capability.

### Checkpoint
1. Why is "replace exactly-once-matching snippet" safer than "write the whole updated file"?
2. What bug does the read-before-edit rule prevent?
3. How does a path jail differ from running the agent as a low-privilege user, and why might you want both?

## 08. Browser and HTTP Tools

**MOTTO:** The web is the biggest API ever built — and the most hostile input your agent will ever eat.

### The Problem
Search gives you URLs; now the agent needs contents. Raw `requests.get` returns 400 KB of HTML where 2 KB of it is the article — nav bars, cookie banners, and script tags devour your context window. And some pages don't exist until JavaScript runs. Meanwhile, any page you fetch might contain text written to manipulate your agent.

### The Concept
Two tiers, escalate only when needed:

```
  HTTP fetch (requests + HTML→text)      Headless browser (Playwright)
  ─ fast, cheap, stateless               ─ runs JS, clicks, types, screenshots
  ─ fails on JS-rendered SPAs            ─ slow, heavy, stateful, fragile
        │                                       │
        └──── try this first ────► escalate ────┘
```

The librarian vs. the intern: an HTTP fetch is asking a librarian to photocopy a page; a browser session is sending an intern to physically operate the website. Send the intern only when the photocopier fails.

### Build It
1. Fetch with a timeout, a size cap, and a real User-Agent; verify content-type.
2. Strip HTML to readable text: drop `script`/`style`/`nav`, keep headings, paragraphs, links.
3. Truncate to a token budget with a "content continues" marker and offset-based pagination.

```python
from html.parser import HTMLParser

class TextExtract(HTMLParser):
    skip = {"script", "style", "nav", "footer"}
    def __init__(self): super().__init__(); self.out = []; self.depth = 0
    def handle_starttag(self, tag, attrs): self.depth += tag in self.skip
    def handle_endtag(self, tag): self.depth -= tag in self.skip
    def handle_data(self, data):
        if not self.depth and data.strip(): self.out.append(data.strip())
```

4. Browser tier: expose *actions* (`goto`, `click(selector)`, `type`, `read_page`), not raw Playwright — the model operates a remote control, your code owns the browser object.
5. Security: block internal IP ranges (SSRF), never auto-execute instructions found in page text.

### Use It
| Tool | Good for | Cost |
|---|---|---|
| `requests`/`httpx` + readability | Articles, docs, APIs | Milliseconds |
| Jina Reader / Firecrawl-style APIs | Clean markdown from any URL | Per-call fee |
| Playwright / Puppeteer | SPAs, logins, forms | Seconds + RAM |
| Accessibility-tree browsing | Agent-friendly page structure | Playwright + parsing |

### War Story
ChatGPT plugins launched in March 2023 as "the app store moment" — Browsing, Code Interpreter, and third-party plugins via OpenAPI manifests. Within months the browsing plugin was briefly pulled (July 2023) after users bypassed paywalls with it, and plugins were deprecated in 2024 in favor of GPTs and built-in tools. Lesson: web-facing tools attract abuse cases their designers never listed.

### Checkpoint
1. Why fetch-then-strip instead of passing raw HTML to the model?
2. What is SSRF, and why does an HTTP tool need an IP blocklist?
3. When does a headless browser justify its cost over plain HTTP fetch?

## 09. The Tool Router: Dispatch Without Spaghetti

**MOTTO:** Every tool call passes through one door — validation, execution, and logging live at that door.

### The Problem
Your agent has 12 tools and your loop has become an `if name == "get_weather": ... elif name == "search": ...` ladder. Adding a tool means editing four places. Validation is copy-pasted, logging is inconsistent, and one tool's typo crashes another's dispatch. This is how agent codebases rot.

### The Concept
A tool router is a registry plus a pipeline — the same pattern as a web framework's URL router:

```
  tool_call ──► [lookup] ──► [validate args] ──► [policy check] ──► [execute] ──► [format result]
                   │              │                   │                 │
                unknown        schema err          denied            exception
                   └──────────────┴─── all become tool-result errors ──┘
```

Tools register themselves; the router owns everything cross-cutting: argument validation, permissions, timeouts, logging, result truncation. The loop code never mentions a specific tool by name.

### Build It
1. Registry: dict of name → `(fn, schema)`. A decorator populates it.
2. Dispatch: look up, validate required args and types against the schema, call, catch, format.
3. Cross-cutting hooks in ONE place: timing, truncation, audit log.

```python
REGISTRY = {}

def tool(fn):
    REGISTRY[fn.__name__] = {"fn": fn, "schema": schema_from(fn)}
    return fn

def dispatch(call):
    entry = REGISTRY.get(call.name)
    if not entry:
        return f"ERROR: unknown tool '{call.name}'. Available: {list(REGISTRY)}"
    missing = [p for p in entry["schema"]["parameters"]["required"] if p not in call.args]
    if missing:
        return f"ERROR: missing required args {missing}"
    try:
        result = entry["fn"](**call.args)
        return str(result)[:8000]          # truncation lives HERE, once
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"
```

4. The unknown-tool error listing available tools is deliberate — models recover from hallucinated tool names when told what actually exists.

### Use It
| Pattern | Where you've seen it |
|---|---|
| Decorator registry | LangChain `@tool`, most Python frameworks |
| Schema-validated dispatch | Pydantic-based agents |
| Middleware pipeline | MCP servers, enterprise gateways |
| Central truncation/logging | Every production agent, eventually |

The test of a good router: adding tool #13 touches exactly one file and zero lines of loop code.

### War Story
This is the exact problem the Model Context Protocol (announced by Anthropic, November 2024) standardizes at the ecosystem level: instead of every app hand-rolling M×N integrations between models and tools, tools live behind a common registry-and-dispatch protocol. MCP is a tool router with a wire format — the pattern you just built, promoted to an open standard.

### Checkpoint
1. What cross-cutting concerns belong in the router rather than in individual tools?
2. Why return "unknown tool, here's what exists" instead of raising an exception?
3. How does a registry-with-decorator design keep the agent loop tool-agnostic?

## 10. Dynamic Tool Loading and Tool Search

**MOTTO:** Don't hand the model a 40-page menu — hand it a waiter who knows the menu.

### The Problem
Every tool schema you register costs prompt tokens on *every single turn* — hundreds of tokens each, forever. Worse, accuracy degrades: with 50+ similar tools in context, models confuse `search_orders` with `search_order_items`, pick plausible-but-wrong tools, and burn turns. Connect three MCP servers and you can have 100 tools eating tens of thousands of tokens before the user says hello.

### The Concept
Treat tools like a library treats books — a catalog in front, the stacks in back:

```
  Static loading:                   Dynamic loading:
  ┌────────────────────┐            ┌────────────────────┐
  │ all 80 schemas,    │            │ 5 core schemas     │
  │ every turn,        │            │ + search_tools()   │  ← the meta-tool
  │ ~25k tokens        │            │ ~2k tokens         │
  └────────────────────┘            └────────────────────┘
                                      model: search_tools("send slack message")
                                      → schema for slack_send loaded into context
                                      → model calls slack_send
```

The model gets a small always-on core plus a *meta-tool* that searches the full catalog by keyword or similarity and injects matching schemas on demand. Discovery becomes a tool call.

### Build It
1. Split tools: `core` (always in context) vs `deferred` (name + short description in a searchable index).
2. Implement `search_tools(query)`: rank the deferred catalog (keyword or embedding match), return the top schemas, and add them to the active set for subsequent turns.
3. Optionally evict: drop loaded-but-unused schemas after N turns to reclaim tokens.

```python
def search_tools(query, catalog, active, k=3):
    scored = sorted(catalog.values(),
                    key=lambda t: overlap(query, t["name"] + " " + t["description"]),
                    reverse=True)[:k]
    for t in scored:
        active[t["name"]] = t          # now callable next turn
    return "Loaded: " + ", ".join(t["name"] for t in scored)
```

4. The two-phase dance matters: turn N discovers, turn N+1 calls. Your router must accept calls only to *active* tools and suggest `search_tools` for the rest.

### Use It
| Approach | Tradeoff |
|---|---|
| All tools static | Simple; fine under ~15 tools |
| Grouped namespaces (`slack.*`) | Cheap disambiguation, still all loaded |
| Tool search / deferred loading | Scales to hundreds; adds a discovery turn |
| Code-execution-as-tools | Model writes code against APIs; max flexibility, max sandbox burden |

Anthropic's Tool Search Tool (2025) reported large token savings and accuracy gains on many-tool benchmarks with exactly this defer-and-discover design.

### War Story
Anthropic's engineering write-ups on MCP at scale describe the problem bluntly: agents wired to multiple MCP servers could see hundreds of tool definitions consuming tens of thousands of tokens before any work began, and they reported that moving from loading all tools up front to on-demand discovery (tool search / code execution with MCP, 2025) cut that overhead dramatically. The many-tool problem is a context-budget problem wearing a tools costume.

### Checkpoint
1. What are the *two* costs of registering many static tools (not just the token one)?
2. Why does dynamic loading require two turns before a deferred tool actually runs?
3. When is plain static loading still the right call?

## 11. Designing Tools Agents Actually Use Well

**MOTTO:** Tools are prompts — every name, description, and parameter is instruction text the model reads.

### The Problem
Your tool works perfectly in unit tests and the agent still fumbles it: calls `search` when it should call `lookup`, passes a city name where an airport code goes, or ignores the tool entirely. You blame the model. But the model only knows what your schema *says* — and your schema says `"q": string. Description: the query`.

### The Concept
The model experiences your tool exactly the way a new hire experiences an internal API with only its docs — no source, no Slack, no tribal knowledge. Tool design is therefore prompt engineering with a type system:

```
  BAD                                GOOD
  name: "proc_data"                  name: "search_customer_orders"
  desc: "processes data"             desc: "Search a customer's order history
  args: {d: string}                   by keyword. Returns up to 10 orders as
                                      JSON. Use get_order_details for line
                                      items. Example: query='refund', last_90d"
```

Rules of thumb: names state verb + object; descriptions say what it returns, when to use it, when NOT to (point to the sibling tool); enums beat free strings; and granularity should match *intent* — one `book_meeting(person, time)` beats four calendar micro-calls the model must choreograph.

### Build It
1. Name for disambiguation: if two tools could be confused, the difference belongs in both names.
2. Description = contract + routing hint + example. Three sentences minimum for non-trivial tools.
3. Constrain arguments: enums, formats ("ISO 8601"), defaults. Every constraint you encode is a mistake the model can't make.
4. Return *for the model*: structured, compact, labeled — `{"orders": [...], "total": 4, "hint": "use get_order_details(id) for line items"}` beats a raw DB dump.
5. Close the loop: run the agent, read transcripts, find where it fumbled, fix the *schema text*, rerun. Evaluate tools like you evaluate prompts — because they are prompts.

### Use It
| Smell | Fix |
|---|---|
| Model picks wrong sibling tool | Contrastive descriptions ("use X for..., use THIS for...") |
| Malformed argument values | Enum / format spec / example in description |
| Model chains 4 calls for 1 intent | Consolidate into one intent-level tool |
| Model ignores a useful tool | Description doesn't say *when* to use it |
| Huge raw results | Return summaries + IDs; add a detail tool |

### War Story
Anthropic's "Writing tools for agents" engineering post (2025) describes improving tool performance substantially without touching the tools' code — by rewriting names, descriptions, and output formats, then measuring on agent evals; they even used Claude to optimize its own tool descriptions. The implementation was never the bottleneck. The prose was.

### Checkpoint
1. In what sense are tool definitions "prompts," and what follows from that for how you iterate on them?
2. Why do enums and format constraints reduce agent errors more than better instructions in the system prompt?
3. What signals in an agent transcript tell you a tool's *granularity* is wrong?

## 12. Build a Tool-Using Agent From Scratch

**MOTTO:** If you can't build the loop in 100 lines, you don't understand the loop yet.

### The Problem
You've now seen schemas, choice, parallelism, errors, routing, and design — as parts. Frameworks bundle them so thoroughly you can ship an agent without ever seeing the loop. Then it misbehaves, and you're debugging a black box. Time to build the whole thing with no framework and a mock LLM, so every moving part is yours.

### The Concept
The complete anatomy, nothing hidden:

```
  ┌────────────────────────────────────────────────┐
  │  messages = [system, user]                     │
  │  loop:                                         │
  │    response = llm(messages, tools)             │
  │    if response.tool_calls:                     │
  │        results = [dispatch(c) for c in calls]  │
  │        messages += [assistant_msg, *results]   │
  │    else:                                       │
  │        return response.text      ← done        │
  └────────────────────────────────────────────────┘
```

A mock LLM (scripted responses) makes the loop testable and deterministic — the same trick you'll use forever in agent unit tests.

### Build It
```python
import json
from dataclasses import dataclass, field

@dataclass
class ToolCall:
    id: str; name: str; args: dict

REGISTRY = {}
def tool(fn): REGISTRY[fn.__name__] = fn; return fn

@tool
def calculator(expression: str) -> str:
    """Evaluate an arithmetic expression, e.g. '17*23'."""
    allowed = set("0123456789+-*/(). ")
    if not set(expression) <= allowed: return "ERROR: arithmetic only"
    return str(eval(expression))          # sandboxed by the whitelist

@tool
def lookup_capital(country: str) -> str:
    """Return the capital city of a country."""
    return {"france": "Paris", "japan": "Tokyo"}.get(country.lower(), "ERROR: unknown country")

def dispatch(call):
    fn = REGISTRY.get(call.name)
    if not fn: return f"ERROR: unknown tool {call.name}"
    try: return fn(**call.args)
    except Exception as e: return f"ERROR: {e}"

class MockLLM:                             # scripted brain: swap for a real API later
    def __init__(self, script): self.script = iter(script)
    def __call__(self, messages, tools): return next(self.script)

llm = MockLLM([
    {"tool_calls": [ToolCall("1", "lookup_capital", {"country": "France"})]},
    {"tool_calls": [ToolCall("2", "calculator", {"expression": "17*23"})]},
    {"text": "The capital of France is Paris, and 17*23 = 391."},
])

def run_agent(user_msg, llm, max_turns=10):
    messages = [{"role": "system", "content": "Use tools when helpful."},
                {"role": "user", "content": user_msg}]
    for _ in range(max_turns):
        r = llm(messages, REGISTRY)
        if "tool_calls" in r:
            messages.append({"role": "assistant", "tool_calls": r["tool_calls"]})
            for c in r["tool_calls"]:
                messages.append({"role": "tool", "tool_call_id": c.id,
                                 "content": dispatch(c)})
        else:
            return r["text"]
    return "ERROR: max turns exceeded"

print(run_agent("Capital of France, and what's 17*23?", llm))
```

Run it. Then break it on purpose: script a call to a nonexistent tool, a bad argument, an infinite tool-call script — and watch your error handling and `max_turns` earn their keep.

### Use It
| Upgrade path | Replaces |
|---|---|
| Real API (OpenAI/Anthropic SDK) | `MockLLM` |
| `schema_from()` + JSON Schema | Bare registry |
| `asyncio.gather` | Sequential dispatch loop |
| Persisted `messages` | In-memory list (→ Phase 4) |

The scripted-LLM test harness stays. Deterministic agent tests are how production teams sleep at night.

### War Story
The virality of tiny from-scratch implementations — Simon Willison's ~100-line Python agent posts, countless "an agent is just a loop" write-ups from 2024–2025 — made a once-contrarian point mainstream: production agents like Claude Code are, at their core, a while-loop over an LLM call and a tool dispatcher. The value is in the tools, the prompts, and the guardrails. You've now built all three.

### Checkpoint
1. Why does a mock LLM make agent behavior *testable* in a way real API calls can't?
2. What two safety mechanisms in this loop prevent it from running forever or crashing on bad tool calls?
3. Which single components would you swap to turn this mock agent into a real one?
