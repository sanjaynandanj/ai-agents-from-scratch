# Phase 02 — 🔄 The Agent Loop

> Every agent framework is 100 lines of while-loop wearing a trench coat.

Phase 0 gave you the mental model; Phase 1 gave you the engine. Now you build the transmission: the loop that turns one-shot LLM calls into an agent. This phase covers the canonical ReAct pattern, then hardens it piece by piece — stop conditions, error handling, reflection, budgets, streaming, human gates — until Lesson 10, where you assemble everything into a complete, runnable, zero-API-key agent. By the end, you'll read any framework's source and recognize old friends.

## 01. ReAct: Reason, Act, Observe

**MOTTO:** Make the model narrate its plan before every move — the narration is free error-checking.

### The Problem

Give an LLM tools and let it fire actions directly, and it acts on stale assumptions: calling tools that don't fit, chaining actions that made sense two observations ago. Give it only reasoning and it hallucinates the facts it was supposed to look up. Each mode alone fails in a characteristic way — confident action without grounding, or grounded reasoning without hands.

### The Concept

ReAct (Yao et al., 2022) interleaves the two: every turn, the model emits a **Thought** (free-text reasoning about the current state), then an **Action** (a tool call), then receives an **Observation**. Chain-of-thought (Phase 1, Lesson 06) with its feet on the ground.

```
  Thought: I need France's population before I can halve it.
  Action:  lookup[population of France]
  Observation: 68,000,000 (approx., 2024)
  Thought: Now divide by 2. The commas will break the calculator; strip them.
  Action:  calculator[68000000 / 2]
  Observation: 34000000.0
  Thought: Done.
  FINAL:   About 34 million.

  ── the Thought line is where the model course-corrects using
     the LAST observation before committing to the NEXT action.
```

The paper's finding: reasoning-only (CoT) hallucinated facts; acting-only made ungrounded moves; interleaving beat both on HotpotQA and Fever (fact-checking, grounded via a Wikipedia API) and on interactive tasks (ALFWorld, WebShop). The thought isn't decoration — it's the synthesis step between perception and action.

### Build It

1. Prompt format: teach the exact grammar, ideally with one full few-shot turn (Phase 1, Lesson 05): `Thought: ...` then `Action: tool[input]`, and `FINAL: ...` to finish.
2. Parse with a strict regex; anything unparseable becomes an observation saying so (Lesson 04).
3. Append the model's full output *and* the observation to the transcript — the thoughts must persist, they're the agent's running plan.
4. Modern variant: with native function calling (Phase 1, Lesson 08), the "Action" is a structured tool call, and the "Thought" is the text (or reasoning block) accompanying it. Same pattern, better parser.

### Use It

ReAct is the default skeleton nearly everywhere: LangChain's original agents were literally named after the paper (`zero-shot-react-description`), and today's tool-calling loops in the OpenAI Agents SDK, Claude's tool use, and smolagents are ReAct with structured actions. When choosing a framework, ask how it exposes the three beats — if you can't see thoughts and observations in the trace, debugging (Phase 0, Lesson 07) gets strictly harder.

### War Story

ReAct (Yao et al., 2022, published at ICLR 2023) reported that on Fever fact verification, interleaved reasoning-and-acting outperformed both chain-of-thought-only and act-only baselines, with CoT-only prone to fact hallucination it could not check. The pattern was so legible that LangChain — the breakout agent library of 2023 — shipped it as the default agent, which is how a research prompt format became the industry's while-loop.

### Checkpoint

- What failure mode does reasoning-only exhibit, and what failure mode does acting-only exhibit?
- Why must Thought lines be kept in the transcript rather than discarded after parsing?
- How does the ReAct pattern map onto native function calling?

## 02. The Scratchpad: An Agent's Working Memory

**MOTTO:** The transcript is RAM; the scratchpad is the notebook that survives the pager.

### The Problem

By turn 18, your agent's transcript holds three file dumps, five dead-end explorations, and — somewhere in the middle — the two facts that matter. Context costs are climbing (Phase 1, Lesson 12), attention is diluting (Phase 1, Lesson 01), and when you eventually compact history, you'd better not compact away the answer. The transcript is a *log*; what the agent needs is *notes*.

### The Concept

A scratchpad is a distinct, curated store of working state — separate from the raw conversation. The transcript records everything that happened; the scratchpad records what's *worth remembering*: goals, confirmed facts, decisions, open questions.

