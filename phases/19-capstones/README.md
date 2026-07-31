# Phase 19 — 🏆 Capstone Projects

> Stop reading about agents. Ship one. Then ship a team of them.

Eighteen phases of concepts are worth exactly one working repo. Each capstone below is a complete project spec: pick one (or run them in order — they compound), build it end to end, and hold yourself to the Definition of Done like a reviewer who doesn't like you. No tutorials from here on. Just you, a terminal, and a model.

---

## 01. Capstone: Your Own Agent Framework in 500 Lines

**GOAL:** Rebuild the core of every agent framework — loop, tools, context, state — small enough to hold in your head, good enough to build the other capstones on.

### What You'll Build
A Python (or TypeScript) package — call it `microagent` — providing: an agent loop with streaming, tool registration via decorators with auto-generated JSON schemas, context management with compaction, session persistence, retries with idempotency awareness, and tracing to JSONL. Hard limit: 500 lines of core library code (tests and examples don't count). The constraint is the curriculum: every line must earn its place.

### Requirements
- `@tool` decorator derives name/description/schema from the function signature and docstring; readonly vs. effectful is declared, and the executor treats them differently (auto-retry reads only — Phase 16-04).
- Agent loop supports: streaming output, parallel tool execution, turn caps, cost caps, and a stop-and-summarize graceful exit.
- Context manager compacts oldest turns past a token budget; sessions serialize to disk and resume mid-run.
- Every run emits a trace (spans with inputs/outputs/tokens/cost) replayable by a `microagent replay <trace>` command.
- Provider-agnostic: at least two model providers behind one interface.

### Milestones
1. Bare loop: model + one tool + while-loop; a task completes end to end.
2. Tool system: decorator, schema generation, parallel execution, retry policy.
3. Context + state: compaction, session save/resume, kill the process mid-run and recover.
4. Tracing: JSONL spans, cost accounting, the replay command.
5. Second provider + a 3-example gallery (calculator agent, file agent, research-lite agent).
6. The audit: count lines, cut to ≤500, write the "what I left out and why" doc.

### Stretch Goals
- Hooks API (pre/post tool-call interceptors) — then implement the permission gate as a hook, proving the abstraction.
- Publish it (PyPI/npm) with docs; get one person you don't know to use it.

### Definition of Done
- [ ] Core library ≤500 lines, no framework dependencies (HTTP client and stdlib only)
- [ ] All three gallery agents run successfully with streaming
- [ ] Mid-run process kill → session resumes and completes
- [ ] A trace from a gallery run replays deterministically to the divergence point
- [ ] Turn cap and cost cap each trigger the graceful-exit path in tests
- [ ] README explains every design decision in one paragraph each

### Concepts You'll Cement
The agent loop (Phase 2), tool schemas and execution (Phase 3), context management (Phase 5), persistence, retries, tracing, and cost control (Phase 16) — by owning every line instead of importing them.

---

## 02. Capstone: A Coding Agent That Passes Its Own Tests

**GOAL:** Build a terminal coding agent that, given a repo and an issue, produces a patch that makes the tests pass — then prove it on a benchmark you didn't write.

### What You'll Build
A CLI coding agent (on your Capstone-01 framework or from scratch) implementing the case-study-01 design: file navigation tools, search/replace editing, sandboxed command execution, a permission gate, and a stuck detector. Then an evaluation run against SWE-bench Lite (or a 25-task slice of it) with honest reporting.

### Requirements
- Tools: `read_file`, `grep`, `glob`, `edit` (exact-match search/replace with unique-match validation), `bash` (sandboxed, allowlisted), `run_tests`.
- Never loads whole repos: navigation-first context strategy with a repo map.
- Stuck detection: same test failing 3× with similar edits → stop with a summary of attempts.
- Benchmark harness: containerized per-task environments, patch extraction, official test-based scoring — no self-graded success.
- Full cost/latency accounting per task; a results table in the README.

### Milestones
1. Agent fixes a planted bug in a toy repo you wrote (walk before benchmark).
2. Edit reliability hardening: 50-edit stress test across gnarly cases (unicode, indentation, near-duplicate blocks) at >95% apply rate.
3. Harness: run one SWE-bench Lite task end to end in a container, scored by the repo's own tests.
4. Full slice run (≥25 tasks); collect traces for every failure.
5. Failure autopsy: categorize every miss (wrong file? bad edit? wrong understanding? gave up?), fix the top category, re-run.
6. Write the report: score, cost/task, failure taxonomy, before/after of your one improvement.

### Stretch Goals
- Add a plan-then-execute mode and measure whether it actually helps on this benchmark (the answer is less obvious than you think).
- Try a cheap-model routing tier for read/search turns; report the cost delta at equal score.

### Definition of Done
- [ ] ≥20% resolved on your SWE-bench Lite slice (honest, test-scored) — or a documented autopsy explaining every point below it
- [ ] Mean cost per attempted task ≤$1.50 with per-task breakdown
- [ ] Zero unsandboxed command executions (audit the traces)
- [ ] Failure taxonomy with counts, and one data-driven improvement with before/after scores
- [ ] Another person can run the whole eval from your README

### Concepts You'll Cement
Tool design under adversity (Phase 3), context strategy for large codebases (Phase 5), sandboxing (safety phases), and — above all — honest benchmark-driven iteration (Phase 9): the loop of run, autopsy, fix, re-run is the actual skill.

---

## 03. Capstone: A Deep-Research Agent with Citations

**GOAL:** Build an orchestrator-plus-subagents research system whose reports you'd stake your name on — every claim traceable to a source that really says it.

### What You'll Build
The case-study-02 design, running: a lead agent that scopes and decomposes questions, parallel search subagents on a cheap model, a synthesis pass, and a mechanical citation verifier that fetches every cited source and confirms the supporting quote exists. Delivered as an async job (queue, progress events, notification) with a markdown report artifact.

### Requirements
- Lead emits subagent briefs with objective, output schema, and exclusions; subagents run in parallel with a fetch budget.
- Subagents record (url, exact quote) pairs at read time; findings are compressed and source-linked.
- Citation verifier: re-fetch, fuzzy-match quotes, mark each claim verified/unverified; unverified claims are cut or flagged in the report — never silently kept.
- Async delivery: job API, progress events ("subagent B: reading source 4/7"), resumable via checkpoints on worker death.
- Budget enforcement: max fetches and max dollars per report, graceful summarize-and-stop.

### Milestones
1. Single-agent researcher: search, fetch, synthesize with citations — no verification yet.
2. The verifier: quote-matching against fetched sources; measure the pre-verifier fabrication rate on 10 reports (this number will motivate you).
3. Multi-agent: lead + 3 parallel subagents with briefs; compare quality and wall-clock vs. milestone 1 on the same questions.
4. Async job wrapper with progress and checkpoint-resume.
5. Evaluation: a 15-question suite with a quality rubric (coverage, accuracy, citation integrity, structure), scored by LLM judge + your spot audits.

### Stretch Goals
- Contradiction handling: when sources disagree, the report presents both with sourcing rather than picking silently.
- Add source-quality weighting (primary > secondary > SEO sludge) and measure the effect on your rubric scores.

### Definition of Done
- [ ] Zero unverified-claims-presented-as-fact across the 15-question eval suite
- [ ] Parallel subagents beat single-agent wall-clock by ≥2× on multi-facet questions
- [ ] Worker killed mid-run resumes and delivers the report
- [ ] Cost per report ≤$1.00 with the two-tier model split, itemized in the trace
- [ ] Rubric scores reported per question, including the failures

### Concepts You'll Cement
Multi-agent orchestration (Phase on multi-agent), context isolation and compression between agents, async deployment patterns (16-07), budget enforcement (16-02), and the deepest one: verification as architecture — designing so trust is checked, not assumed.

---

## 04. Capstone: An MCP Server Suite

**GOAL:** Build three production-quality MCP servers and experience the other side of the tool-call boundary — where tool design quality directly becomes agent capability.

### What You'll Build
Three Model Context Protocol servers exercising different capability classes: (1) a **knowledge server** exposing search/read over a document corpus (resources + tools), (2) an **effectful server** wrapping a real system with writes — e.g., a task/todo database — with idempotency keys and a dry-run mode, (3) a **long-running server** wrapping a slow operation (e.g., a site crawler or your Capstone-03 researcher) with job-style start/status/result tools. Plus a shared test harness that exercises all three through a real client (Claude Desktop, or any MCP-capable client).

### Requirements
- Spec-compliant MCP over stdio (and HTTP/SSE for one of the three); tools, resources, and at least one prompt template exposed.
- Tool descriptions written for a model consumer: what it does, when to use it, error semantics, examples — then *tested* by measuring an agent's tool-selection accuracy against a 20-task suite.
- Effectful server: idempotency keys on writes, dry-run mode, input validation with actionable error messages (the model must be able to self-correct from your errors).
- Long-running server: start returns a job id; status streams progress; results retrievable after client reconnect.
- Auth/config via environment; no secrets in code; graceful degradation when the backing system is down.

### Milestones
1. Knowledge server: search + read tools over a corpus; wire into a client and query it interactively.
2. Tool-description iteration: run the 20-task selection suite, rewrite descriptions, re-run — record the accuracy delta (this is the heart of the capstone).
3. Effectful server with idempotency + dry-run; adversarial tests (duplicate calls, garbage inputs, mid-write crash).
4. Long-running server with the job pattern; kill and reconnect the client mid-job.
5. Package the suite: install docs, config reference, the test harness, and a demo script.

### Stretch Goals
- Add OAuth-style scoped tokens to the effectful server: a read-only token demonstrably cannot write.
- Publish one server publicly and incorporate one external user's feedback.

### Definition of Done
- [ ] All three servers pass the shared harness through a real MCP client
- [ ] Tool-selection accuracy ≥90% on the 20-task suite, with the before/after description experiment documented
- [ ] Duplicate effectful calls with the same idempotency key produce exactly one write (tested)
- [ ] Client disconnect/reconnect during a long job retrieves the result
- [ ] Malformed inputs return errors an agent demonstrably self-corrects from (show a trace)

### Concepts You'll Cement
Tool schemas and ergonomics (Phase 3), MCP itself (Phase on MCP), idempotent effectful design (16-04), async job patterns (16-07) — and tool-description-as-prompt-engineering, the most underrated skill in the agent stack.

---

## 05. Capstone: A Local Agent on an Open Model

**GOAL:** Run the full agent stack — model included — on your own hardware, and learn what the frontier labs' polish has been hiding from you.

### What You'll Build
A fully local agent: an open-weights model (7–14B class, e.g., a Qwen or Llama instruct variant) served locally (llama.cpp/Ollama/vLLM), driving your Capstone-01 framework with tool calling, on tasks a local agent is actually good for — file organization, local document Q&A, scripted automations — with zero bytes leaving the machine.

### Requirements
- Local serving with an OpenAI-compatible endpoint; your framework talks to it with zero cloud fallback in local mode.
- Tool calling that works *despite the model*: robust parsing of imperfect tool-call output, re-prompting on malformed calls, format few-shots — measure and report tool-call validity rate.
- A model-selection study: ≥3 models / quantization levels compared on your own 20-task agent suite (success rate, tokens/sec, memory) — not on vibes.
- Honest capability boundary: a written comparison of the same 20 tasks against a frontier API model, with per-task analysis of where the local model breaks (long context? multi-step planning? tool syntax?).
- Practical UX: streaming, and first token <2s on your hardware for typical prompts.

### Milestones
1. Serve a model locally; raw chat works; measure tokens/sec.
2. Wire into your framework; get one tool call working end to end (budget a full day for tool-call parsing pain — it's the lesson).
3. Hardening: malformed-call recovery, format few-shots, validity rate ≥90% on the task suite.
4. The bake-off: 3+ models/quants × 20 tasks, results table.
5. Ship one genuinely useful daily automation (e.g., downloads-folder organizer, local notes Q&A) you actually keep using.

### Stretch Goals
- Fine-tune the local model on trajectories from a frontier model doing your 20 tasks (17-01) and re-run the bake-off — quantify the distillation gain.
- Speculative decoding or a draft model for latency; report the speedup.

### Definition of Done
- [ ] 20-task suite: ≥60% success locally, with the frontier-model comparison table and failure analysis
- [ ] Tool-call validity ≥90% after hardening (before/after numbers reported)
- [ ] Airplane-mode demo: the full agent works with networking disabled
- [ ] Model bake-off table: success, speed, memory across ≥3 configurations
- [ ] One daily-use automation running for ≥1 week (show the logs)

### Concepts You'll Cement
What the model actually contributes vs. the harness (Phases 1–3), tool-calling internals you never see behind polished APIs, quantization/serving tradeoffs, and capability-boundary judgment — knowing *when* a small model is enough is a superpower for cost engineering everywhere else.

---

## 06. Capstone: A Multi-Agent Research Team

**GOAL:** Coordinate specialist agents into a team that produces something none of them could alone — and prove the coordination earns its token bill.

### What You'll Build
A team that takes a hard open question ("Should our startup build on stack A or B?", "What's the strongest case for and against X?") and produces a decision document via specialist roles: a **planner** decomposing the problem, two **researchers** working opposing sides (your Capstone-03 machinery, reused), a **critic** attacking drafts for weak evidence and logical gaps, and a **synthesizer** producing the final recommendation with explicit uncertainty. An orchestrator owns state, budgets, and the workflow; agents exchange typed artifacts, not chat.

### Requirements
- Typed artifact handoffs (research pack, critique with severity-tagged items, draft versions) — no shared free-form transcript between agents.
- The critic is adversarial by construction: separate context, cannot edit, must produce falsifiable objections tied to specific claims; drafts iterate until critic severity drops below threshold or the round budget (≤3) is hit.
- Opposing-side research: the two researchers get explicitly opposed briefs; the synthesizer must address the strongest version of both.
- Global budget enforcement across all agents (dollars and wall-clock) with graceful early synthesis on exhaustion.
- The ablation: the same questions run through (a) single agent, same total budget, (b) the team without the critic, (c) the full team — scored blind on a rubric.

### Milestones
1. Orchestrator + typed artifacts working with stub agents (deterministic fakes) — test the machine before adding minds.
2. Planner + two researchers integrated; opposing briefs produce genuinely different evidence.
3. Critic loop: measure draft quality before/after critique rounds on 5 questions.
4. Synthesizer with explicit uncertainty sections ("what would change this recommendation").
5. The ablation study across 10 questions; write up which configuration wins where, at what cost.

### Stretch Goals
- Dynamic team sizing: the planner decides how many researchers a question needs; measure cost/quality vs. fixed topology.
- Human-in-the-loop checkpoint: a human can redirect after the research phase; measure how often redirection changes the conclusion.

### Definition of Done
- [ ] Full team beats the equal-budget single agent on blind rubric scores across 10 questions (or you report honestly that it didn't, and why)
- [ ] Critic ablation quantified: rubric delta with and without
- [ ] No agent ever sees another's raw transcript — artifacts only (verify in traces)
- [ ] Budget exhaustion mid-run produces a coherent early synthesis, not a crash
- [ ] Total cost per document ≤$3 with per-agent breakdown

### Concepts You'll Cement
Orchestration topologies and context isolation (multi-agent phase), artifact-based handoffs (case 18-10), adversarial verification, budget governance across agents (16-02) — and the discipline of *proving* multi-agent value with ablations instead of assuming it, because the single strong agent is a brutal baseline.

---

## 07. Capstone: An Eval Harness with a Leaderboard

**GOAL:** Build the measurement infrastructure every other capstone secretly depends on — task suites, graders, statistical honesty, and a leaderboard that updates itself.

### What You'll Build
A general agent-eval harness: define task suites in YAML/JSON (setup, task, grading spec), run any agent configuration against them in isolated environments with N repetitions, grade with programmatic checkers and calibrated LLM judges, store every run, and serve a static leaderboard site with scores, confidence intervals, cost, and latency — regenerated on every run. Then dogfood it: put your other capstone agents (and 2–3 model/prompt variants) on the board.

### Requirements
- Task format supports three grader types: exact/programmatic check, rubric-scored LLM judge, and trajectory assertions (e.g., "must not call effectful tools", "≤15 turns").
- Judge calibration: a 30-item human-labeled set; report judge-human agreement and don't ship a judge below your agreement bar (e.g., 85%).
- Statistical honesty: N≥5 runs per (agent, task); report mean ± bootstrap confidence interval; the leaderboard visually flags non-significant differences between neighbors.
- Isolation: each run in a fresh sandbox; full trace captured per run, linked from the leaderboard (click a score → see the trajectories).
- Regression mode: `harness gate --baseline <run-id>` exits nonzero on significant regression — usable in CI (16-06).

### Milestones
1. Task format + runner: one suite (10 tasks), one agent, programmatic grading, repetitions.
2. LLM judge + the calibration study (this will humble your judge prompt).
3. Storage + static leaderboard generation with CIs and cost columns.
4. Trace linking: every cell on the board drills down to real trajectories.
5. Dogfood: ≥3 agent configurations across ≥2 suites; write up one surprising result the numbers exposed.
6. CI gate mode wired into one of your other capstone repos.

### Stretch Goals
- Pairwise-preference mode (judge compares two agents' outputs head-to-head, Bradley-Terry ranking) alongside absolute scores; note where the two rankings disagree.
- Public deployment with a submission format so someone else can add their agent.

### Definition of Done
- [ ] 2+ suites, 25+ total tasks, all three grader types in use
- [ ] Judge-human agreement ≥85% on the calibration set, documented
- [ ] Every leaderboard score shows N, CI, cost, and links to traces
- [ ] The gate command correctly passes a no-change run and fails a deliberately sabotaged one (test both)
- [ ] A documented surprising finding from dogfooding — evidence the harness sees what eyeballs missed

### Concepts You'll Cement
Everything from Phase 9 (evals, judges, calibration) made industrial; variance and statistical rigor most people skip; observability integration (16-01); regression gating (16-06). Measurement infrastructure is the highest-leverage code in the whole field — labs win with it, and so will you.

---

## 08. Capstone: The Grand Agent (Your Design, Defended)

**GOAL:** Design and ship an agent of your own conception, end to end — then defend it like a staff engineer: design doc, review, honest evaluation, postmortem.

### What You'll Build
Your call — that's the point. Pick a real problem you personally have (the best forcing function for honesty), design it with the Phase 18 method, build it with production discipline, and run it on real usage for at least two weeks. Scope bar: it must involve tools with real effects, some form of memory or state, and at least one hard sub-problem you can name in advance. Examples for calibration (don't copy them): an agent that manages your open-source repo's issue triage; a personal finance analyst over your actual statements; an agent that maintains your home lab.

### Requirements
- A design doc *before code*, in the Phase 18 format: requirements, napkin math (with arithmetic someone can check), architecture diagram, deep dives on the 2–3 hardest problems, tradeoffs table with rejected alternatives.
- A design review: present the doc to at least one other person (or a rigorous red-team session with a frontier model playing hostile reviewer); log the objections and your responses; change something because of it.
- Production discipline, actually applied: traces on every run, budgets enforced, effectful tools idempotent and gated, a golden-set regression gate, and the 16-12 readiness checklist completed with evidence.
- Two weeks of real operation: real tasks, real failures, a maintained incident log.
- The defense: a final report — what you predicted vs. what happened, eval results, cost reality vs. napkin math, the worst failure and its fix, and what you'd redesign.

### Milestones
1. Problem selection + design doc (the napkin math will kill half your ideas — good).
2. Design review; revise the doc; commit to scope.
3. Build the core loop and tools; first real task completed.
4. Production hardening: pass your own readiness checklist (16-12), no waived items without written justification.
5. Two-week operation window; incident log; at least one prompt/design revision driven by the golden set.
6. Final report + defense presentation.

### Stretch Goals
- Ship it to one real user who isn't you and survive their first week.
- Open-source it with docs good enough that a stranger files a useful issue.

### Definition of Done
- [ ] Design doc predates the code (commit history proves it) and includes checkable napkin math
- [ ] Review objections logged, with at least one design change traced to them
- [ ] Readiness checklist complete with evidence links (traces, test runs, chaos test)
- [ ] ≥2 weeks of real usage: ≥20 real tasks, incident log, cost actuals vs. estimate compared
- [ ] Final report names the worst failure honestly and shows the fix's before/after evals
- [ ] You can answer "why is this an agent and not a script?" convincingly — or you've written the braver conclusion that a script would have done fine

### Concepts You'll Cement
All of it — but especially the meta-skills no single phase teaches: scoping under napkin math, defending design decisions under challenge, operating what you built, and telling the truth about the results. That last one is the difference between someone who has read about agents and someone you'd trust to ship one.
