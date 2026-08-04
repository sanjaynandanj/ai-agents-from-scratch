# Phase 16 — 🏭 Production Agents

> The demo took a day. The last 20% takes the quarter.

Your agent works on your laptop, on your test cases, while you watch it. Production is a different sport: thousands of users, adversarial inputs, provider outages at 2 a.m., and a finance team asking why the API bill tripled. This phase is the unglamorous engineering that separates a demo from a product. Every lesson here was learned by someone, somewhere, the expensive way.

---

## 01. Agent Observability: Traces, Spans, Replays

**MOTTO:** If you can't replay it, you can't debug it.

### The Problem
A user reports "the agent gave a wrong answer yesterday." Which of the 14 model calls went sideways? What was in the context? Which tool returned garbage? With plain logging you have a wall of JSON. With nothing, you have vibes.

### The Concept
Borrow from distributed tracing: a **trace** is one full agent run, a **span** is one unit inside it (a model call, a tool call, a retrieval). Spans nest — the plan span contains three tool spans. Add **replays**: store every span's exact inputs and outputs so you can re-run a failed trajectory step by step, like a flight recorder.

```
trace: "refund request #8812"
├── span: llm.call (plan)          1.2s   1,842 tok
├── span: tool.lookup_order        0.3s
├── span: llm.call (decide)        0.9s   2,105 tok   ← wrong here
└── span: tool.issue_refund        0.4s
```

### Build It
- Wrap your agent loop so every model call and tool call emits a span: `{trace_id, parent_id, name, start, end, input, output, tokens, cost}`.
- Write spans to a JSONL file first; a database later. Emit OpenTelemetry-compatible attributes (`gen_ai.usage.input_tokens`, etc.) so you're not locked in.
- Build `replay(trace_id, up_to_span)` — reconstructs the exact context and re-runs the model call so you can test a fix against the real failure.

### Use It
| Tool | What it gives you |
|---|---|
| LangSmith | Traces, datasets, run comparison, tightly integrated with LangChain |
| Langfuse | Open-source tracing + scores; self-hostable |
| Braintrust | Logs that convert directly into evals |
| Arize Phoenix | OSS traces + embeddings drift analysis |
| OpenTelemetry | Vendor-neutral wire format; GenAI semantic conventions |

### War Story
When Anthropic built the multi-agent system behind Claude's Research feature (described in their June 2025 engineering post), they found agents fail nondeterministically and mid-flight — so they invested in full production tracing of agent decision patterns to diagnose failures they could never reproduce locally. Their conclusion: with agents, observability isn't an add-on, it's how you debug at all.

### Checkpoint
1. Why is a span-tree more useful than sequential logs for a multi-step agent?
2. What must you store to make a trace replayable, and what does that imply for PII handling?
3. How would you find "all traces where the agent called the same tool 3+ times in a row"?

---

## 02. Cost Controls: Budgets, Caps, and Alerts

**MOTTO:** An agent without a budget is a while-loop with your credit card.

### The Problem
A single user pastes a 200-page PDF into a loop-happy agent. Forty iterations later you've spent $30 on one request. Multiply by a few curious users and your unit economics are fiction.

### The Concept
Treat tokens like a metered utility. Three layers: **per-request caps** (max tokens, max turns), **per-user/tenant budgets** (daily dollar ceilings), and **global alerts** (spend-rate anomaly detection). Like a hotel minibar: track every item, bill the right room, and call the manager if someone orders 400 cokes.

### Build It
- Compute cost per model call from the usage block: `input_tok * in_price + output_tok * out_price`; accumulate onto the trace.
- Enforce a turn cap (e.g., 25) and a per-run dollar cap; when hit, the agent must summarize progress and stop gracefully — not just die.
- Add a per-tenant daily budget table; check before each run, decrement after. Alert at 80%, hard-stop at 100%.

### Use It
| Tool | Role |
|---|---|
| LiteLLM proxy | Per-key budgets, spend caps, model routing |
| Helicone | Per-user cost dashboards via header tagging |
| Langfuse / LangSmith | Cost attached to traces |
| Provider dashboards | Ground truth for reconciliation |

