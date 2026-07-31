# Phase 06 — 🗂️ Planning & Reasoning

> Amateurs improvise. Agents that ship make plans — then revise them.

So far your agent reacts: see prompt, pick tool, repeat. That works for "what's the weather" and falls apart for "migrate this codebase to Python 3.12." This phase is about giving agents a frontal lobe — decomposition, lookahead, search, verification, and the discipline to notice when the plan is on fire. By the end you'll build a plan → execute → replan loop in raw Python, no framework required.

## 01. Task Decomposition: Big Goals Into Small Steps

**MOTTO:** You can't eat an elephant, but you can eat 400 elephant-sized bites.

### The Problem
Give an LLM "build me a landing page" as one shot and you get a mediocre average of every landing page it has seen. Big goals overflow attention, hide missing requirements, and give you no place to catch errors until the very end.

### The Concept
Decomposition turns one vague goal into an ordered list of small, verifiable steps — like a recipe instead of "make dinner."

```
GOAL: "Ship the report"
  ├── 1. Fetch sales data        (verifiable: rows > 0)
  ├── 2. Compute monthly totals  (verifiable: sums match)
  ├── 3. Render chart            (verifiable: file exists)
  └── 4. Write summary + email   (verifiable: draft reviewed)
```

Each step should be small enough that failure is obvious and cheap. If you can't say how you'd check a step, it's still too big.

### Build It
Prompt the model to emit steps as structured data, not prose:

```python
DECOMPOSE_PROMPT = """Break this goal into 3-7 concrete steps.
Return JSON: [{"id": 1, "action": "...", "done_when": "..."}]
Goal: {goal}"""
```

The `done_when` field is the trick — forcing a completion criterion per step exposes vague steps immediately.

### Use It
| Tool | How it decomposes |
|---|---|
| Claude Code | Maintains a visible todo list per task |
| LangGraph | You define nodes; the graph is the decomposition |
| CrewAI | Tasks assigned to role-based agents |

### War Story
Least-to-most prompting (Zhou et al., 2022) showed that asking the model to decompose a problem before solving each piece dramatically beat standard prompting on compositional generalization tasks like SCAN — the same model, just forced to bite smaller. Decomposition isn't a framework feature; it's a prompting-era result that still holds.

### Checkpoint
1. Why does a `done_when` criterion per step matter more than the step description itself?
2. What's the failure mode of decomposing too finely?
3. How would you detect that two steps in a plan are secretly the same step?

## 02. Plan-and-Execute vs ReAct: When to Plan Ahead

**MOTTO:** Planning is cheap. Re-planning after step 9 of 10 is not.

### The Problem
ReAct interleaves thinking and acting — great for exploration, but every step re-decides the whole strategy, burning tokens and drifting off-goal. Pure upfront planning is efficient but blind: the plan can't see what step 2 discovered.

### The Concept
Two ends of a dial:

```
ReAct:            think → act → observe → think → act → ...
Plan-and-execute: PLAN [1..N] → act 1 → act 2 → ... → act N
```

ReAct is a hiker with a compass; plan-and-execute is a hiker with a printed route. The compass wins in fog (unknown environments); the route wins on mapped trails (known workflows). Most production agents plan first, then run a small ReAct loop *inside* each step.