```
  TRANSCRIPT (append-only log)          SCRATCHPAD (curated state)
  ├ turn 1: read config… 4KB dump      ┌─────────────────────────────┐
  ├ turn 2: grep… 2KB, dead end        │ GOAL: fix failing test #12  │
  ├ turn 3: read test… 3KB             │ FACTS: bug in parse_date(), │
  ├ …                                  │   introduced in commit a1c  │
  └ turn 18: …                         │ TRIED: regex fix — broke #7 │
       │                               │ NEXT: widen format list     │
       └── compactable, lossy          └── small, dense, durable ────┘
```

Two implementations: **in-context** (a maintained summary block the agent rewrites, always pinned in the prompt) and **externalized** (a file or store the agent writes/reads via tools — surviving compaction, and even sessions). Writing notes is also thinking: forcing the agent to distill "what do I now know?" is a comprehension checkpoint, not just storage.

### Build It

1. Give the agent two tools: `write_note(text)` and `read_notes()` — or simpler, one `notes.md` file via generic file tools.
2. Instruct it in the system prompt: after any significant observation, record conclusions (not raw output) in notes; consult notes before planning.
3. On compaction (Phase 1, Lesson 09), drop raw transcript freely — the scratchpad is what you keep verbatim.
4. Structure beats prose: `GOAL / FACTS / TRIED / NEXT` headings make notes greppable by the agent and by you at trace-reading time.
5. Anti-pattern to police: the agent dumping raw tool output into notes. Notes are *distilled* — enforce a length budget.

### Use It

| Approach | Survives compaction? | Survives sessions? | Cost |
|---|---|---|---|
| Thoughts in transcript only | No | No | Free |
| Pinned in-context summary block | Yes (you pin it) | No | Tokens every turn |
| External file/store via tools | Yes | Yes | Tool-call turns |

Production tools converged here: Claude Code reads `CLAUDE.md` memory files and writes plan/note files during long tasks, and Anthropic's agent guidance explicitly lists note-taking outside the context window as a core context-management technique. The file system is the most underrated memory architecture in agents.

### War Story

Anthropic's own engineering guidance on context management (2025) describes agentic memory as "taking notes that persist outside the context window" — citing an agent playing Pokémon that maintained tallies and maps across thousands of steps far exceeding any context window. The industry's most advanced answer to long-horizon memory is, sincerely, "the agent keeps a notebook."

### Checkpoint

- What's the difference in *purpose* between the transcript and the scratchpad?
- Why does an external scratchpad make history compaction safe?
- Why is "distill, don't dump" a rule worth enforcing with a length budget?

## 03. Stop Conditions: Knowing When to Quit

**MOTTO:** An agent that can't stop isn't autonomous — it's unattended.

### The Problem

Your loop's exit is `if "FINAL:" in response` — a string the model may never produce. Maybe it keeps "double-checking." Maybe it finished the task and moved on to unrequested improvements. Maybe it's stuck re-verifying forever. Termination is not a behavior models come with; it's a mechanism you design, and a missing one turns every edge case into an infinite loop.

### The Concept

Stop conditions come in three families, and a production loop needs all three:

```
  ┌─ 1. SUCCESS ────── the model signals done (FINAL:, a submit() tool,
  │                    or a text-response-with-no-tool-call turn)
  ├─ 2. VERIFIED ───── an external check confirms done (tests pass,
  │                    file exists, validator accepts) — the strong form
  └─ 3. GUARDRAIL ──── you stop it regardless: max turns, max cost,
                       wall-clock timeout, repeated-action detector

  precedence: guardrails ALWAYS enforce; verification gates success;
  model signal alone is the WEAKEST evidence of doneness.
```

The deep issue: the model's "I'm done" is a claim, not a fact (premature victory, Phase 0, Lesson 05). Wherever a programmatic check exists, doneness should be *verified*, not declared — "stop when the tests pass," not "stop when the model says the tests would pass."

### Build It

1. Make stopping explicit and easy: a dedicated `finish(answer)` tool (or `FINAL:` sentinel) beats inferring doneness from prose.
2. Gate it: when `finish` is called, run your checker; on failure, don't stop — return the checker's output as an observation ("2 tests still failing") and continue.
3. Layer guardrails outside the model's control: `for turn in range(max_turns)` (never `while True`), a cost ceiling (Phase 1, Lesson 12), a duplicate-action detector.
4. Distinguish exits in your result object: `success_verified`, `success_claimed`, `budget_exhausted`, `stuck`. Downstream code and your evals must treat these differently.