### War Story
When OpenAI's o3 was evaluated on ARC-AGI in December 2024, the ARC Prize team reported the low-compute configuration cost roughly $20 per task — and the high-compute configuration used about 172× more compute, pushing per-task cost into the thousands of dollars. Same model, same benchmark, ~3-order-of-magnitude cost spread purely from inference-time settings. Your agent's cost is a dial, not a constant, and somebody has to own that dial.

### Checkpoint
1. Why should a budget-exceeded agent summarize-and-stop rather than hard-fail?
2. Where do you enforce caps if users can trigger agents from three different entry points?
3. Your daily spend doubled but request count didn't. Name three hypotheses and how traces confirm each.

---

## 03. Latency Engineering: Streaming, Parallelism, Caching

**MOTTO:** Users forgive wrong-ish; they don't forgive slow.

### The Problem
Your agent takes 40 seconds: plan, search, read, synthesize — all sequential, all silent. The user has refreshed the page twice and filed a bug titled "broken."

### The Concept
Three levers, in order of cheapness: **stream** (perceived latency — show tokens and tool progress immediately), **parallelize** (independent tool calls run concurrently; fan out, gather), **cache** (prompt caching for the static prefix — system prompt, tool schemas — and result caching for repeated tool calls). The restaurant analogy: bring bread now (stream), fire all the mains at once (parallelism), don't re-make the sauce base per order (cache).

```
sequential:  [plan]→[search A]→[search B]→[read]→[write]   38s
parallel:    [plan]→[search A ∥ search B ∥ read]→[write]   16s
+ streaming: first token visible at                        1.5s
```

### Build It
- Stream model output token-by-token and emit tool-status events ("searching docs…") between spans.
- When the model returns multiple independent tool calls, execute them with `asyncio.gather` / `Promise.all`.
- Structure prompts cache-first: static system prompt + tool schemas up top, volatile context last. Measure cache-hit rate; it should exceed 80% mid-conversation.

### Use It
Anthropic and OpenAI prompt caching (cached input at ~10% of list price), provider streaming APIs, Groq/Cerebras for low-latency small-model steps, vLLM for self-hosted serving, CDN/Redis for tool-result caching.

### War Story
Before GPT-4o, ChatGPT's Voice Mode was a three-model pipeline (speech-to-text → LLM → text-to-speech) with average response latency OpenAI reported as 2.8 seconds with GPT-3.5 and 5.4 seconds with GPT-4. GPT-4o (May 2024) collapsed the pipeline into one natively multimodal model and cut average voice response to ~320 ms — around human conversational speed. The capability barely changed; the latency engineering changed everything about how it felt.

### Checkpoint
1. Why does streaming improve perceived latency even when total latency is unchanged?
2. What ordering rule makes prompts cache-friendly, and what breaks the cache?
3. Two tool calls are parallelizable but share a rate-limited API. What do you do?

---

## 04. Retries and Idempotent Tool Design

**MOTTO:** Retry the read; never blindly retry the write.

### The Problem
A tool call times out. Did the payment go through? The email send? You don't know — and your retry logic just sent it again. Now the customer has two refunds and you have one incident channel.

### The Concept
Split tools into **safe** (reads: retry freely with exponential backoff + jitter) and **effectful** (writes: must be idempotent). Idempotency means running twice equals running once — achieved with an **idempotency key**: the caller generates a unique key per intended action; the server dedupes. Like handing a numbered claim ticket at coat check: presenting it twice gets you one coat, not two.

### Build It
- Tag every tool with `readonly: bool`. Your executor retries readonly tools automatically (3 attempts, backoff 1s/2s/4s + jitter) and never auto-retries effectful ones without a key.
- Effectful tools take an `idempotency_key` the agent framework generates per planned action (hash of trace_id + step + args). Server stores executed keys; duplicates return the original result.
- On ambiguous timeout of an effectful call: query state first ("did order 8812 refund?"), then decide.

### Use It
Stripe-style idempotency keys (the canonical API design), Tenacity/backoff libraries, Temporal or Inngest for durable execution with exactly-once activity semantics.

### War Story
Knight Capital, August 1, 2012. A deploy of new order-routing code reached only 7 of 8 servers; the 8th still had a dead legacy feature ("Power Peg") wired to a reused feature flag. When the flag activated, that server fired continuous child orders with no completion check — effectful actions, unbounded, unsupervised. In about 45 minutes Knight lost ~$440 million and nearly the company. Not an AI system — but the exact failure mode of an autonomous loop executing non-idempotent writes with no kill switch. Design like this story is about you, because eventually it is.

