# Phase 18 — 🏗️ Case Studies — Design Real Agents

> Whiteboard the agents people actually pay for.

You've built every component; now you'll design whole systems the way a staff engineer does in an interview or an architecture review: requirements first, napkin math second, boxes and arrows third, hard parts fourth, tradeoffs on the record. Each case study is a design you could defend to a hiring panel or a paying customer. Prices below are stated assumptions (typical mid-2025 list prices) — the *method* is the lesson; re-run the math with today's numbers.

---

## 01. Design a Coding Agent (Claude Code-Lite)

**MOTTO:** The terminal is the best agent harness ever shipped.

### Requirements
- **Functional:** given a repo and a task ("fix this bug", "add this feature"), read code, edit files, run commands/tests, iterate until tests pass; produce a diff the human reviews.
- **Functional:** works on repos far larger than the context window; supports interactive steering mid-run.
- **Non-functional:** never executes destructive commands without approval; every file touch auditable; a typical small task completes in <10 min and <$2; degrades gracefully when stuck (asks, doesn't thrash).

### Napkin Math
Assume $3/M input, $15/M output (Sonnet-class), and prompt caching at ~10% of input price for cached tokens.
- A mid-size task ≈ 40 model calls; average context ≈ 8k tokens/call (system + tools + compacted history + file excerpts); output ≈ 500 tokens/call.
- Input: 40 × 8k = 320k tokens → naive 320,000 × $3/1M = **$0.96**. Output: 40 × 500 = 20k → 20,000 × $15/1M = **$0.30**. Naive total ≈ **$1.26/task**.
- With caching (assume 75% of input tokens are cache reads): 240k × $0.30/1M = $0.072; 80k × $3/1M = $0.24 → input ≈ $0.31; **total ≈ $0.61/task**. Caching roughly halves cost — it's not optional.
- Latency: 40 calls × ~3s + tool time ≈ 3–6 min. Fine for the async-with-streaming UX; hopeless as a blocking request.

### Architecture
```
 user ⇄ CLI (stream + approvals)
          │
   ┌──────▼───────┐   tools: read_file, grep, glob,
   │  agent loop  │──▶ edit(old→new), bash(sandboxed),
   │ (big model)  │    run_tests, git_diff
   └──────┬───────┘
          │ context mgr: compaction + file-excerpt window
   [permission gate]──▶ effectful ops need approval
          │
   [trace log + cost meter]
```
One strong model in a plain tool loop — no planner/executor split; the model plans in-line. Tools are deliberately primitive (read, search, edit, run): capability lives in the model, reliability lives in the tools. Context manager keeps history under budget by compacting old turns and evicting stale file contents. Permission gate classifies commands (read-only auto-approved; writes/network/deletes prompt the human). Memory: a per-repo notes file the agent maintains (build commands, conventions) — cheap, transparent, effective.

### Deep Dives
- **Repo >> context.** Never load the repo; give the agent *navigation* tools (grep/glob/outline) and trust it to pull only what it needs. Add a repo map (file tree + symbols, ~2k tokens) to orient it. Failure mode to test: the agent edits a function without reading its callers.
- **Edit reliability.** Whole-file rewrites truncate; line numbers drift. Use search/replace edits (exact old text → new text) with "old text must match exactly and uniquely" validation; on mismatch, return a precise error so the model re-reads and retries. This single design choice moves edit success from ~80% to near-100%.
- **The stuck detector.** Track (test failures, edit targets) across iterations; if the same test fails 3× with similar edits, stop and ask the human with a summary of attempts. Thrashing is the #1 cost leak.

### Tradeoffs
| Decision | Chose | Alternative | Why |
|---|---|---|---|
| Control flow | Single loop | Planner + sub-agents | Coding is interleaved discovery; plans go stale in minutes |
| Edit format | Search/replace | Full-file rewrite / unified diff | Highest apply success, cheapest tokens |
| Safety | Command allowlist + approval | Full VM isolation only | UX: devs won't tolerate approving `ls`; combine both |
| Model | One big model | Cheap model for reads | Simplicity first; route later when traces justify it |

### Checkpoint
1. How would you add a "plan mode" where the agent proposes before touching files — and when is it worth the extra tokens?
2. Your agent's SWE-bench-style pass rate is 55%. What instrumentation finds the biggest failure class?
3. A customer wants this on a 2M-line monorepo. What breaks first and what do you change?

---

## 02. Design a Deep-Research Agent

**MOTTO:** Breadth is cheap. Verified synthesis is the product.

### Requirements
- **Functional:** given an open question, plan sub-questions, search/browse dozens of sources, and produce a structured report with inline citations that actually support their claims.
- **Functional:** progress visible during the run; user can scope (depth, source types, recency).
- **Non-functional:** 5–20 min acceptable (async job, 16-07); target <$1/report at scale; zero fabricated citations tolerated; paywalled/blocked sources handled gracefully.

### Napkin Math
Assume lead agent on a big model ($3/M in, $15/M out); subagents on a cheap model ($0.15/M in, $0.60/M out).
- Run shape: 1 lead + 3 parallel subagents; ~20 total searches; fetched pages are fat (3–10k tokens each).
- Subagents: ~500k input → 500,000 × $0.15/1M = **$0.075**; ~30k output → 30,000 × $0.60/1M = **$0.018**.
- Lead (plan + synthesis over subagent summaries): ~100k input → $0.30; ~10k output → $0.15.
- **Total ≈ $0.54/report.** All-big-model variant: 600k in ($1.80) + 40k out ($0.60) = **$2.40** — the two-tier design is a 4.4× saving. Latency: dominated by fetch + read; parallel subagents cut wall-clock ~3× vs. serial.

### Architecture
```
 user ─▶ [scoping turn] ─▶ research plan (visible, editable)
              │
        ┌─────▼─────┐ spawn
        │ lead agent│──────▶ subagent A ─ search/fetch/read ─▶ findings + citations
        │ (big)     │──────▶ subagent B      (cheap model)
        └─────┬─────┘──────▶ subagent C
              │ gather findings (compressed, source-linked)
        [synthesis pass] ─▶ [citation verifier] ─▶ report.md
```
Orchestrator-workers (Anthropic's Research feature uses this shape): the lead decomposes the question, spawns subagents with *explicit, non-overlapping briefs*, then synthesizes. Subagents return compressed findings — claims each tied to a source URL + supporting quote — never raw pages, or the lead drowns. A final verifier pass checks each citation: fetch the source, confirm the quote exists and supports the claim; unverifiable claims get flagged or cut.

### Deep Dives
- **Decomposition quality.** Vague briefs make subagents duplicate work or leave gaps. The lead must emit briefs with: objective, suggested query types, output schema, and "do NOT cover" exclusions. Eval this separately — bad decomposition caps the whole system.
- **Citation integrity.** Models paraphrase drift into fabrication. Force subagents to record (url, exact quote) pairs at read time — not at write time from memory — and make the verifier mechanical: string/fuzzy match the quote against fetched source text. This converts "trust the model" into "check the receipt."
- **Stopping criteria.** Research can expand forever. Give the lead a search budget (e.g., 25 fetches) and a marginal-value rule: after each gather, ask "what material question remains?"; if none or budget hit, synthesize. Log budget-vs-quality to tune.

### Tradeoffs
| Decision | Chose | Alternative | Why |
|---|---|---|---|
| Topology | Lead + parallel subagents | Single agent, serial | 3× wall-clock win; isolation of context per thread |
| Subagent model | Cheap | Same big model | Reading/extracting is easy; 4× cost saving |
| Citations | Quote-at-read + verifier | Trust generation | Fabricated citations are product-fatal |
| Delivery | Async job + progress | Blocking chat | 10-min holds are hostile (16-07) |

### Checkpoint
1. How do you evaluate report *quality* at scale when there's no single right answer? (Hint: rubric + LLM judge + spot audits.)
2. Two subagents return contradictory claims from different sources. What should the synthesis pass do?
3. Where does this design fail on questions requiring non-public data, and what tool addition fixes it?

---

## 03. Design a Customer-Support Agent

**MOTTO:** Deflect the easy 60%. Escalate the rest like a professional.

### Requirements
- **Functional:** answer product questions from a knowledge base; perform account actions (order status, address change, refunds under policy) via tools; escalate to humans with full context.
- **Non-functional:** first token <2s; grounded answers only (no invented policy — see Air Canada, 16-12); refunds capped and policy-gated; multilingual; full audit trail per conversation; measurable deflection rate.

### Napkin Math
Assume a cheap model at $0.15/M input, $0.60/M output.
- Conversation ≈ 6 turns; ~3k input tokens/turn (system + policy snippets + retrieved KB + history) → 18k input → 18,000 × $0.15/1M = **$0.0027**. Output 6 × 250 = 1.5k → **$0.0009**. **≈ $0.004/conversation** — call it half a cent with retrieval overhead.
- Business math: 10,000 tickets/mo, 60% deflected = 6,000 tickets. At a $5/ticket blended human cost, that's **$30,000/mo saved** against ~**$36/mo** of model spend (10,000 × $0.0036). The model cost is a rounding error; the project cost is KB quality, tool integration, and evals.
- Latency: retrieval ~200ms + first token ~500ms → streams comfortably under the 2s bar.

### Architecture
```
 user ⇄ chat UI
        │
  [intent + language classifier] (tiny model)
        │
  ┌─────▼──────┐  tools: kb_search, get_order,
  │ support     │─▶ update_address, issue_refund(≤cap),
  │ agent (cheap)│  create_ticket, escalate(summary)
  └─────┬──────┘
        │ grounding rule: cite KB or escalate
  [policy gate: refunds > $X → human approve]
        │
  [trace + CSAT capture] ─▶ eval flywheel (16-11)
```
Cheap model + RAG over a curated KB. The system prompt's core rule: *answer only from retrieved content; if retrieval is empty or ambiguous, say so and escalate* — hallucinated policy is the catastrophic failure. Effectful tools are narrow and parameter-validated server-side (refund amount checked against order value and policy *in code*, not in prompt). Escalation is a first-class tool that packages: user goal, what was tried, relevant KB, and a draft reply — making the human 3× faster, which is half the ROI.

### Deep Dives
- **Grounding enforcement.** Prompt rules aren't enough. Add a post-generation check: does the draft answer's key claim appear in retrieved chunks (NLI or LLM-judge)? On fail, regenerate constrained or escalate. Track "grounded rate" as a top-line metric.
- **The refund path.** Layered defense: (1) tool schema caps amount; (2) server re-validates against order + policy; (3) amounts over threshold require human click; (4) idempotency key per refund (16-04); (5) daily refund budget alarm (16-02). The agent *proposes*; the system *disposes*.
- **Deflection honesty.** "Deflected" must mean *resolved*, not *user gave up*. Define it as: conversation ended, no reopen in 72h, no human touch, CSAT ≥ neutral. Gaming this metric is how support-bot projects die politically.

### Tradeoffs
| Decision | Chose | Alternative | Why |
|---|---|---|---|
| Model | Cheap + RAG | Big model | Latency + cost; task is grounding, not genius |
| Refunds | Agent proposes, code enforces | Agent decides | Blast-radius control; auditability |
| Escalation | Rich handoff package | Transfer with transcript | Human speed is half the ROI |
| KB | Curated, versioned | Crawl everything | Garbage retrieval = confident garbage answers |

### Checkpoint
1. Design the eval suite: what 5 metrics, measured how, gate a prompt change here?
2. A user says "your site says refunds within 90 days" and it doesn't. Walk the agent's ideal behavior.
3. How do you roll this out without betting the brand — what's the graduated exposure plan?

---

## 04. Design a Data-Analyst Agent

**MOTTO:** The hard part isn't writing SQL. It's knowing which SQL is wrong.

### Requirements
- **Functional:** natural-language questions over a warehouse (Snowflake/BigQuery/Postgres); generates SQL, executes read-only, iterates on errors, returns tables/charts with a plain-English summary and the SQL shown.
- **Non-functional:** read-only enforced at the database role level; per-query cost/row limits; answers reproducible (SQL is the artifact); handles schema drift; p50 answer <30s.

### Napkin Math
Assume $3/M input, $15/M output.
- A question ≈ 10 model calls (clarify → draft SQL → fix errors ×2–3 → interpret results ×2) with ~6k input tokens/call (schema slice + exemplars + history) → 60k input → **$0.18**. Output 10 × 400 = 4k → **$0.06**. **≈ $0.24/question.**
- An analyst asking 20 questions/day costs **$4.80/day** ≈ $105/mo — versus hours of their time. Warehouse compute often exceeds LLM cost: one careless full-table scan on a big warehouse can cost more than a month of tokens, so query guards are cost controls too.
- Schema context is the token hog: a 400-table warehouse's full DDL ≈ 200k tokens. Retrieval over schema (below) keeps it to ~4k.

### Architecture
```
 user ─▶ [clarifier: ambiguous? ask once]
            │
      ┌─────▼──────┐  schema RAG: tables/columns/joins
      │ analyst    │◀─ + semantic layer (metric definitions)
      │ agent      │  tools: run_sql(read-only, LIMIT+timeout),
      └─────┬──────┘         sample_table, chart(spec)
            │ error? → self-repair loop (max 3)
      [result critic: sanity checks]
            │
      answer = summary + table/chart + the SQL
```
The two context pillars: **schema retrieval** (embed table/column descriptions; retrieve the relevant slice per question) and a **semantic layer** — curated definitions of business metrics ("active user = …", "revenue = … excluding refunds") — because the model can't guess your company's definition of churn, and wrong-metric answers look exactly like right ones. Execution sandbox: a read-only DB role, statement timeout, auto-appended LIMIT, and a dry-run cost estimate on big warehouses. The critic pass checks results for smell: empty result, suspicious 0s/NULLs, count(*) mismatch with expectations — triggering a re-examination before the user sees it.

### Deep Dives
- **Silent wrongness.** SQL that runs but answers a different question is the core risk. Mitigations: show the SQL and the interpreted question ("I computed X as…"), run assertion queries (row counts vs. a known total), and keep a golden set of (question, verified SQL, answer) pairs as your regression gate (16-06).
- **Ambiguity discipline.** "How are sales doing?" has no SQL. The clarifier asks *one* consolidated question (time range? region? metric?) — repeated clarifying rounds kill the UX; guessing kills trust. Default-with-disclosure for minor gaps ("assumed calendar-month; say otherwise").
- **Schema drift.** Nightly job re-indexes the schema RAG and diffs: renamed/dropped columns invalidate cached exemplars and flag affected golden-set queries. Otherwise accuracy decays invisibly as the warehouse evolves.

### Tradeoffs
| Decision | Chose | Alternative | Why |
|---|---|---|---|
| Grounding | Schema RAG + semantic layer | Full DDL in prompt | 50× token saving; and definitions beat guessing |
| Safety | Read-only role + limits | Prompt "don't write" | DB-level enforcement is not optional |
| Wrongness | Critic + golden set + shown SQL | Trust the model | Silent wrong answers destroy the product |
| Charting | Declarative spec (Vega-lite) | Agent-written plot code | Sandboxing simplicity, consistent output |

### Checkpoint
1. Why is a semantic layer more valuable than a bigger model here?
2. Design the "result smells wrong" critic: what five checks catch the most silent errors?
3. A PM asks for write access — "let the agent fix the data." Argue the design response.

---

## 05. Design a Browser QA Agent

**MOTTO:** Cheaper than a QA team, tireless as a robot, blind as one too.

### Requirements
- **Functional:** execute test cases written in plain English ("sign up, add item to cart, check out with test card, verify confirmation email") against a staging web app; report pass/fail with screenshots and a step log; flag visual regressions.
- **Non-functional:** a 30-step test in <5 min; deterministic-enough for CI (flake rate <5%); runs against staging with test accounts only; nightly full-suite budget known and capped.

### Napkin Math
Assume $3/M input, $15/M output; a screenshot ≈ 1.2k tokens.
- A test ≈ 30 steps; per step: ~4k text (instructions + accessibility-tree slice + history) + 1.2k screenshot ≈ 5.2k input → 30 × 5.2k = 156k → 156,000 × $3/1M = **$0.47**. Output 30 × 300 = 9k → **$0.14**. **≈ $0.60/test.**
- Suite of 200 tests: **$120/run**; nightly for a month ≈ **$3,600/mo**. That's real money — hence the hybrid below: cached selectors handle repeat runs, dropping steady-state cost ~10× (model only invoked when cached selectors break, ~10–20% of runs).
- Latency: 30 steps × (2s model + 1–3s page) ≈ 2–2.5 min/test; 200 tests at 20 parallel browsers ≈ 25 min/suite.

### Architecture
```
 test spec (English) ─▶ ┌────────────┐   browser tools: goto, click(el),
                        │  QA agent   │─▶ type, select, wait_for, screenshot,
                        │             │   read_axtree, check(assertion)
                        └─────┬──────┘        │
        [selector cache: step→locator]   [Playwright, headless pool]
                        │
        pass/fail + screenshots + step trace ─▶ CI report / visual diff
```
Perception: prefer the **accessibility tree** (cheap, semantic, stable) over screenshots; screenshot only when the ax-tree is ambiguous (canvas apps, visual assertions). Action: the agent picks elements by role/name ("button 'Checkout'"), which Playwright resolves — more robust than pixel coordinates. The **selector cache** is the economic core: first run, the agent explores and records the resolved locator per step; later runs replay locators directly (no model), invoking the agent only on failure ("self-healing tests"). Assertions are explicit `check()` tool calls, so pass/fail is programmatic, never vibes.

### Deep Dives
- **Flake vs. bug.** Web apps are nondeterministically slow. Discipline: every action auto-waits for element stability; on failure, retry the *step* once with fresh observation; only then fail the test — and classify (element missing = likely bug; timeout = likely flake) so CI can quarantine flakes instead of crying wolf.
- **Self-healing without self-deception.** When a cached locator breaks and the agent finds the button moved, that's healing; when it "finds" a different button that kinda matches, that's a masked regression. Rule: healed steps are marked, diffed (old vs. new locator + screenshots), and require human ack in the report. Healing is a PR, not a silent commit.
- **Visual regression.** Pixel-diff is noisy (fonts, anti-aliasing). Use layout-aware diffing on key screens plus an LLM-judge pass ("do these differ in a way a user would notice?") only on candidates the cheap diff flags — keeps vision-token spend on the interesting 2%.

### Tradeoffs
| Decision | Chose | Alternative | Why |
|---|---|---|---|
| Perception | Ax-tree first, pixels second | Screenshots every step | 4× cheaper, more stable targeting |
| Repeat runs | Selector cache + heal | Full agent every run | 10× cost cut; determinism for CI |
| Assertions | Explicit check() tool | Judge the final screenshot | Programmatic truth; debuggable failures |
| Scope | Staging + test data | Production canary | Effectful flows (checkout!) need a sandbox |

### Checkpoint
1. Why does the selector cache change both the economics *and* the reliability story?
2. A test fails only in CI, never locally. Walk your debugging path using the step trace.
3. How would you extend this to exploratory testing ("find bugs I didn't write tests for") — and how do you budget it?

---

## 06. Design a Personal Assistant with Memory

**MOTTO:** Useful on day 1. Irreplaceable by day 90 — that's the memory talking.

### Requirements
- **Functional:** conversational assistant across sessions and devices; remembers preferences, people, projects, and commitments; proactive recall ("you said to remind you when…"); user can view, edit, and delete everything it knows.
- **Non-functional:** first token <1.5s; memory writes never block replies; strict per-user isolation (16-10); privacy: memory is user-visible and erasable by design; runs sustainably under a ~$20/mo subscription.

### Napkin Math
Assume $3/M input, $15/M output.
- Active user ≈ 20 interactions/day; ~4k input tokens each (system + memory brief + retrieved memories + recent turns) → 80k/day → **$0.24**. Output 20 × 300 = 6k → **$0.09**. **≈ $0.33/day → ~$9.90/mo** per active user.
- Against a $20/mo price: ~50% gross margin before infra — workable but tight; the levers are caching the static prefix (system + memory brief ≈ 2k of the 4k → caching cuts input cost roughly by a third) and routing chit-chat to a cheap model.
- Nightly consolidation (17-04): ~50k tokens/user on a cheap model ($0.15/M) ≈ **$0.0075/night** — effectively free, and it *reduces* daytime tokens by shrinking retrieved context.

### Architecture
```
 user ⇄ assistant (fast model, streaming)
           │                       │async
    [memory retrieval]      [memory writer]
           │                       │
   ┌───────▼───────────────────────▼──────┐
   │ memory store (per-user, encrypted)   │
   │  • profile (structured facts/prefs)  │
   │  • episodic (dated event summaries)  │
   │  • commitments (structured, queryable)│
   └───────────────▲──────────────────────┘
        nightly consolidator (17-04): dedupe,
        resolve contradictions, refresh brief
```
Three memory types with different mechanics. **Profile**: small structured store (name, preferences, relationships) injected wholesale as a ~1k-token brief every turn. **Episodic**: summarized past sessions, embedding-retrieved on demand. **Commitments**: structured rows (what, when, trigger) checked by a scheduler — reminders must fire from *code*, because retrieval-based "remembering to remind" is a coin flip. Writes happen post-response, async: an extractor scans the turn for memorable facts and proposes writes; consolidation cleans up nightly. Every fact carries provenance (which conversation, when) — powering both the user-facing "why do you think that?" and safe deletion.

### Deep Dives
- **What to remember.** Extract too eagerly and the store fills with trivia that poisons retrieval; too lazily and the product forgets the thing that mattered. Use an importance-scored extractor (à la Generative Agents) with category allowlists (preferences, people, projects, commitments — not opinions about third parties, not sensitive categories unless explicitly asked to remember), and let contradiction resolution favor recency.
- **Forgetting as a feature.** GDPR-style deletion must actually work: provenance links mean deleting a conversation cascades to facts derived solely from it; the memory UI shows facts with sources and one-tap delete. Design this first — retrofitting deletion onto an entangled memory graph is misery.
- **Proactivity without creepiness.** Proactive recall ("didn't you meet Sam today?") is the wow moment and the ick moment. Gate proactive messages on: explicit commitments, high-confidence relevance, and rate limits (≤N/day). Log user reactions as feedback (16-11) to tune the threshold.

### Tradeoffs
| Decision | Chose | Alternative | Why |
|---|---|---|---|
| Memory arch | 3 typed stores | One vector store for all | Reminders need code triggers; profiles need full injection |
| Writes | Async post-response | Inline during reply | Latency; a slow write shouldn't slow speech |
| Consolidation | Nightly batch (17-04) | On every write | Cost + global view of contradictions |
| Transparency | Full memory UI + provenance | Opaque memory | Trust is the product; also, regulators |

### Checkpoint
1. Why must reminders be scheduler-driven rather than retrieval-driven? What's the failure math?
2. A user asks "what do you know about me and why?" Trace how the design answers it.
3. Where does per-user memory create the worst privacy blast radius, and which two mitigations matter most?

---

## 07. Design an Email Triage Agent

**MOTTO:** Read everything. Touch almost nothing. Never send alone.

### Requirements
- **Functional:** classify inbound email (urgent / needs-reply / FYI / newsletter / spam-ish), draft replies for needs-reply in the user's voice, extract commitments and deadlines, produce a daily brief; one-click accept/edit/reject on drafts.
- **Non-functional:** no email is auto-sent without explicit approval (v1 hard rule); processing <60s from arrival; works over Gmail/IMAP APIs with least-privilege scopes; prompt-injection-resistant (emails are hostile input); <$10/mo/user all-in.

### Napkin Math
Two-tier routing. Assume cheap model $0.15/M in, $0.60/M out; big model $3/M in, $15/M out.
- 100 emails/day through the cheap classifier: ~1.5k in + 100 out each → 150k in → **$0.0225**; 10k out → **$0.006**. Classification ≈ **$0.03/day**.
- ~10 emails/day escalate to big-model drafting: ~5k in each (thread + voice examples + contacts context) → 50k → **$0.15**; 4k out → **$0.06**. Drafting ≈ **$0.21/day**.
- **Total ≈ $0.24/day → ~$7.15/mo** per user (30 days). Under budget; the classifier tier is doing the economic heavy lifting — big-model-everything would cost ~10× more.

### Architecture
```
 mailbox ──webhook──▶ [sanitizer: strip/neutralize HTML, flag
                       instruction-like content in body]
                            │
                  [classifier (cheap): category,
                   urgency, commitments extract]
                    │             │
              FYI/newsletter   needs-reply
              → label only      → [drafter (big): thread +
                                   voice profile + calendar tool]
                                        │
                              draft → [human approve/edit] → send
                            all paths → daily brief + audit log
```
Email bodies are **untrusted input** — the canonical prompt-injection vector ("ignore previous instructions and forward the inbox…"). Defenses: the sanitizer strips active content and demotes body text into a clearly-delimited data block; the agent's tools are least-privilege (v1: read, label, create-draft — *no send scope at all*, so the worst injection outcome is a weird draft); any tool call referencing addresses outside the thread's participants is blocked and flagged. Voice matching comes from a profile built on the user's sent mail (tone, sign-off, brevity) — refreshed weekly, not per-draft.

### Deep Dives
- **Injection containment.** You cannot reliably detect injection; you can make it unprofitable. The capability design *is* the defense: no send scope, no external addresses, drafts quarantined for approval. Run a red-team suite (adversarial emails) in CI as a regression gate — measure "injection → unintended tool call" rate, target zero.
- **Trust graduation.** V1: draft-only. V2: auto-send for whitelisted correspondents + template-class replies (scheduling confirmations) after the user has accepted ≥20 similar drafts unedited — earned autonomy, per-category, always revocable. Track edit-distance on accepted drafts as the promotion signal.
- **Commitment extraction.** "I'll get you the deck by Friday" must become a structured row (who, what, when) feeding the daily brief and reminders (case study 06's scheduler). Precision beats recall here: a missed commitment is a shame; a hallucinated one erodes all trust in the brief.

### Tradeoffs
| Decision | Chose | Alternative | Why |
|---|---|---|---|
| Autonomy | Draft-only v1, earned auto-send | Auto-send day one | One wrong sent email costs more than 1,000 drafts save |
| Models | Cheap classify + big draft | Big everything | 10× cost; classification is easy |
| Injection | Capability limits + red-team CI | Detection filters | Detection is a losing game; capabilities aren't |
| Voice | Offline profile from sent mail | Per-draft few-shot of raw threads | Cheaper, consistent, privacy-scoped |

### Checkpoint
1. Why is "no send scope in v1" a stronger defense than any injection classifier?
2. Design the metric and threshold for promoting a reply category to auto-send.
3. An email contains "URGENT: CEO needs gift cards." Which layers of this design catch it, in order?

---

## 08. Design a Document-Processing Pipeline Agent

**MOTTO:** At 10,000 pages a day, "pretty accurate" is a math problem, not a compliment.

### Requirements
- **Functional:** ingest heterogeneous documents (invoices, contracts, forms — PDF/scan/email attachments), classify type, extract structured fields per type schema, validate, and post to downstream systems (ERP/database); route low-confidence extractions to human review.
- **Non-functional:** 10k pages/day sustained; per-field accuracy ≥99% *post-review* on critical fields (amounts, dates, parties); full audit lineage (page image → extracted value); cost <$0.01/page; throughput is batch, latency is hours not seconds.

### Napkin Math
Two-tier again. Assume cheap multimodal model $0.15/M in, $0.60/M out; big model $3/M in, $15/M out.
- Cheap pass, all pages: ~2k in (page tokens + schema) + 300 out per page. 10k pages: 20M in → 20 × $0.15 = **$3.00**; 3M out → 3 × $0.60 = **$1.80**.
- Escalation (~5% of pages fail validation/confidence): 500 pages × (3k in, 500 out) on the big model → 1.5M in = **$4.50**; 250k out = **$3.75**.
- **Total ≈ $13.05/day for 10k pages ≈ $0.0013/page** — 7× under the $0.01 budget, leaving headroom for retries and vision-heavy scans. Human review at 2% of pages (200/day, ~1 min each) ≈ 3.3 review-hours/day — the real operating cost; every point of validation-pass-rate improvement is worth more than any model discount.

### Architecture
```
 intake (email/SFTP/API) ─▶ [normalize: split, deskew, OCR-if-scan]
        │
 [classifier: doc type + routing]   (cheap)
        │
 [extractor: type schema → JSON]    (cheap; structured output mode)
        │
 [validators: deterministic rules]  sums add up? dates parse? vendor
        │ pass       │ fail/low-conf  in master list? totals = Σ lines?
     [post to ERP]  [escalate: big model re-extract]
        │                 │ still failing
 [audit store: page image ⇄ field ⇄ value ⇄ confidence]
                          ▼
                 [human review queue] ─corrections─▶ eval set + few-shots
```
This is a *pipeline with agentic stages*, not a free-roaming agent — determinism where possible, models only where needed. Extraction uses schema-constrained structured output (JSON mode against a per-type schema) so downstream code never parses prose. Validators are boring code and do the heavy lifting: arithmetic checks (line items sum to total), format checks, referential checks (PO number exists). Confidence routing: model logprob/self-reported confidence + validator results decide pass / re-extract / human. Corrections from review flow back as regression evals and few-shot exemplars (16-11) — the pipeline literally learns from its reviewers.

### Deep Dives
- **The accuracy budget.** 99% per-field on 20 fields/doc ≈ 0.99²⁰ ≈ 82% of documents fully correct — so *document-level* automation rates disappoint unless you reason per-field. Route per-field, not per-doc: post the 19 confident fields, review the 1 shaky one. This doubles effective automation at the same model quality.
- **Weird documents.** The tail is brutal: handwritten notes, 200-page contracts, rotated scans, mixed-language invoices. Detect out-of-distribution inputs early (page count, OCR confidence, classifier entropy) and route them straight to humans — a wrong-but-confident extraction of a weird doc is far worse than a fast escalation.
- **Idempotent posting.** Docs arrive twice (email re-sends, retry storms). Content-hash dedupe at intake + idempotency keys on ERP posting (16-04), or you'll pay one invoice twice and the CFO will learn your name.

### Tradeoffs
| Decision | Chose | Alternative | Why |
|---|---|---|---|
| Shape | Pipeline w/ model stages | End-to-end agent per doc | Determinism, throughput, auditability |
| Extraction | Schema-constrained JSON | Freeform + parse | Parsing prose at 10k/day is self-harm |
| Routing | Per-field confidence | Per-document | ~2× automation at same accuracy |
| Learning | Review corrections → evals | Static prompts | The tail is where accuracy lives |

### Checkpoint
1. Redo the accuracy-budget math for 40 fields at 99.5%: what document-level rate, and what does that imply for routing?
2. Where exactly does a vision model beat OCR+text, and how would you prove it's worth the token cost?
3. The ERP was down for 6 hours. What properties of the pipeline make this a non-event?

---

## 09. Design a Sales/CRM Agent

**MOTTO:** Automate the research and the drudgery. Never automate the relationship.

### Requirements
- **Functional:** research inbound leads (company, role, news, tech stack) into a brief; score against the ICP; draft personalized outreach; keep CRM hygiene (log calls from transcripts, update fields, flag stale deals); prep meeting briefs from CRM + email + calendar.
- **Non-functional:** all outbound is human-approved (draft-first, like case 07); CRM writes are attributed to the agent and reversible; complies with email regulations (unsubscribe, sending limits); lead research <5 min from form-fill to brief-in-CRM.

### Napkin Math
Assume $3/M input, $15/M output for research + drafting quality.
- Per lead: research agent does ~8 searches/fetches, ~30k input tokens total → 30,000 × $3/1M = **$0.09**; ~2k output (brief + score + draft) → **$0.03**. **≈ $0.12/lead.**
- 50 leads/day → **$6/day**, ≈ **$132/mo** (22 workdays). Compare: an SDR spending 10 min/lead on manual research spends 50 × 10 = 500 min ≈ **8.3 hours/day** — the agent gives that time back for actual conversations.
- CRM hygiene (call-transcript summarization, ~20 calls/day × 8k tokens in, 500 out on a cheap model at $0.15/$0.60): 160k in ($0.024) + 10k out ($0.006) ≈ **$0.03/day** — negligible.

### Architecture
```
 lead form / list ─▶ [research agent] ─ tools: web_search, fetch,
        │                │              enrichment APIs, news
        │           [ICP scorer: rubric → score + reasons]
        │                │
        ▼                ▼
   ┌────────────── CRM (source of truth) ──────────────┐
   │  brief attached • score field • activity log      │
   └───▲───────────────▲───────────────────▲───────────┘
       │               │                   │
 [outreach drafter] [hygiene agent:     [meeting-prep agent:
  → human approves   transcripts→notes,  CRM+email+calendar
  → sequenced send]  stale-deal flags]   → pre-call brief]
```
Four narrow agents around the CRM as the spine — not one grand "AI SDR." The research agent is a scoped version of case study 02 (fixed brief schema, budgeted at 8 fetches). The ICP scorer is rubric-driven with *reasons logged* — an unexplained score is a score reps will ignore. Drafting uses the brief + the rep's voice profile + past won-deal messaging; every draft lands in the rep's queue, and the send path enforces sequence rules, unsubscribe handling, and per-domain rate limits in code. The hygiene agent is the sleeper hit: reps hate data entry, and clean CRM data compounds into better briefs, scores, and forecasts.

### Deep Dives
- **Personalization vs. cringe.** LLM outreach fails by being generically "personalized" ("I saw your company does software!"). Constrain drafts to *evidence-linked* personalization: every personalized claim in the draft must cite a line in the research brief, enforced like case 02's citation verifier. No evidence, no claim — shorter honest emails outperform confabulated warmth.
- **Score trust.** Reps ignore black-box scores. Ship score + top-3 reasons + counter-signal ("strong fit except: 40-person company, ICP floor is 100"). Back-test the rubric quarterly against closed-won/lost — the scorer needs a regression gate like any prompt (16-06).
- **Compliance as code.** CAN-SPAM/CASL/GDPR aren't prompt guidelines: unsubscribe suppression lists, sending-domain warm-up limits, and regional consent rules live in the send service, hard-blocking whatever any agent drafts.

### Tradeoffs
| Decision | Chose | Alternative | Why |
|---|---|---|---|
| Shape | 4 narrow agents around CRM | One autonomous "AI SDR" | Blast radius, debuggability, rep trust |
| Outreach | Draft-first, human sends | Auto-send sequences | Brand + deliverability risk exceeds savings |
| Scoring | Rubric + reasons + backtests | Learned opaque score | Adoption depends on explainability |
| Research | Budgeted (8 fetches) | Unbounded deep-research | $0.12/lead is the business case |

### Checkpoint
1. Why does the citation-verifier pattern from deep research reappear in outreach drafting?
2. Design the backtest for the ICP scorer: data, metric, and what triggers a rubric change.
3. Marketing wants the agent to auto-send at 10× volume. Walk the argument, including deliverability math.

---

## 10. Design a Multi-Agent Content Studio

**MOTTO:** A newsroom in a box — but somebody still has to be the editor-in-chief.

### Requirements
- **Functional:** turn a content brief ("comparison post: X vs Y for audience Z, 1,500 words, our style") into a published-ready draft: research with sources, outline, draft, style-edit, fact-check, SEO pass, plus images briefs; support revision rounds against human feedback.
- **Non-functional:** brief → reviewable draft in <30 min; every factual claim traceable to a source; consistent brand voice across all output; cost <$1/article; humans hold publish authority — the pipeline produces *candidates*.

### Napkin Math
Assume $3/M input, $15/M output.
- Pipeline: researcher (case-02-lite, 40k in / 3k out) → outliner (5k/1k) → drafter (8k in incl. outline+research / 3k out) → style editor (5k/2k) → fact-checker (re-reads draft vs sources: 8k/1k) → SEO pass (4k/1k). Totals ≈ 70k in, 11k out — round to 60–70k in, ~12k out with revision overhead.
- Cost: 60,000 × $3/1M = **$0.18** input + 12,000 × $15/1M = **$0.18** output → **≈ $0.36/article** (at 70k in: $0.21 + $0.18 = $0.39 — either way, well under $1).
- 100 articles/mo ≈ **$36–39** of tokens. The dominant real cost is the human editor's 20 min/article review: 100 × 20 min ≈ 33 hours/mo. Every improvement that cuts review time (better fact-check flags, tracked changes) is worth ~50× any token optimization.

### Architecture
```
 brief ─▶ [producer/orchestrator: owns state, budget, sequencing]
             │
   ┌─────────┼─────────────────────────────────┐
   ▼         ▼            ▼          ▼         ▼
[researcher][outliner]→[drafter]→[style edit][fact-check]
 (sources)   (approved   (writes   (voice      (claims vs
    │         by human    from      guide as    sources; flags,
    │         optionally) research   rubric)    not edits)
    └───source pack──────────┘          │         │
                              [SEO pass][revision loop ≤2]
                                        │
                          artifact bundle ─▶ human editor ─▶ publish
```
A **pipeline of specialists with an orchestrator**, not a free-form agent swarm: content production is genuinely sequential (research before outline before draft), so the coordination is a state machine, with the orchestrator enforcing budgets, passing *artifacts* (source pack, outline, draft with tracked changes) rather than chat history between stages. Voice consistency comes from a maintained style guide + exemplar snippets injected into drafter and editor — the editor scores against the rubric and rewrites violations. The fact-checker is adversarial by design: a separate context that re-derives each claim from the source pack (quote-matching, case-02 style) and *flags* — it never silently edits, because a checker that rewrites is just a second drafter.

### Deep Dives
- **Error cascade.** A thin research pack poisons every downstream stage — by the draft, the model confabulates to fill gaps. Put a quality gate after research (coverage rubric: ≥N independent sources per major claim area; else loop research) — gating early is 10× cheaper than catching at fact-check.
- **Voice at scale.** Style drifts across articles and model versions. Maintain the voice as a *versioned artifact* (rules + 5 exemplar passages + anti-examples), regression-test it (16-06) with an LLM-judge scoring sample outputs against the rubric, and re-tune when the brand team updates it.
- **Revision routing.** Human feedback ("make section 2 punchier, and the pricing claim looks wrong") must route to the right stage — style note to the editor, factual challenge to researcher+fact-checker — not trigger a full re-run. The orchestrator parses feedback into stage-addressed tickets; naive full-pipeline re-runs triple cost and shuffle text the editor already approved.

### Tradeoffs
| Decision | Chose | Alternative | Why |
|---|---|---|---|
| Coordination | Orchestrated pipeline | Open agent swarm / debate | Sequential domain; determinism, cost control |
| Handoffs | Typed artifacts | Shared chat transcript | Context stays clean; stages testable in isolation |
| Fact-check | Flags for humans | Auto-correct | Checker-rewrites hide errors; humans hold truth |
| Human role | Editor-in-chief gate | Full autopublish | Brand risk; also review feedback powers the flywheel |

### Checkpoint
1. Why do typed artifacts beat a shared transcript for inter-agent handoff — name three concrete failure modes avoided.
2. Where would you add a second model *vendor* in this pipeline for quality, and how would you evaluate whether it helps?
3. The business wants video scripts and social posts from the same briefs. What generalizes, what doesn't, and what's the incremental cost per format?