```python
if action.tool == "finish":
    ok, report = checker(task)
    if ok: return Result("success_verified", action.args)
    observation = f"Not done: {report}"     # back into the loop
```

### Use It

Frameworks encode family 1 and 3 for you: OpenAI's Agents SDK ends a run when the model produces a final text output and enforces `max_turns`; LangGraph ships a recursion limit (default 25) that raises `GraphRecursionError`. Family 2 — verification — is domain-specific and almost always yours to write. It's also the highest-leverage line of code in the whole loop.

### War Story

AutoGPT's own 2023 documentation warned that its "continuous mode" was "potentially dangerous" and could "run forever" — an agent shipped with an explicit disclaimer that its stop conditions were the user watching it. Thousands of users ran it anyway and reported agents circling indefinitely on subgoals; "how do I make it stop researching and start doing" became a genre of GitHub issue. Termination is a feature; absence of termination is a warning label.

### Checkpoint

- Rank the three stop-condition families by strength of evidence that the task is actually done.
- Why should a `finish` call be gated by a checker rather than trusted?
- Why is `for turn in range(N)` non-negotiable even when you also have cost limits?

## 04. Error Handling Inside the Loop

**MOTTO:** Inside an agent loop, an exception isn't a crash — it's an observation.

### The Problem

Turn 7: the model calls `search` with malformed arguments, your tool raises, the exception propagates, and the whole run — six turns of paid, correct progress — dies. Or worse: your code catches the error silently, returns nothing, and the model, seeing no pushback, assumes the action worked. Traditional error handling (crash or swallow) is exactly wrong for agents.

### The Concept

The loop is a conversation with an entity that can *read error messages and adapt*. So route errors back into the transcript as observations, written for a model audience:

```
                     ┌──────────────┐
   action ──────────►│   dispatch   │── ok ──► Observation: <result>
                     │  (validate,  │
                     │   execute,   │── err ─► Observation: Error: unknown tool
                     │   timeout)   │          'serch'. Available: search, read_file.
                     └──────────────┘          Did you mean 'search'?
                                                    │
        model reads the error, corrects, retries ◄──┘

  Error message quality = recovery probability. "Error 500" teaches nothing;
  "file not found: ./config.yml — directory contains: config.yaml" teaches everything.
```

Distinguish error classes: **model errors** (bad tool name, bad args, unparseable output) — always recoverable, feed back with guidance; **environment errors** (timeout, 404, permission denied) — feed back with what's known, maybe retry idempotent calls yourself; **infrastructure errors** (LLM API down, budget breached) — the loop itself must handle these; the model can't reason its way around a dead API.

### Build It

1. Wrap every tool call: `try/except` with a timeout; *nothing* a tool does should escape the dispatch layer.
2. Validate before executing (name in registry, args against schema) — cheaper than executing and failing.
3. Write errors as actionable observations: what failed, why, what's available, a suggestion.
4. Add a repeat detector: same action + same error twice → inject "This approach has now failed twice. Try a different one." Models anchor on their own transcript; sometimes you must break the anchor.
5. Cap error recovery: N consecutive failed turns → exit as `stuck` with the trace. Infinite resilience is just a slow infinite loop.
6. For transient environment errors (rate limits, flaky HTTP), retry with backoff *below* the model's awareness — don't waste model turns on jitter.

### Use It

Anthropic's "Building Effective Agents" (2024) calls the tool layer an **agent-computer interface (ACI)** and urges investing in it like a human UI. The SWE-agent paper (Yao et al., 2024) demonstrated it empirically: redesigning the interface — concise feedback, guardrails against repeated mistakes — substantially improved software-fixing success with the *same* model. Error messages are prompts. Write them like prompts.

### War Story

SWE-agent (Yao et al., 2024) attributed much of its state-of-the-art SWE-bench performance not to a better model but to a better interface: purpose-built file viewers and editors whose feedback (including error feedback) was designed for LLM consumption, versus dropping the model into a raw shell. Same brain, kinder error messages, materially more resolved GitHub issues — the strongest published evidence that this lesson's unglamorous plumbing moves the top-line number.

### Checkpoint

- Why is "exception as observation" the right default, and for which error class does it break down?
- What makes an error message high-quality from the model's perspective?
- Why do you need both a repeat detector and a consecutive-failure cap?

## 05. Reflection: The Agent That Critiques Itself

**MOTTO:** The cheapest second opinion is the same model reading its own work with fresh instructions.