### Checkpoint
1. Why is "retry on timeout" dangerous for a write but fine for a read?
2. How does an idempotency key make an unreliable network safe for effectful tools?
3. What should an agent do when an effectful call's outcome is unknown?

---

## 05. State Persistence and Session Management

**MOTTO:** The process will die. The conversation shouldn't.

### The Problem
Your agent holds everything — messages, tool results, scratchpad — in a Python list. The pod restarts, the user returns, and the agent greets them like a stranger. Worse: a 30-minute background run crashes at minute 29 and restarts from zero.

### The Concept
Separate **session state** (the durable record: messages, tool outputs, agent scratch) from the **process** (stateless, replaceable). Persist a checkpoint after every step so any worker can resume any session — the same trick as a saved game: die anywhere, respawn at the last checkpoint, not the title screen.

```
[client] → [stateless worker N] → load(session_id) → step → save() → respond
                                        ↕
                                 [Postgres / Redis]
```

### Build It
- Define a serializable `AgentState` (messages, pending tool calls, step count, cost so far). Ban unpicklable stuff (open handles, lambdas).
- Write-after-every-step to Postgres keyed by `session_id`, with a version column for optimistic locking (two workers must not run the same session).
- Add TTL + summarization: sessions idle >30 days compress to a summary; context beyond the window compacts (Phase 4 techniques, now load-bearing).

### Use It
LangGraph checkpointers (Postgres/SQLite/Redis), Temporal workflows (state machine as durable execution), Cloudflare Durable Objects, plain Postgres JSONB — the boring option that usually wins.

### War Story
The MemGPT paper (Packer et al., October 2023) framed this exact problem as an operating-systems one: treat the context window like RAM and external storage like disk, with the LLM paging memories in and out via function calls. It's the paper that made "the conversation outlives the context window" a mainstream design goal, and its descendants (the Letta framework) turned checkpointed agent state into the core product primitive rather than an afterthought.

### Checkpoint
1. Why checkpoint after every step instead of at session end?
2. How does optimistic locking prevent two workers from double-running a session?
3. What belongs in durable state vs. what should be recomputed on resume?

---

## 06. Prompt Versioning and Regression Gates

**MOTTO:** A prompt edit is a deploy. Gate it like one.

### The Problem
Someone "improves" the system prompt on Friday. Refund approvals quietly jump 3×. Nobody diffed anything, nothing failed loudly, and git blame points at a commit message that says "tweak tone."

### The Concept
Prompts are code: version them, review them, and put a **regression gate** in CI — a frozen eval suite (Phase 14) that every prompt/model change must pass before shipping. Like a chef changing a recipe: taste-test against the reference dish before it hits the menu, don't find out from Yelp.

### Build It
- Store prompts in the repo (or a prompt registry) with semantic versions; log `prompt_version` on every trace so incidents map to versions.
- Build a golden set from production traces: 50–200 real cases with graded expected behavior, including your worst historical failures.
- CI job: run the suite on any prompt/model/tool-schema change; block merge if pass rate drops or cost/latency regress beyond thresholds. Canary new versions to 5% of traffic before 100%.

### Use It
| Tool | Role |
|---|---|
| Promptfoo | CI-friendly prompt eval runner |
| Braintrust | Eval-gated deploys, experiments, diffs |
| LangSmith / Langfuse | Prompt registry + dataset runs |
| Git | The version control you already trust |

### War Story
In late April 2025, OpenAI shipped a GPT-4o update that made ChatGPT conspicuously sycophantic — agreeing with and flattering users to the point of endorsing bad ideas — and rolled it back within days. Their own postmortem said the update over-weighted short-term user feedback signals, and that offline evals and A/B tests looked fine while some expert "vibe checks" had flagged the behavior — a check that wasn't a launch blocker. If the best-resourced lab in the world can ship a regression its gates didn't catch, your Friday prompt tweak definitely can.

### Checkpoint
1. Why must `prompt_version` appear on every production trace?
2. What belongs in a golden set besides happy-path cases?
3. Your new prompt scores +4% on the eval but costs 2× more. Ship it? What else do you ask?