### Build It
- Planner call: emit the full step list once (use lesson 01's schema).
- Executor loop: for each step, allow up to K tool calls to complete it.
- Escape hatch: if a step's observations contradict the plan, jump to replanning (lesson 05).

### Use It
| Pattern | Where you see it |
|---|---|
| ReAct | LangChain's original agents, simple tool loops |
| Plan-and-execute | LangGraph plan-execute template, BabyAGI lineage |
| Hybrid | Claude Code: todo list up front, reactive loop per todo |

### War Story
The ReAct paper (Yao et al., 2022) showed that interleaving reasoning traces with actions beat both act-only and reason-only baselines on HotpotQA and ALFWorld. A year later, Plan-and-Solve prompting (Wang et al., 2023) showed upfront planning beat zero-shot chain-of-thought on math reasoning. Neither wins everywhere — which is exactly the point.

### Checkpoint
1. Name a task where ReAct clearly beats plan-and-execute, and one where it loses.
2. Why does plan-and-execute usually cost fewer tokens per task?
3. What signal should trigger a fallback from executing to replanning?

## 03. Tree of Thoughts: Exploring Alternatives

**MOTTO:** Your first idea is a sample, not a decision.

### The Problem
Greedy generation commits to the first token path the model likes. For problems where early choices matter — puzzles, designs, proofs — one bad early thought poisons everything downstream, and the model never looks back.

### The Concept
Tree of Thoughts (ToT) generates *multiple* candidate thoughts at each step, scores them, and expands only the promising ones. It's chess-player thinking: consider three moves, mentally evaluate each, then go deeper on the best.

```
            [problem]
           /    |    \
        t1a    t1b    t1c      ← generate 3 thoughts
        0.9    0.2    0.6      ← self-evaluate each
       /  \           |
    t2a    t2b       t2c       ← expand only survivors
```

### Build It
Three functions, one loop:
1. `propose(state, k)` — ask the LLM for k next-step thoughts.
2. `evaluate(state)` — ask the LLM (or a heuristic) to score 0–1, or vote "sure/maybe/impossible."
3. `search` — BFS or DFS over states, keeping the top-b per depth.

The evaluator is the whole game. A sloppy evaluator turns your tree into an expensive random walk.

### Use It
ToT is rarely a library import — it's a pattern you hand-roll for high-stakes, checkable steps: SQL query generation with EXPLAIN as the evaluator, code fixes with tests as the evaluator, plans scored by a critic prompt.

### War Story
In the Tree of Thoughts paper (Yao et al., 2023), GPT-4 with chain-of-thought solved only 4% of Game of 24 puzzles; with ToT it solved 74%. Same model, same weights — the entire gain came from search structure around the model.

### Checkpoint
1. Why is the evaluator more important than the proposer in ToT?
2. When is ToT a waste of money?
3. What real-world signal (not an LLM score) could evaluate a code-generation thought?

## 04. Search Over Reasoning: Beams and MCTS-lite

**MOTTO:** Don't argue with the model — outvote it.

### The Problem
ToT with naive BFS explodes: branching factor 3, depth 5 is 243 states, each costing LLM calls. You need principled ways to spend a fixed budget on the most promising branches.

### The Concept
Two classic algorithms, downsized for LLMs:

- **Beam search**: at each depth keep only the top-b candidates by score. Predictable cost: `b × k` calls per depth.
- **MCTS-lite**: repeat select → expand → rollout (cheap simulation or quick score) → backpropagate value up the tree. Spends budget adaptively where value estimates are high or uncertain.

```
Beam (b=2):   ████ ████ ▁▁▁▁ ▁▁▁▁     keep best 2, prune rest
MCTS:         visits pile up on branches that keep paying off
```

And the simplest search of all — **self-consistency**: sample N full answers, majority-vote the result. No tree, embarrassingly parallel, surprisingly strong.

### Build It
- Start with self-consistency (N samples + vote). Measure the gain.
- Upgrade to beam search only if intermediate steps are scoreable.
- Reach for MCTS-lite only when you have a cheap rollout signal (tests pass, parser accepts, constraint satisfied).

### Use It
| Technique | Cost profile | Needs |
|---|---|---|
| Self-consistency | N× one query | Votable final answer |
| Beam | b×k× per depth | Step-level scores |
| MCTS-lite | Adaptive | Cheap rollout/verifier |

### War Story
AlphaGo's 2016 win over Lee Sedol ran MCTS guided by neural value and policy networks — move 37 in game 2, a move human pros initially called a mistake, came out of that search. Earlier, self-consistency (Wang et al., 2022) showed that just sampling multiple chains of thought and voting gave large accuracy jumps on GSM8K. Search around the model is an old, repeatedly winning trick.

### Checkpoint
1. Why is self-consistency the right first experiment before building any tree?
2. What property must intermediate states have for beam search to work?
3. In MCTS-lite for code generation, what plays the role of the "rollout"?

## 05. Replanning: When Step 3 Destroys the Plan

**MOTTO:** The plan is a hypothesis. Reality is the reviewer.

### The Problem
Plans age badly. Step 3 reveals the API is deprecated, the file doesn't exist, the user actually meant something else. An agent that keeps executing a dead plan produces confident garbage; one that replans from scratch on every hiccup never finishes.

### The Concept
Replanning is a controlled feedback edge, not a panic button:

```
plan → execute step → observe
              │
        result matches done_when? ──yes──▶ next step
              │no
        retry (≤2) → still failing?
              │yes
        REPLAN(goal, completed_steps, failure_context)
```

Key detail: the replanner receives what *already succeeded* so it doesn't redo work, plus the failure evidence so it doesn't repeat the mistake.

### Build It
- Track plan state: `pending / running / done / failed` per step.
- Cap retries per step and replans per task (2 and 3 are sane defaults).
- On replan, prompt with: original goal, completed steps + results, failed step, error text. Ask for a *revised remainder*, not a whole new plan.

### Use It
Every serious agent framework has this edge: LangGraph conditional edges back to a planner node, Claude Code revising its todo list mid-task after a failed command, CI-fixing agents that re-diagnose after a red build.

### War Story
AutoGPT, the March 2023 phenomenon that rocketed to over 100k GitHub stars in weeks, became equally famous for looping — re-attempting failed steps and re-generating near-identical plans until users killed the process or the API bill did. Its core missing piece was exactly this: replan caps and failure context, not more autonomy.

### Checkpoint
1. Why should the replanner receive completed steps rather than starting fresh?
2. What's the difference between a retry and a replan, mechanically?
3. How do replan caps prevent the AutoGPT loop failure mode?

## 06. Hierarchical Planning: Managers and Workers

**MOTTO:** The CEO doesn't write the SQL.

### The Problem
One agent holding the whole task in context means one context window holding everything: the grand strategy, the current file diff, the API docs, the error logs. Quality degrades as the window fills with details irrelevant to the current step.

### The Concept
Split by altitude. A **manager** agent owns the goal and the plan; **worker** agents each get one subtask, a clean context, and only the inputs they need. Workers return results, not transcripts.

```
        [Manager: goal, plan, results summary]
          │            │             │
     [Worker A]   [Worker B]    [Worker C]
     fresh ctx    fresh ctx     fresh ctx
     one subtask  one subtask   one subtask
```

This is HTN (hierarchical task network) planning from classical AI, reborn with LLMs in every role.

### Build It
- Manager prompt: decompose, dispatch, integrate. It never touches tools directly.
- Worker prompt: one subtask + `done_when` + relevant context only.
- Contract: workers return a structured result `{status, output, notes}` — the manager sees a paragraph, not 50 tool calls.

### Use It
| System | Hierarchy |
|---|---|
| Claude Code subagents | Main agent dispatches Task agents with fresh context |
| MetaGPT | Software-company roles: PM → architect → engineer |
| LangGraph | Supervisor pattern with worker nodes |

### War Story
MetaGPT (Hong et al., 2023) assigned LLM agents fixed company roles — product manager, architect, engineer — passing structured documents between them instead of raw chat, and outperformed flat multi-agent chat on code-generation benchmarks. The structure, not extra model capability, delivered the gain.

### Checkpoint
1. Why do workers get *fresh* context instead of a copy of the manager's?
2. What belongs in the worker→manager return contract?
3. When does hierarchy add latency without adding quality?

## 07. Verification Loops: Check Before You Claim

**MOTTO:** "It should work now" is not a test result.

### The Problem
LLMs are fluent about success. An agent that writes code, doesn't run it, and reports "done!" is optimizing for your approval, not your outcome. Unverified claims compound: step 5 builds on step 3's imaginary success.

### The Concept
Insert a verifier between "did the thing" and "claim the thing":

```
generate → VERIFY → pass? → claim done
              │ fail
              ▼
        feed error back → regenerate (≤K)
```

Verifiers come in a hierarchy of trustworthiness: hard checks (tests, compilers, schema validators) > soft checks (LLM critic with a rubric) > vibes (none). Always prefer the hardest verifier available — generation is creative, verification should be boring.

### Build It
- After every claimed step completion, run its `done_when` check *mechanically* where possible: run the test, hit the endpoint, stat the file.
- For unverifiable-by-machine steps, use a separate critic call with a rubric — a fresh context critic, not the same conversation grading its own homework.
- Log verify results; they're your replan triggers.

### Use It
Coding agents live on this loop: generate patch → run test suite → feed failures back. Claude Code runs commands and reads their output; SWE-bench-style agents are scored *only* on whether tests pass, which is verification as ground truth.

### War Story
OpenAI's "Let's Verify Step by Step" (Lightman et al., 2023) trained a process reward model that checked each reasoning step rather than just the final answer, and found process supervision significantly outperformed outcome supervision on MATH problems. Checking steps beats trusting conclusions — even for the model's own reasoning.

### Checkpoint
1. Rank: unit test, LLM critic, "looks right" — and justify the ordering.
2. Why should an LLM critic get a fresh context instead of the working transcript?
3. What goes wrong when the same prompt both generates and verifies?

## 08. Reasoning Models: o-series, R1, and Extended Thinking

**MOTTO:** Some models now do the scratchpad for you. Know when to let them.

### The Problem
Everything so far — ToT, search, verification — is scaffolding *you* build around a model. Reasoning models internalize much of it: they emit long private chains of thought, explore, backtrack, and self-correct before answering. Your scaffolding decisions change when the model plans natively.

### The Concept
Three flavors of the same idea:
- **OpenAI o-series** (o1, Sept 2024): RL-trained to produce long hidden reasoning tokens before the visible answer.
- **DeepSeek-R1** (Jan 2025): open-weights reasoning model whose training showed reasoning behaviors (self-checking, backtracking) *emerging* from RL on verifiable problems; thinking exposed in `<think>` tags.
- **Anthropic extended thinking** (Claude 3.7 Sonnet, Feb 2025): one model with a dial — a token budget for visible thinking, from zero to thousands.

Rule of thumb: reasoning models replace *within-step* scaffolding (ToT for one hard step) but not *across-step* orchestration (plans, tools, verification against reality).

### Build It
- Route: hard, self-contained problems (math, tricky code, analysis) → reasoning model; simple tool dispatch → fast model.
- Don't pile chain-of-thought prompts on a reasoning model — "think step by step" is redundant and can hurt.
- Still verify externally: internal reasoning checks logic, not reality.

### Use It
| Model family | Thinking control |
|---|---|
| OpenAI o-series / GPT-5 | `reasoning_effort` parameter |
| Claude | Extended thinking with token budget |
| DeepSeek-R1 | Open weights; think tags in output |

### War Story
DeepSeek-R1's January 2025 release — open weights, MIT license, benchmark scores near o1 at a fraction of the claimed training cost — triggered a market panic that wiped roughly $600B off Nvidia's market cap in a single day, the largest one-day value loss for any US company at the time. Reasoning stopped being a proprietary moat that week.

### Checkpoint
1. What scaffolding does a reasoning model make redundant, and what does it not?
2. Why can "think step by step" hurt an o-series model?
3. Why must you still run external verification even with a reasoning model?

## 09. Inference-Time Compute: Pay More, Think Harder

**MOTTO:** Intelligence is now a slider with a price tag.

### The Problem
For years, the only way to a better answer was a bigger model. But you can't retrain per query — and some queries are worth $0.001 of thought while others are worth $10. You need a knob at inference time, not training time.

### The Concept
Inference-time (test-time) compute: spend more tokens/samples/search on a single query to get a better answer.

```
accuracy
   ▲          ___----
   │      _--
   │    /
   │   /
   └──────────────▶ log(inference compute)
```

The mechanisms are everything from this phase: longer thinking budgets, self-consistency sampling, best-of-N with a verifier, tree search. The curve is roughly log-linear — each doubling of compute buys a fixed accuracy bump, until it doesn't.

### Build It
- Define per-task compute tiers: cheap (1 sample, no thinking), standard (thinking on), expensive (best-of-N + verifier).
- Route by stakes and by measured difficulty (e.g., escalate on verifier failure — retry the failed query at the next tier).
- Track cost-per-solved-task, not cost-per-call. An expensive call that avoids three retries is cheap.

### Use It
`reasoning_effort` (OpenAI), thinking budgets (Anthropic, Gemini), and best-of-N with reranking are all this knob wearing different clothes. Escalation routing — cheap model first, expensive on failure — is the production version.

### War Story
In December 2024, OpenAI's o3 scored 87.5% on the ARC-AGI semi-private eval in high-compute mode — a benchmark designed to resist LLMs — but reported compute costs ran to thousands of dollars per task at that setting. The o1 announcement (Sept 2024) had already published log-scale plots of accuracy climbing with test-time compute. The capability is real; so is the invoice.

### Checkpoint
1. Why is cost-per-solved-task the right metric rather than cost-per-call?
2. What does the log-linear compute/accuracy curve imply about diminishing returns?
3. Design an escalation policy for a code-fixing agent with three compute tiers.

## 10. Task Lists and Progress Tracking (Todo-Driven Agents)

**MOTTO:** The humble checkbox is a state machine you can read.

### The Problem
Long tasks drift. Forty tool calls in, the context is a swamp of logs and the model half-remembers what it was doing. Users, meanwhile, stare at a spinner with no idea whether the agent is on step 2 or step 9 — or looping.

### The Concept
Make the plan a *live artifact*: a todo list the agent writes, updates, and re-reads. It serves three masters at once — the model (re-anchors attention on the goal every turn), the user (visible progress), and the system (machine-checkable state for resumption and timeouts).

```
[x] 1. Locate failing test          done
[x] 2. Reproduce locally            done
[~] 3. Patch off-by-one in parser   in_progress
[ ] 4. Run full suite               pending
[ ] 5. Update changelog             pending
```

### Build It
- Give the agent two tools: `todo_write(items)` and `todo_update(id, status)`.
- Inject the current list into every turn's context — this is the anti-drift mechanism.
- Enforce invariants in code, not prompts: exactly one `in_progress` item; can't mark done without a verify result (lesson 07).

### Use It
| Tool | Todo mechanism |
|---|---|
| Claude Code | Built-in todo list, visible in the UI |
| BabyAGI lineage | Task queue: create, prioritize, execute |
| LangGraph | Plan held in typed graph state |

### War Story
BabyAGI (Yohei Nakajima, April 2023) was little more than a task list and three loops — create tasks, prioritize tasks, execute tasks — yet it became one of the defining agent demos of 2023 and shaped a generation of frameworks. Two years later, Claude Code shipped todo tracking as a core built-in tool, not an add-on. The checkbox won.

### Checkpoint
1. What three audiences does a live todo list serve simultaneously?
2. Why enforce "one in_progress item" in code rather than in the prompt?
3. How does re-injecting the todo list each turn fight context drift?

## 11. Long-Horizon Coherence: Not Losing the Plot

**MOTTO:** Any agent can start strong. Shipping is a 400-turn problem.

### The Problem
Over hundreds of turns, agents forget constraints stated at turn 3, redo finished work, contradict earlier decisions, and mistake activity for progress. Context windows fill; summaries lose the one detail that mattered; the goal quietly mutates.

### The Concept
Coherence is engineered, not prompted. The toolkit:

```
┌─ Goal card ──────────────┐  restated verbatim every turn
├─ Todo list ──────────────┤  live plan state (lesson 10)
├─ Decision log ───────────┤  "chose X over Y because Z" — append-only
├─ Compaction ─────────────┤  summarize old turns, PRESERVE decisions
└─ Milestone checkpoints ──┤  verify against original goal, not last summary
```

The decision log is the underrated one: most incoherence is silently *re-litigating* settled decisions after compaction erased the reasoning.

### Build It
- Pin an immutable goal statement outside the compactable region.
- On compaction, summarize observations aggressively but carry decisions and constraints verbatim.
- Every N steps, run a drift check: "Given the original goal, is the current activity on the critical path?" — with the *original* goal text, not the summary.

### Use It
Claude Code compacts long sessions while preserving key state; long-running research and coding agents checkpoint to files (`NOTES.md`, plan files) precisely so that coherence survives context resets and process restarts.

### War Story
Anthropic's "Claude Plays Pokémon" experiment (streamed on Twitch, Feb 2025) showed Claude 3.7 making real progress but also spending long stretches stuck — wandering areas and revisiting failed approaches as context about past attempts decayed. METR's March 2025 study framed the field's trajectory: the length of tasks agents can complete has been doubling roughly every seven months. Horizon *is* the frontier.

### Checkpoint
1. Why should drift checks compare against the original goal instead of the latest summary?
2. What information must survive compaction verbatim, and why?
3. How does a decision log prevent re-litigating settled choices?

## 12. Build a Planning Agent From Scratch

**MOTTO:** If you can't build the loop in 100 lines, you don't understand the loop.

### The Problem
Frameworks hide the plan-execute-replan loop behind abstractions. Time to prove there's no magic: a planner, an executor, a verifier, and a replan edge — in plain Python with a mock LLM you can swap for a real one later.

### The Concept
The full Phase 6 pipeline in one loop: decompose (01), execute steps (02), verify (07), retry-then-replan (05), track progress (10).

### Build It
```python
import json

def mock_llm(prompt: str) -> str:
    """Swap for a real API call. Returns JSON plans/results."""
    if "PLAN" in prompt:
        return json.dumps([
            {"id": 1, "action": "fetch_data", "done_when": "rows > 0"},
            {"id": 2, "action": "summarize", "done_when": "summary non-empty"},
        ])
    return json.dumps({"output": "42 rows", "ok": True})

def plan(goal, context=""):
    return json.loads(mock_llm(f"PLAN steps for: {goal}\n{context}"))

def execute(step):
    return json.loads(mock_llm(f"EXECUTE: {step['action']}"))

def verify(step, result):
    return result.get("ok", False)  # real: run tests, check schema, etc.

def run(goal, max_replans=2):
    steps, done = plan(goal), []
    replans = 0
    while steps:
        step = steps.pop(0)
        for attempt in range(2):                     # retry cap
            result = execute(step)
            if verify(step, result):
                done.append((step, result)); break
        else:                                        # both attempts failed
            if replans >= max_replans:
                return {"status": "failed", "done": done, "stuck_on": step}
            replans += 1
            ctx = f"Completed: {done}\nFailed: {step} — replan the remainder."
            steps = plan(goal, ctx)                  # revised remainder
    return {"status": "success", "done": done}

print(run("Ship the weekly report"))
```

Exercises: (a) make `mock_llm` fail step 2 once and watch the retry; (b) make it fail persistently and watch the replan; (c) add a todo-list printout each iteration; (d) swap in a real LLM client.

### Use It
This skeleton *is* LangGraph's plan-and-execute template, CrewAI's task loop, and Claude Code's todo-driven flow, minus the ergonomics. Now when a framework misbehaves, you know which of these five moving parts to blame.

### War Story
BabyAGI's original April 2023 script was a couple hundred lines of Python doing essentially this loop, and it captivated the industry. The moat was never the loop — it's the verifiers, the prompts, and the judgment about when to replan.

### Checkpoint
1. Trace the code path when a step fails twice and a replan is available.
2. Why does the replan prompt include completed steps?
3. What would you change to make `verify` trustworthy for a code-writing agent?