### The Problem

Your agent submits an answer that fails the checker. The loop just... tries again, with the failure in the transcript but no analysis of it — so it often repeats a near-identical attempt. The information needed to do better is present; the *processing* of that information into a lesson is missing.

### The Concept

Reflection adds an explicit self-critique step: after a failed (or completed) attempt, the model is prompted to analyze what went wrong and produce guidance for the next attempt. Reflexion (Shinn et al., 2023) formalized this: the agent attempts a task, receives feedback (test results, environment signals), generates a *verbal* reflection — "I assumed the list was sorted; it isn't; next time check first" — stores it in an episodic memory buffer, and retries with reflections in context. Verbal reinforcement learning: the lesson is a paragraph, not a gradient.

```
   attempt ──► evaluate ──► fail ──► REFLECT ──► memory ──► attempt #2
      ▲                              (why did it              │
      │                               fail? what to           │
      └────────── reflections in context ◄────────────────────┘
                  change?)

   distinct from retry: retry = same context, new dice.
   reflexion = context now contains a diagnosis.
```

Two flavors: **episodic** (between full attempts, à la Reflexion) and **inline** (mid-loop critique of a draft before submitting — generator/critic in one loop). Both hinge on the same asymmetry: models are better at *judging* a concrete artifact than at generating perfectly on the first pass.

### Build It

1. After a failed attempt, issue a dedicated reflection call — separate prompt, critic persona: "Here is the attempt and the failure evidence. Diagnose the root cause in ≤3 sentences and state one concrete change."
2. Ground it in evidence: reflection over a *test failure* is diagnosis; reflection with no external signal is often confabulation. Prefer reflecting on checker output, not vibes.
3. Store reflections in a running list; prepend on retry; cap attempts (2-3 — returns fall off fast).
4. Inline variant: before `finish`, one critique pass against an explicit rubric ("check: edge cases, off-by-one, spec compliance"), then revise once.
5. Caveat honestly: self-critique without new information can degenerate into the model agreeing with itself. External feedback is the active ingredient; reflection is the metabolizer.

### Use It

| Pattern | Signal source | Cost | When |
|---|---|---|---|
| Plain retry | None | 1x per attempt | Transient/randomness failures |
| Reflexion-style | Tests/env feedback | +1 reflection call per attempt | Checkable tasks (code, math) |
| Inline critic pass | Rubric | +1 call before finish | Quality-sensitive output |
| Separate critic model | Second model | 2 models | Adversarial review, evals |

### War Story

Reflexion (Shinn et al., 2023) reported 91% pass@1 on the HumanEval coding benchmark with GPT-4 — surpassing the previously reported GPT-4 baseline of 67% — with no weight updates, purely by letting the agent read its own test failures, write itself a memo, and try again. Few published results make the case this cleanly that the loop's *structure*, not the model, was the binding constraint.

### Checkpoint

- What distinguishes Reflexion-style retry from naive retry, mechanically?
- Why does reflection work best when anchored to external feedback like test output?
- Why cap reflection-retry cycles at 2-3 attempts?

## 06. Self-Consistency: Ask Three Times, Take the Vote

**MOTTO:** One sample is an anecdote; five samples and a vote is a measurement.

### The Problem

On genuinely hard reasoning steps, your model is right 70% of the time — and you're sampling it once, at some temperature, and shipping whatever comes out. A 30% error rate on a load-bearing step, injected into a compounding loop (Phase 0, Lesson 05), is a slow-motion disaster you're choosing per-call cheapness over.

### The Concept

Self-consistency (Wang et al., 2022): sample the same prompt multiple times at nonzero temperature, extract each sample's final answer, and take the majority vote. The intuition — correct reasoning paths are many and convergent (different routes, same destination); errors are diverse and scattered. Sampling diversity turns that asymmetry into signal.

```
  prompt ──┬── sample 1 (T=0.7) ──► reasoning A ──► "34,000,000" ─┐
           ├── sample 2 (T=0.7) ──► reasoning B ──► "34,000,000" ─┼─► vote:
           ├── sample 3 (T=0.7) ──► reasoning C ──► "3,400,000"  ─┤   34,000,000
           ├── sample 4 (T=0.7) ──► reasoning D ──► "34,000,000" ─┤   (4/5) ✓
           └── sample 5 (T=0.7) ──► reasoning E ──► "34,000,000" ─┘
                                        errors scatter; truth clusters.
  BONUS: the vote margin (4/5 vs 3/5) is a free confidence signal.
```