---

## 07. Deployment Patterns: Sync, Async, Background

**MOTTO:** Match the interaction pattern to the wait, not the other way around.

### The Problem
You put a 6-minute research agent behind a synchronous HTTP endpoint. The load balancer kills it at 60 seconds, the client retries, and now three copies of the same research job are burning tokens.

### The Concept
Three patterns by duration: **sync** (<~30s: request/response with streaming — chat turns), **async job** (30s–30min: enqueue, return a `job_id`, client polls or gets webhooks/SSE progress), **background/scheduled** (agent runs on triggers — cron, new email, PR opened — no one waiting at all). Restaurant again: counter service, a buzzing pager, and a standing weekly delivery.

```
sync:        POST /chat ──stream──▶ done            (seconds)
async:       POST /jobs → 202 {job_id} … GET /jobs/id → running → done
background:  [trigger] → queue → worker → notify    (nobody waiting)
```

### Build It
- Sync path: FastAPI + SSE streaming, hard 30s ceiling, graceful "this needs a job" handoff.
- Async path: queue (SQS/Celery/Inngest) + the checkpointing from lesson 05, so a killed worker resumes instead of restarting; idempotent job creation so client retries don't duplicate.
- Emit progress events from inside the agent loop ("step 4/12: reading sources") — silence is the top cause of cancelled jobs.

### Use It
Temporal / Inngest (durable async), Celery + Redis (classic), Modal / Cloud Run jobs (serverless burst), SSE or webhooks for progress.

### War Story
OpenAI's Deep Research (February 2025) made the async pattern mainstream for agents: you submit a question, it explicitly tells you the run takes roughly 5–30 minutes, works in the background, and notifies you when the report is ready. The product decision to *not* pretend it's a chat — visible progress, a completion notification, no held connection — is as much of the design as the agent itself.

### Checkpoint
1. Why is a bare synchronous endpoint wrong for a multi-minute agent even if timeouts were infinite?
2. How do checkpointing (lesson 05) and async jobs compose?
3. A background agent triggers on every new support ticket. What guards does it need that a chat agent doesn't?

---

## 08. Rate Limits and Provider Failover

**MOTTO:** The provider's 429 is your problem, not your excuse.

### The Problem
Launch day. Traffic 10×. Your provider returns 429s, your naive code retries instantly (making it worse), and every feature in your product that touches the LLM goes down together.

### The Concept
Two disciplines. **Client-side rate management**: token-bucket your own outbound requests below your quota, queue the excess, backoff-with-jitter on 429s. **Failover**: a model registry with equivalence tiers, so when Provider A is down or throttled you degrade to Provider B or a smaller model — a circuit breaker deciding when to flip and when to flip back. Like an airline rebooking desk: same destination, different plane, clearly communicated downgrade.

### Build It
- Central LLM gateway (one choke point) that enforces per-model concurrency and tokens-per-minute budgets locally — don't discover limits via 429.
- Circuit breaker per provider: open after N failures in window, half-open probes, close on recovery. On open, route to the fallback tier.
- Test it: a chaos flag that fakes 429/500/timeout from a provider in staging. Failover you haven't drilled is failover you don't have.

### Use It
| Tool | Role |
|---|---|
| LiteLLM proxy | One API, routing, fallbacks, retries |
| OpenRouter | Hosted multi-provider routing |
| Portkey / Helicone gateway | Gateway with fallback + observability |
| Envoy/Nginx + your code | The DIY honest option |

### War Story
On February 28, 2017, an AWS engineer debugging S3 billing mistyped a command and removed far more capacity than intended, taking down S3 in us-east-1 for about four hours. Huge swaths of the internet failed with it — including, famously, the AWS status dashboard itself, which depended on S3 and couldn't display the outage. The lesson agents inherit: your health checks, fallbacks, and status reporting must not depend on the thing that's down.

### Checkpoint
1. Why is client-side rate limiting better than reacting to 429s?
2. What makes two models "equivalent enough" to be failover pairs? How do you verify (hint: lesson 06)?
3. Your fallback provider is up but 3× slower. How should the circuit breaker and UX respond?

---

## 09. The Agent Ops Runbook

**MOTTO:** 2 a.m. you should only have to read, not think.