Requirements: temperature > 0 (identical greedy samples can't vote — Phase 1, Lesson 02), and an extractable, *comparable* final answer (a number, a choice, a normalized string). For free-form prose there's no clean vote; use a judge/critic instead (Lesson 05).

### Build It

1. Isolate the load-bearing decision (the plan choice, the numeric answer, the classification) — don't self-consistency the whole trajectory.
2. Sample k=3-10 at T≈0.7, in parallel (latency ≈ one call; cost = k calls).
3. Extract answers via your delimiter (Phase 1, Lesson 06: `ANSWER:` exists for this), normalize, `Counter(...).most_common(1)`.
4. Use the margin: unanimous → proceed; split vote → escalate (more samples, stronger model, or a human gate — Lesson 09).
5. Budget honestly: k=5 is 5x that step's cost. Reserve it for steps whose failure is expensive; this is precision spending, not a default.

```python
answers = parallel(lambda: extract(llm(prompt, temperature=0.7)), k=5)
winner, count = Counter(answers).most_common(1)[0]
confidence = count / len(answers)
```

### Use It

The idea generalizes across the modern stack: best-of-n with a verifier or reward model picking the winner, and consult-multiple-models patterns all trade parallel samples for reliability. Within agents, the highest-leverage placements are plan selection at the start of a run and final-answer checks on quantitative tasks — the steps where one wrong draw poisons everything downstream.

### War Story

Wang et al. (2022) reported that self-consistency boosted chain-of-thought accuracy on GSM8K math by +17.9 percentage points, with large gains on other reasoning benchmarks — no new model, no new training, just "sample several and vote." It remains one of the best accuracy-per-engineering-hour trades in the literature: about five lines of orchestration code.

### Checkpoint

- Why does self-consistency require temperature > 0?
- Why does majority voting work — what asymmetry between correct and incorrect paths does it exploit?
- Where in an agent loop is the k-times cost of self-consistency most justified?

## 07. Turn Budgets and Runaway Loops

**MOTTO:** Automation without a kill switch isn't a system — it's a stampede.

### The Problem

The agent hits a state its prompt never anticipated: a tool that always errors, a task that's subtly impossible, a transcript that anchors it into repeating itself. Without hard limits, it will burn turns — and money — indefinitely, because an LLM under anchoring pressure is perfectly happy to try the same thing an eleventh time. Stop conditions (Lesson 03) defined the families; this lesson engineers the guardrail family properly, because it's the one that runs when everything else has already failed.

### The Concept

Layered limits, each catching what the previous misses:

```
  per-turn:    tool timeout, max output tokens        (catches: one hung call)
  per-run:     max turns, max cost, wall clock        (catches: runaway loop)
  cross-run:   daily spend cap, concurrency cap       (catches: runaway RETRIES —
                                                       the outer system relaunching
                                                       a failing agent forever)
  ┌────────────────────────────────────────────────┐
  │ the failure that hurts is never the loop alone │
  │ — it's the loop × the scheduler that respawns  │
  │ it × the night nobody was watching.            │
  └────────────────────────────────────────────────┘
```

Runaway detection is subtler than a counter, because loops are often *semantic*: the agent alternates A→B→A→B, or rephrases the same failing search eight ways. Progress, not motion, is the thing to measure.

### Build It

1. Turn budget sized empirically: p95 turns of *successful* runs on your eval set, plus slack. Too tight starves legitimately hard tasks; too loose funds doom loops.
2. Cycle detector: hash each (tool, normalized_args); a hash seen ≥3 times, or ≥2 with identical failing observations, triggers intervention.
3. Escalating intervention ladder — don't jump straight to kill: (a) inject a nudge observation ("you have repeated this action; change strategy"), (b) force a reflection turn (Lesson 05), (c) terminate as `stuck` with the trace.
4. Warn the model near budget end: "3 turns remain — wrap up with your best current answer." Models finish gracefully when told; guillotined runs return nothing.
5. Enforce cost/time in the loop body itself (the `Budget` class, Phase 1, Lesson 12) — never in a sidecar that observes but can't halt.

### Use It

Every serious harness exposes the per-run layer — `max_turns` (OpenAI Agents SDK), recursion limits (LangGraph), max iterations (nearly all others). The cross-run layer is almost always missing from frameworks and almost always where real incidents live: it's provider spend alerts, queue-level concurrency caps, and your own retry policy having a ceiling. Configure all three layers; test the guardrails by deliberately giving the agent an impossible task and watching what happens.

### War Story

The canonical runaway-automation parable predates LLMs: on August 1, 2012, Knight Capital deployed trading software with a repurposed feature flag that activated dead code, and the system fired unintended orders for about 45 minutes — losing roughly $440 million and nearly destroying the firm — because no layer existed that could recognize "this is wrong" and halt. Agent loops inherit the same physics: the cost of a runaway is set not by the bug but by how long nothing stops it.

### Checkpoint

- What failure class does each of the three limit layers catch that the others miss?
- Why is a semantic cycle detector needed in addition to a turn counter?
- Why warn the model before the turn budget expires instead of just terminating?

## 08. Streaming and Interruptibility

**MOTTO:** Users forgive slowness they can watch; they don't forgive a spinner hiding a mistake in progress.

### The Problem

Your agent takes 60 seconds across six turns. Rendered as one silent spinner, that's an eternity — users assume it hung, refresh, and now two agents are mutating the same data. Worse: at turn 2 the user can already *see* the agent misread the task, and there's no way to stop it before it acts five more times on the wrong premise.

### The Concept

Two distinct capabilities, often conflated:

```
  STREAMING (visibility)                 INTERRUPTIBILITY (control)
  tokens/events emitted as produced      run can be stopped/redirected mid-flight
  ──────────────────────────────         ──────────────────────────────
  UI: "Thought: checking the            UI: [ ■ stop ]  "wait — use the
       invoice table…"                        staging DB, not prod"
  cuts PERCEIVED latency                 cuts WASTED WORK and BLAST RADIUS
  (TTFT ~1s vs total 60s)
        └────────────── streaming is what MAKES timely interruption
                        possible: you can't stop what you can't see ─┘
```

For agents, stream *semantic events*, not just tokens: turn started, thought text, tool called with args, observation received, final answer streaming. And interruption has a hard rule inherited from systems programming: **interrupt at action boundaries.** Killing a run mid-tool-execution can leave the environment half-mutated; the safe points are before dispatch and after observation.

### Build It

1. Restructure the loop as a generator: `yield Event("thought", ...)`, `yield Event("tool_call", ...)`, `yield Event("observation", ...)` — the UI consumes events; the loop doesn't know about UIs.
2. Check a cancellation flag at every action boundary: before dispatching a tool and before starting the next turn.
3. On cancel: finish or roll back the in-flight tool if possible, persist the transcript + scratchpad, exit as `interrupted` — resumable, not vaporized.
4. Support *redirect*, not just stop: user input mid-run is appended as a new user message; the next turn's context includes it. (This is how "actually, use staging" steers a live run.)
5. Transport: provider APIs stream via server-sent events (SSE); pass through with your semantic events layered on top.

### Use It

Streaming has been table stakes since ChatGPT's launch UX (November 2022): token-by-token rendering plus a stop-generation button. Agent frameworks now expose event streams (Agents SDK streaming events, LangGraph's `stream` modes yielding node-level updates). The frontier of this lesson is voice: OpenAI's Realtime API (October 2024) had to handle *barge-in* — the user talking over the model — making interruption a first-class protocol event, with the model's unspoken audio truncated from history. Interruptibility, it turns out, is an API design problem all the way down.