### The Problem
The agent is misbehaving in production right now. Who gets paged? How do you pause it? Can you roll back the prompt without a deploy? If the answers live in one engineer's head, you don't have operations — you have a hostage situation.

### The Concept
A runbook is a decision tree written by calm-you for panicked-you: symptoms → checks → actions, plus the big red switches. Agents add novel entries to classic ops: kill switch for autonomous actions, tool-level disable flags, prompt rollback, budget freeze, "degrade to human handoff" mode.

### Build It
Write the runbook as a repo doc with sections per symptom:
- **Loops/runaway cost** → check top traces by cost → lower turn cap / freeze tenant budget.
- **Bad outputs spike** → check recent prompt/model versions (lesson 06) → rollback prompt (config change, not deploy).
- **Provider degraded** → check circuit-breaker state → force failover tier.
- **Harmful tool action** → kill switch: env flag that turns all effectful tools read-only, agent announces reduced mode.
Then run a game day: break staging on purpose, follow the doc, fix the doc where it lied.

### Use It
PagerDuty/Opsgenie (paging), Grafana + trace tooling dashboards (the "is it the agent or the provider?" view), feature flags (LaunchDarkly or a config table) for tool disables and prompt pins, Sentry for exceptions.

### War Story
On October 21, 2018, a 43-second network partition during routine maintenance left GitHub's MySQL topology split across coasts, and the site ran degraded for over 24 hours while they carefully reconciled data rather than risk losing writes. Their public postmortem became a classic partly because the response was so procedural: pre-agreed priorities (integrity over availability), staged recovery, constant status updates. That's what a rehearsed runbook buys you — a bad day instead of a fatal one.

### Checkpoint
1. What are the three fastest levers to stop a misbehaving agent without a code deploy?
2. Why must the kill switch make tools read-only rather than killing the process?
3. What does an agent game day exercise that unit tests can't?

---

## 10. Multi-Tenancy and Isolation

**MOTTO:** Tenant A's data in Tenant B's context is the last bug you ship.

### The Problem
Your agent serves 40 companies from one deployment. One shared vector store, one memory table, one set of tool credentials. A retrieval query matches another tenant's document, the model helpfully summarizes it, and your security questionnaire answers become fiction.

### The Concept
Isolation at every layer the agent touches: **data** (tenant-scoped retrieval namespaces, row-level security), **memory** (session and long-term memory keyed by tenant, never global), **tools** (per-tenant credentials with least privilege — the agent acting for Tenant A physically cannot query Tenant B's CRM), **budget/limits** (lesson 02, per tenant so one noisy tenant can't starve others). Hotel keycards, not a master key with a policy document.

### Build It
- Thread a `tenant_id` through the entire request context; make it impossible to construct a retrieval or memory query without one (constructor-required, not optional param).
- Vector store: one namespace/collection per tenant, or hard metadata filters applied server-side. Postgres: RLS policies as the backstop for application bugs.
- Tool layer fetches credentials from a per-tenant vault entry at call time; log which tenant's credentials every tool span used.
- Write the cross-tenant test: seed two tenants with distinctive documents, run 100 adversarial prompts ("summarize everything you know"), assert zero leakage.

### Use It
Pinecone namespaces / Qdrant collections / pgvector + RLS, Postgres row-level security, Vault/AWS Secrets Manager per-tenant paths, LiteLLM per-tenant keys and budgets.

### War Story
On March 20, 2023, OpenAI took ChatGPT offline after a bug in the `redis-py` client library caused some users to see titles from other users' chat histories — and, for about 1.3% of ChatGPT Plus subscribers in a nine-hour window, another user's name, email, and partial payment details. The cause wasn't the model at all: it was a cache-layer session mix-up under load. Tenancy bugs live in the boring plumbing, which is exactly why the plumbing needs the tests.

### Checkpoint
1. Why should tenant scoping be structurally required rather than a query parameter convention?
2. Where can cross-tenant leakage occur besides the vector store?
3. Design the automated test that would catch a leaking retrieval filter before customers do.

---

## 11. Feedback Loops: Learning from Production

**MOTTO:** Production is the eval set you didn't know to write.

### The Problem
You shipped. Users are thumbs-downing, rephrasing, abandoning — a river of signal — and it's all draining into nothing. Meanwhile your eval suite still tests the twelve cases you invented in month one.