### War Story

OpenAI's Realtime API (announced at DevDay, October 2024) shipped interruption handling as a core primitive for speech-to-speech apps — because in voice, users *naturally* interrupt, and a model that talks over them is unusable regardless of intelligence. When a modality forces the issue, the answer is instructive: interruption support was built into the protocol itself, not bolted onto the UI. Text agents deserve the same architecture.

### Checkpoint

- Distinguish what streaming buys you from what interruptibility buys you.
- Why must interruption happen at action boundaries rather than at arbitrary moments?
- What should be persisted on interruption, and why does that make `interrupted` different from `failed`?

## 09. Human-in-the-Loop Gates

**MOTTO:** Autonomy is earned per action, not granted per agent.

### The Problem

Your agent is 95% reliable. Its actions include "read a file" and "email 4,000 customers." Treating those uniformly means either paralyzing the agent with confirmations for trivial reads, or discovering the 5% failure rate via an apology campaign. The unit of trust is wrong: it's not the agent that deserves autonomy or not — it's each *action*.

### The Concept

Classify every tool by reversibility and blast radius; gate accordingly:

```
                low blast radius        high blast radius
  reversible    ✓ auto-approve          ⚠ auto + audit log
                (read file, search)     (bulk edit w/ undo)
  irreversible  ⚠ confirm or sandbox    ⛔ HARD GATE: human
                (send one email,        approves the CONCRETE
                 small payment)         action + args
                                        (deploy, delete, mass send)

  gate = loop PAUSES: (proposed action, args, context) → human
         → approve | edit args | reject-with-reason → loop resumes
  A rejection is an observation too: "Rejected: wrong recipient list."
```

Design constraint that decides whether this works in practice: **approval fatigue**. A gate that fires 50 times a run trains the human to click yes — at which point you have ceremony, not safety. Gates must be rare, high-signal, and rich in context (what, why, what happens if approved).

### Build It

1. Tag tools at registration: `risk="auto" | "confirm" | "hard_gate"` — policy lives in the tool registry, not scattered through prompts.
2. Implement the pause: the loop yields an `approval_request` event (Lesson 08's event stream) and blocks — or, for async workflows, checkpoints state and resumes on decision, hours later if need be.
3. Feed decisions back as observations — especially rejections with reasons; "Rejected: that's the prod database" is steering data (and scratchpad material).
4. Batch approvals where natural: "here are the 3 emails I propose to send" beats three interruptions.
5. Log every approval with the exact args approved. When something goes wrong anyway, "human approved *this specific action*" versus "agent acted alone" is the whole incident review — and increasingly, the whole legal question.
6. Escalation hooks: low vote-confidence (Lesson 06), repeated failures (Lesson 07), and budget-end (Lesson 07) are all natural triggers to *promote* an action to a gate dynamically.

### Use It

Framework support is real but thin: LangGraph has first-class `interrupt`/checkpoint primitives for human approval; the OpenAI Agents SDK and Claude-based harnesses support tool-approval callbacks; Claude Code prompts before running commands it classifies as consequential. The classification of *your* tools' blast radius, though, is judgment no framework ships. Do the 2×2 for every tool you register.

### War Story

In July 2025, an AI coding agent on Replit deleted a production database during a "code freeze" for SaaStr founder Jason Lemkin's project — an incident Replit's CEO publicly called "unacceptable," followed by announced safeguards including better separation of development and production environments. The action was irreversible, high-blast-radius, and ungated. The 2×2 in this lesson is cheap; the incident review isn't.

### Checkpoint

- What two properties of an action determine its gate level, and why per-action rather than per-agent?
- Why is approval fatigue a *safety* problem and not just a UX problem?
- How should a human rejection flow back into the loop, and what makes a rejection valuable?

## 10. Build a Complete Agent Loop in 100 Lines

**MOTTO:** If you can't build it in 100 lines, you don't get to import it in one.

### The Problem

You've now met every organ: ReAct format, transcript-as-memory, stop conditions, error-as-observation, budgets. Separately, each is a paragraph. The proof of understanding is assembly: one file, no framework, no API key, that runs an agent end to end — and that you can read a trace from, break on purpose, and fix.

### The Concept

The full anatomy, and where each prior lesson lives in it:

```
  ┌── agent.py ─────────────────────────────────────────────┐
  │  MockLLM        (Phase 0 L08: deterministic brain)      │
  │  tools          (Phase 0 L04: calculator, lookup)       │
  │  parse()        (L01 ReAct grammar; P1 L07 rigor)       │
  │  run_agent()    (P0 L03 loop · L03 stops · L04 errors   │
  │                  · L07 turn budget · trace printing)    │
  └─────────────────────────────────────────────────────────┘
```

### Build It

Save as `agent.py`, run `python agent.py`. No keys, no network, fully deterministic.

```python
"""A complete agent loop in ~100 lines. Zero API keys. Run: python agent.py"""
import re

# ---------- The "brain": a mock LLM with scripted responses (Phase 0, L08) ----------
class MockLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []                       # full prompts, for trace-reading practice

    def complete(self, prompt: str) -> str:
        self.calls.append(prompt)
        if not self.responses:
            raise RuntimeError("MockLLM ran out of script — is your loop over-turning?")
        return self.responses.pop(0)

# ---------- Tools (Phase 0, L04): name -> function, str in, str out ----------
def calculator(expression: str) -> str:
    if not set(expression) <= set("0123456789+-*/(). "):
        return f"Error: calculator only accepts digits and + - * / ( ). Got: {expression!r}"
    try:
        return str(eval(expression, {"__builtins__": {}}, {}))    # sandboxed eval
    except Exception as e:
        return f"Error: {e}"

FACTS = {
    "population of france": "68,000,000 (approx., 2024)",
    "capital of france": "Paris",
}
def lookup(query: str) -> str:
    return FACTS.get(query.strip().lower(), f"Error: no entry for {query!r}. Try a simpler query.")

TOOLS = {"calculator": calculator, "lookup": lookup}

# ---------- Parsing the ReAct grammar (L01): Action: tool[input] | FINAL: answer ----------
ACTION_RE = re.compile(r"Action:\s*(\w+)\[(.*)\]", re.DOTALL)

def parse(response: str):
    if "FINAL:" in response:
        return "final", response.split("FINAL:", 1)[1].strip()
    m = ACTION_RE.search(response)
    if m:
        return "action", (m.group(1), m.group(2).strip())
    return "invalid", None

# ---------- The loop (Phase 0 L03; stops L03; errors L04; budget L07) ----------
def run_agent(task: str, llm: MockLLM, max_turns: int = 6) -> str:
    transcript = [f"Task: {task}"]
    for turn in range(1, max_turns + 1):                 # guardrail: never while True
        response = llm.complete("\n".join(transcript))   # THINK: full history in
        transcript.append(response)
        print(f"--- turn {turn} ---\n{response}")

        kind, payload = parse(response)
        if kind == "final":                              # model claims done
            print(f"=== FINAL after {turn} turn(s) ===")
            return payload

        if kind == "action":                             # ACT
            tool_name, arg = payload
            if tool_name in TOOLS:
                try:
                    observation = TOOLS[tool_name](arg)  # errors stay inside dispatch
                except Exception as e:
                    observation = f"Error: {tool_name} crashed: {e}"
            else:                                        # model error -> teachable obs
                observation = (f"Error: unknown tool {tool_name!r}. "
                               f"Available: {', '.join(TOOLS)}.")
        else:                                            # unparseable -> teachable obs
            observation = ("Error: could not parse. Reply with "
                           "'Action: tool[input]' or 'FINAL: answer'.")

        transcript.append(f"Observation: {observation}") # OBSERVE
        print(f"Observation: {observation}")
    return "Stopped: turn budget exhausted (best-effort trace above)."

# ---------- The script: what our deterministic "model" says, turn by turn ----------
SCRIPT = [
    "Thought: I need France's population before I can halve it.\n"
    "Action: lookup[population of France]",

    "Thought: Got 68,000,000 — but commas would break the calculator, so I'll strip them.\n"
    "Action: calculator[68000000 / 2]",

    "Thought: 34000000.0 — that's the answer.\n"
    "FINAL: Half of France's population is about 34,000,000 people.",
]

if __name__ == "__main__":
    llm = MockLLM(SCRIPT)
    answer = run_agent("What is half the population of France?", llm)
    print(f"\nAnswer: {answer}")
    print(f"LLM was called {len(llm.calls)} time(s); "
          f"final prompt was {len(llm.calls[-1])} chars (watch this grow — Phase 1, L12).")
```

Exercises, in ascending order of insight: (1) misspell `lookup` as `lookupp` in the script and watch the error-observation path run — then add a fourth scripted response that recovers; (2) delete the `FINAL` response and watch the turn budget catch it; (3) print `llm.calls[-1]` and read the exact context the "model" saw — that's Phase 0 L07 made tangible; (4) replace `MockLLM` with a real client behind the same `complete()` interface and change nothing else.

### Use It

Now open a framework and find these same ~100 lines: smolagents' agent step loop, the Agents SDK's runner, LangGraph's compiled graph loop. Everything they add — retries, streaming events, checkpointing, tool schemas — you now have a slot for in your mental model. That's the point of the trench-coat joke: the coat is real and sometimes worth wearing, but you should always know what's under it.

### War Story

BabyAGI (Yohei Nakajima, spring 2023) went viral as a task-driven autonomous agent implemented in roughly a hundred lines of Python — tiny enough that thousands of people read the entire source in one sitting, which was precisely why it spread: everyone could see the whole trick. Hugging Face's smolagents (December 2024) made minimalism the brand promise itself — an agent library advertising its core logic in about a thousand lines. The loop is small. It was always small.

### Checkpoint

- Map each of Lessons 01, 03, 04, and 07 to the specific line(s) of `agent.py` that implement them.
- Why does the script's second response mention stripping commas, and what loop property does that demonstrate?
- What is the *only* change required to swap MockLLM for a real model, and why was the code designed that way?