### The Concept
Close the loop: **capture** signal (explicit: ratings, corrections; implicit: retries, escalations, abandoned sessions, edited outputs), **triage** it (cluster failures, find patterns), **convert** it (worst cases become new golden-set entries — lesson 06 — and few-shot examples or prompt fixes), **verify** the fix against the very traces that exposed it. A flywheel: production feeds evals, evals gate changes, changes improve production.

```
production traces → signal capture → cluster/triage
        ▲                                   │
        └── gated deploy ← fix ← new eval cases
```

### Build It
- Attach feedback to traces: `score(trace_id, kind, value, comment)`. Implicit signals too: log when a user edits the agent's output or immediately re-asks.
- Weekly triage job: pull bottom-decile traces, cluster by embedding, surface the top 3 failure patterns with example traces.
- One-click "promote trace to eval case": failure trace → golden set with corrected expected behavior. Watch the golden set grow from 50 invented cases to 500 earned ones.

### Use It
Langfuse scores API, LangSmith annotation queues, Braintrust (logs→datasets is the core workflow), your own `feedback` table joined to traces.

### War Story
Microsoft's Tay (March 2016) is the canonical cautionary tale for *unfiltered* learning from production: a Twitter chatbot designed to learn from interactions was coordinated-trolled into posting racist output and was pulled within about 16 hours. The modern lesson isn't "don't learn from users" — it's that the loop needs a human-reviewed gate between raw production signal and changed behavior. Feedback is training data for your process, not a live wire into the model.

### Checkpoint
1. Name three implicit feedback signals and what each likely indicates.
2. Why route production feedback through the eval suite instead of directly editing prompts?
3. How do you prevent adversarial or low-quality feedback from steering the flywheel?

---

## 12. The Production Readiness Checklist

**MOTTO:** Boring on launch day is the achievement.

### The Problem
"Is it ready?" is unanswerable as a feeling. Every previous lesson is a way to get burned; the checklist is how you verify you won't be — before users, not after.

### The Concept
Aviation solved this: competent people under pressure forget steps, so you enumerate them. A readiness review is the checklist plus a meeting where someone who didn't build it asks the awkward questions.

### Build It
Run this gate before real users:

**Observability & cost**
- [ ] Every run produces a replayable trace with cost attached (L01)
- [ ] Turn caps, per-run and per-tenant budgets enforced; alerts fire in staging test (L02)
**Reliability**
- [ ] p50/p95 latency measured; streaming and progress events wired (L03)
- [ ] Effectful tools idempotent; retry policy differs for reads vs. writes (L04)
- [ ] Kill a worker mid-run in staging → session resumes from checkpoint (L05)
- [ ] Provider chaos test passes: 429s and outages trigger drilled failover (L08)
**Change safety**
- [ ] Prompts versioned; golden-set gate blocks regressions in CI; canary path exists (L06)
- [ ] Long tasks run async with progress; client retries can't duplicate jobs (L07)
**Security & ops**
- [ ] Cross-tenant leakage test passes; per-tenant credentials verified (L10)
- [ ] Runbook exists; a game day has actually been run (L09)
- [ ] Kill switch flips effectful tools to read-only via config (L09)
- [ ] Feedback capture wired; triage→eval promotion path works (L11)
**The awkward questions**
- [ ] What's the worst action this agent can take autonomously, and what limits the blast radius?
- [ ] Who is legally answerable for what it says?

### Use It
Encode the checklist as a CI job where possible (eval gate, chaos test, leakage test run automatically); keep the judgment items as a review doc with named sign-offs.

### War Story
In February 2024, a British Columbia tribunal ordered Air Canada to honor a bereavement-fare policy its website chatbot had invented — rejecting the airline's argument that the chatbot was "a separate legal entity responsible for its own actions." The tribunal found the airline responsible for all information on its site, chatbot included, and awarded the passenger damages. It's a small-claims case with a giant moral: the readiness question "who answers for what it says?" already has a legal answer, and it's you.

### Checkpoint
1. Which checklist items can be automated in CI, and which require human review? Why the split?
2. Why should the readiness review include someone who didn't build the agent?
3. Pick any three checklist items and describe the production incident each one prevents.
