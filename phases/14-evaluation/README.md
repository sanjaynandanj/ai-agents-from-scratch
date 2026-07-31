# Phase 14 — 📊 Evaluation & Benchmarks

> If you can't measure your agent, you're shipping a mood.

You've built agents that plan, code, browse, and swarm. Now the uncomfortable question: are they any good, and how would you know? "It worked when I tried it" is not evidence — it's a mood with a sample size of one. This phase builds the measurement stack: evals, trajectory grading, LLM judges, benchmarks, regression suites, and the statistics of non-deterministic systems, ending with an eval harness you write yourself.

## 01. Evals from Scratch: Task, Rubric, Grader

**MOTTO:** An eval is a unit test that tolerates a thousand right answers.

### The Problem
Traditional tests assert `f(x) == y`. Agents don't have one right output: "summarize this ticket" has many good answers and infinitely many bad ones. So teams eyeball outputs, feel vaguely positive, and ship — then discover in production which of the thousand answers their agent actually gives.

### The Concept
Every eval, however fancy, is three parts:

```
  TASK    what the agent is asked, with fixed inputs and environment
  RUBRIC  what "good" means, written down, before you look at outputs
  GRADER  the thing that applies the rubric: code, model, or human
```

Graders form a ladder: *code-based* (exact match, contains, tests pass — cheap, objective, narrow), *model-based* (LLM applies the rubric — flexible, imperfect), *human* (gold standard, expensive). The craft is pushing as much as possible down the ladder: extract the checkable facts ("did it name the refund amount? is the JSON valid?") and reserve judgment calls for judges.

### Build It
Start with 20 tasks from real usage — including the ugly ones that made you wince — each as `{id, input, rubric, grader}`. Write the rubric before running the agent; rubrics written after looking at outputs mysteriously match the outputs. Run, grade, and store every result with a timestamp and config hash. Twenty graded tasks beat zero perfect ones; you'll grow the set in Lesson 05.

### Use It
Harness options: OpenAI Evals, Braintrust, LangSmith, Promptfoo, Inspect (UK AI Safety Institute's open-source framework), or the ~100 lines of Python you'll write in Lesson 10. The harness is the easy part; the task set and rubrics are the asset.

### War Story
The GAIA benchmark (2023) was built on exactly this discipline: real-world assistant questions with unambiguous, code-checkable final answers, so grading needs no judge at all. Humans scored 92%; GPT-4 with plugins scored about 15%. A well-designed rubric made a wide capability gap undeniable — and un-arguable — with simple string matching.

### Checkpoint
1. What are the three components of any eval?
2. Why must rubrics be written before inspecting agent outputs?
3. When do you use a code grader versus a model grader?

## 02. Trajectory Evaluation: Grading the Journey

**MOTTO:** The right answer by the wrong road is a wrong answer on a delay.

### The Problem
Outcome-only grading is blind to *how* the agent got there. An agent can reach the right answer by luck, by ignoring your tools and guessing from priors, or by doing something appalling along the way — deleting a file and recreating it, calling a paid API forty times, exfiltrating data before answering correctly. Outcome: pass. Reality: time bomb.

### The Concept
A trajectory is the full sequence of steps; trajectory evaluation applies rubrics to it:

```
  outcome eval:     [........................] -> answer  ✓/✗
  trajectory eval:  [tool? args? order? loops? cost? recovery?] -> answer
```

Useful trajectory checks: *did it use the required tool* (vs guessing), *step efficiency* (steps vs a reference solution), *no forbidden actions*, *loop detection* (same call, same args, repeatedly), *recovery behavior* (what it did after the first error). These predict production reliability far better than outcome alone, because luck doesn't repeat but process does.

### Build It
First, make trajectories machine-readable: log every step as `{step, type, name, args_hash, result_summary, tokens, latency}`. Then write trajectory graders as plain functions over that list — `assert_tool_used("search")`, `assert_no_tool("delete_file")`, `steps <= 2 * reference_steps`, `no_repeated_call(window=3)`. Score outcome and trajectory separately and report both; a pass with a red trajectory is a different signal than a clean pass, and averaging them hides exactly the thing you built this to see.

### Use It
LangSmith, Langfuse, and Arize Phoenix capture trajectories (often as OpenTelemetry traces) and support custom evaluators over them; Inspect and DeepEval ship trajectory-aware metrics. Agent benchmarks increasingly grade process too — WebArena checks *state* changes, tau-bench checks database state after the conversation, not just the words.

### War Story
The tau-bench paper (2024) evaluated customer-service agents by checking the final database state against policy — not just reply text — and found models frequently produced plausible conversations while violating the airline's rules underneath, such as making changes the policy forbade. Outcome-looking-fine with process-gone-wrong is precisely the failure class trajectory evaluation exists to catch.

### Checkpoint
1. Give two ways an agent can pass an outcome eval while being unshippable.
2. Why should outcome and trajectory scores be reported separately?
3. What log fields must a trajectory contain to be gradeable by code?

## 03. LLM-as-Judge: Powers and Pitfalls

**MOTTO:** The judge is a witness with opinions. Calibrate before you trust the verdict.

### The Problem
Most interesting rubrics — "is this summary faithful?", "was the tone appropriate?" — can't be checked by string matching, and humans don't scale to grading 500 outputs per commit. The obvious move is using an LLM as the grader. The obvious move has documented failure modes.

### The Concept
An LLM judge receives the task, the rubric, and the output, and returns a grade. Its known biases:

```
  position bias   in A-vs-B comparisons, favors one slot (often the first)
  verbosity bias  longer answers score higher at equal quality
  self-preference judges rate their own model family's style higher
  sycophancy      confident, polished wrongness outscores hesitant rightness
```

Mitigations, in order of value: judge against an explicit rubric, never "rate 1-10" bare; for pairwise comparisons, swap positions and only count consistent verdicts; require the judge to quote evidence before scoring; use a judge from a different model family than the agent; prefer binary per-criterion checks over scalar vibes.

### Build It
Build the judge as `judge(task, rubric, output) -> {criterion: pass/fail, evidence}` with structured output, temperature 0. Then — this is the step everyone skips — *evaluate the judge*: hand-label 50 outputs yourself, run the judge on them, and measure agreement. Below ~85% agreement, fix the rubric or the judge prompt before trusting it at scale. Re-check whenever you change judge model or rubric; judge drift is silent and poisons every downstream number.

### Use It
Pairwise judging with position-swap is standard in Arena-style rankings; Braintrust, LangSmith, and Promptfoo all support rubric-based judge evaluators; DeepEval ships judge metrics with bias mitigations. Whatever the tool, the human-agreement audit is on you.

### War Story
The MT-Bench / Chatbot Arena paper (Zheng et al., 2023) put numbers on judge bias: GPT-4-as-judge showed measurable position bias in pairwise comparisons and favored longer answers, yet after mitigations (position swapping among them) reached over 80% agreement with human preferences — comparable to human-human agreement. Both halves matter: the biases are real, and so is the usefulness once you engineer around them.

### Checkpoint
1. Name three documented biases of LLM judges and one mitigation for each.
2. Why must you measure judge-human agreement before scaling a judge?
3. Why do binary per-criterion checks beat 1-10 scalar scores?

## 04. Benchmarks: SWE-bench, GAIA, WebArena, tau-bench

**MOTTO:** A benchmark measures exactly what it measures — read the fine print before you believe the leaderboard.

### The Problem
"Agent X scores 70% on SWE-bench" — should you care? Only if you know what the benchmark actually tests, what it ignores, and whether the number still means anything or the benchmark has been saturated, gamed, or memorized into irrelevance.

### The Concept
The four benchmarks every agent builder should be able to explain:

| Benchmark | Task | Grader | Measures / caveat |
|---|---|---|---|
| SWE-bench (2024) | Patch real GitHub issues (12 Python repos) | Held-out tests | Repo-scale coding; contamination concerns → Verified subset (2024) |
| GAIA (2023) | Real-world assistant Qs, tool use required | Exact-match answer | Grounded multi-step reasoning; humans 92% vs GPT-4+plugins ~15% at release |
| WebArena (2023) | Tasks on self-hosted realistic websites | Programmatic state/answer checks | Web operation; humans ~78%, first agents ~14% |
| tau-bench (2024) | Customer-service dialogs under policy, simulated user | Final DB state + pass^k | Policy compliance and *reliability across retries* |

Benchmark lifecycle: release (huge human-agent gap) → climb → saturation (top models cluster near ceiling, or test-set leakage into training data inflates scores) → replacement. A saturated benchmark stops discriminating; a contaminated one measures memory.

### Build It
Reading a leaderboard defensively: check the *scaffold* (numbers combine model + harness — SWE-bench scores vary wildly across scaffolds for the same model), check the subset (Lite vs Verified vs full are different tests), check the date against model training cutoffs, and check pass@1 vs pass@k reporting. Then remember the only benchmark that predicts *your* product is the one built from your tasks — public benchmarks tell you about models, not about your agent.

### Use It
Run them yourself rather than quoting them: SWE-bench and WebArena publish full harnesses and environments; GAIA and tau-bench are on GitHub/HuggingFace. Running 20 tasks locally teaches more than any leaderboard screenshot.

### War Story
SWE-bench's own arc is the lifecycle lesson: at release (2024 paper), the best assisted model resolved under 2% of issues. Within roughly two years, top agents reported 70%+ on the Verified subset — while OpenAI's Verified audit had already removed a large share of the original tasks as unfair or broken, and researchers raised contamination and overfitting concerns. Same name, radically different meaning over time.

### Checkpoint
1. Why do SWE-bench numbers for the same model differ across scaffolds?
2. What does tau-bench's pass^k metric capture that pass@1 misses?
3. What are two reasons a benchmark's scores can inflate without real capability gains?

## 05. Building a Regression Suite for Agents

**MOTTO:** Every prompt tweak is a code change. Ship it through a test gate like one.

### The Problem
You improve the prompt for refund cases; three weeks later someone notices shipping-status questions broke. Agent behavior is a web of couplings — prompts, tools, model versions — and any edit can silently regress a distant behavior. Without a regression suite, you find out from users.

### The Concept
Same discipline as software CI, adapted for non-determinism:

```
  golden set (frozen tasks + rubrics)
       |            versioned config: prompts, tools, model, harness
       v
  run on every change --> compare to baseline --> gate the merge
```

Two suites in practice: a *smoke suite* (10–30 tasks, minutes, every PR) and a *full suite* (hundreds, nightly). Every production failure becomes a new case — the suite is your institutional memory of every way the agent has embarrassed you. Statistical care is mandatory: with sampling variance, one run of 25 tasks can't distinguish 80% from 88%; Lesson 06 covers how many runs you actually need.

### Build It
Freeze a golden set with pinned model versions and a config hash in every result row. On each change: run smoke suite k times, compare per-task pass rates against baseline, fail the gate on statistically meaningful drops — and *review* per-task diffs, not just the aggregate (an aggregate can hold steady while refunds break and shipping improves). Curate deliberately: retire tasks that have passed 100% for months to a nightly archive, promote every new production incident into the smoke set.

### Use It
Braintrust, LangSmith, and Promptfoo all support baseline-vs-candidate comparison in CI; Promptfoo is particularly natural in a GitHub Actions gate. Storage can be as simple as JSONL per run — what matters is that results are diffable across configs.

### War Story
In April 2025, OpenAI rolled back a GPT-4o update after users found it excessively sycophantic — agreeing with and flattering almost anything. OpenAI's own postmortem said evaluations and A/B tests had looked good, offline checks "generally looked good," while some expert testers had felt something was off — and there was no specific sycophancy eval in the gate. The regression you don't have a test for is the one that ships.

### Checkpoint
1. Why must both config (prompt/model/tools) and results be versioned together?
2. Why can an unchanged aggregate score hide a real regression?
3. Where should new regression cases come from as the suite matures?

## 06. Non-Determinism: pass@k and Variance

**MOTTO:** Your agent's score is a distribution. One run is an anecdote with a decimal point.

### The Problem
Same agent, same task, ten runs: seven passes. Is the agent "70% good"? Is a teammate's 8/10 on their branch an improvement? LLM sampling, tool flakiness, and environment timing make every run a coin flip with an unknown bias — and people routinely ship decisions based on one flip.

### The Concept
Two different questions, two different metrics:

```
  pass@k     P(at least one of k attempts succeeds)   -> capability ceiling
  pass^k     P(all k attempts succeed)                -> reliability floor
```

pass@k (formalized in the HumanEval/Codex paper, 2021) suits problems where you can verify and pick the winner among k tries. pass^k (popularized by tau-bench) suits production, where every single run faces a real user. A model can look great on pass@8 and dismal on pass^8 — same underlying per-run rate, opposite conclusions. And per-task pass rates need error bars: at p=0.7, ten runs give you a 95% confidence interval roughly ±0.28 wide. Ten runs is a vibe.

### Build It
Harness rules: run every task k times (k≥5 for anything decision-relevant) and store *all* attempts, never just the best. Report per-task pass rate with a confidence interval (Wilson interval is fine at small n). When comparing configs A and B, use paired comparisons on the same tasks and a significance test — at minimum, refuse to conclude anything from overlapping intervals. Temperature 0 does *not* buy determinism for agents: tool results, timing, and even batched inference vary. Measure the variance; don't wish it away.

### Use It
Inspect, Braintrust, and LangSmith support repeated runs per task; scipy gives you the tests. tau-bench's harness reports pass^k natively — worth reading as reference code for reliability-first evaluation.

### War Story
The Codex paper (2021) that introduced pass@k also showed why the naive estimator misleads: computing it from a single batch of k samples biases the estimate, so the authors derived an unbiased estimator from n > k samples — a detail that exists precisely because early results were flattered by lucky batches. The field's very first agent-adjacent metric came with a variance warning attached. It still applies.

### Checkpoint
1. Explain pass@k vs pass^k and which one production cares about.
2. Why doesn't temperature 0 make an agent deterministic?
3. Your candidate scored 82% vs baseline 78% on one run of 50 tasks. What do you do before celebrating?

## 07. Online Evals: A/B Tests and User Signals

**MOTTO:** Offline evals grade the rehearsal. Production grades the show.

### The Problem
Your golden set is a frozen photograph of past traffic. Real usage drifts — new topics, new phrasing, adversarial users — and offline pass rates can stay green while production satisfaction quietly rots. Some qualities (was the user actually helped?) only exist in production at all.

### The Concept
Online evaluation instruments the live system:

```
  explicit signals   thumbs, ratings, surveys       (sparse, biased, loud)
  implicit signals   retry, rephrase, abandon, escalate-to-human,
                     edit-the-agent's-output, task completion   (dense, honest)
  experiments        A/B: route x% of traffic to candidate, compare signals
  shadow mode        candidate runs on real inputs, output logged not shown
```

Implicit signals beat explicit ones: few users click thumbs, and the ones who do are angry or delighted, not representative. A user immediately rephrasing is a failure vote; a user copying the agent's code verbatim is a success vote. Shadow mode is the underrated middle step — production inputs, zero user risk.

### Build It
Instrument first: log session outcomes (completed / abandoned / escalated), retries-per-task, and edits to agent output, all joined to config version. Then gate rollouts: shadow → 5% canary with auto-rollback thresholds → 50/50 A/B with significance testing → full. Feed the loop back: sample sessions with bad implicit signals into Lesson 08's error analysis and Lesson 05's regression suite. And mind Goodhart — optimize thumbs-up hard enough and you'll breed a flatterer (see Lesson 05's war story; that mechanism was part of OpenAI's own sycophancy postmortem).

### Use It
Standard experimentation stacks (Statsig, GrowthBook, LaunchDarkly) handle assignment and stats; LLM observability tools (LangSmith, Langfuse, Arize) join traces to feedback. The agent-specific part — defining honest success signals for *your* task — no vendor sells.

### War Story
The Air Canada case (2024) is what un-evaluated production looks like: the airline's website chatbot invented a bereavement-fare refund policy, a customer relied on it, and a Canadian tribunal ordered the airline to honor the hallucinated policy, rejecting the argument that the chatbot was "a separate legal entity responsible for its own actions." Production is an eval where the graders include judges — the courtroom kind.

### Checkpoint
1. Why are implicit signals generally more trustworthy than thumbs ratings?
2. What does shadow mode test that offline evals can't, and what risk does it avoid?
3. How does Goodhart's law bite an agent optimized on user approval signals?

## 08. Error Analysis: Reading Failed Trajectories

**MOTTO:** Your failures are already sorted into piles. Reading them is how you find out which piles.

### The Problem
The suite says 68%. That number tells you that you have a problem and nothing about what it is. Teams respond by tweaking prompts at random and re-rolling the dice — eval-driven superstition. The information you need is sitting in the failed trajectories nobody reads.

### The Concept
Error analysis is qualitative, then quantitative: read failures one by one, label each with *the first step where the trajectory went irrecoverably wrong* and a failure category, then count the piles.

```
  read N failures -> label first-wrong-step + category -> count
  categories that recur: wrong tool / bad args / misread tool output /
    hallucinated fact / gave up early / loop / never-checked-work /
    task ambiguous (eval's fault, not agent's)
```

Two findings recur across nearly every team that does this: failures follow a power law (two or three categories dominate), and a surprising share of "agent failures" are eval bugs — ambiguous tasks, broken fixtures, wrong rubrics. Both findings redirect weeks of effort.

### Build It
Make it a ritual: after every full run, sample 20–30 failures, read each trajectory start to finish, and record `{task_id, first_wrong_step, category, evals_fault?}` in a shared sheet. Derive the taxonomy from the data — start with an empty list and add categories as you read; pre-baked taxonomies make you see what you expect. Fix the top pile, re-run, re-read. Once a category is stable and crisply defined, automate a detector for it (a trajectory grader from Lesson 02) — but the manual reading never fully retires, because new failure modes don't announce themselves.

### Use It
Trace viewers (LangSmith, Langfuse, Phoenix) make reading trajectories humane; a spreadsheet holds the labels. An LLM can pre-cluster failures to save time — treat its clusters as suggestions and audit them like any judge (Lesson 03).

### War Story
OpenAI's SWE-bench Verified effort (2024) was error analysis performed on the benchmark itself: annotators reviewing failures found many weren't model failures at all — issues too underspecified to solve, tests that rejected valid patches — and filtered the task set accordingly. Reading the failures changed the denominator. Do the same audit on your own eval before concluding your agent is the broken part.

### Checkpoint
1. Why label the *first* wrong step rather than the final error?
2. Why derive failure categories from reading rather than defining them upfront?
3. What fraction of failures turning out to be eval bugs would surprise you — and what do you do about them?

## 09. Capability vs Reliability: The Nines Problem

**MOTTO:** A demo needs one success. A product needs the same success every time anyone asks.

### The Problem
Your agent can do the task — you've seen it. It just doesn't do it *every* time. That gap between "can do" (capability) and "does do, dependably" (reliability) is where agent products die: a 90%-reliable step feels magical in a demo and generates a support ticket per ten real uses — and per-step 90% collapses catastrophically when steps chain.

### The Concept
Reliability compounds multiplicatively:

```
  per-step:   99%      95%      90%
  10 steps:   90%      60%      35%
  50 steps:   61%       8%      0.5%
```

Software infrastructure talks in nines (99.9%); agents today often deliver *zero* nines per complex task. The two honest levers: raise per-step reliability (better tools, tighter environments — Phase 13's material), or restructure so failures don't compound — verify-and-retry at each step (turning pass@1 problems into pass@k problems), checkpoint boundaries that localize damage, and human gates at the irreversible points. Marketing quotes capability numbers; engineering plans on reliability numbers; the honest scorecard shows both.

### Build It
Measure the gap explicitly: for each golden task, report pass@5 (capability: can it, ever?) alongside pass^5 (reliability: can it, always?). The spread between them is your engineering roadmap — a wide spread means the skill exists and the *system* around it is failing, which retries, verification, and environment fixes can close; a narrow spread at a low level means the capability itself is missing, and no amount of retry engineering will save you. Different diagnoses, different quarters of work.

### Use It
tau-bench made this distinction mainstream by reporting pass^k; METR's horizon metric bakes in a reliability threshold (50%) precisely because "can complete" is meaningless without one. When you read any agent claim, first ask: at how many nines?

### War Story
The tau-bench paper (2024) reported that even the strongest model tested succeeded on under half of airline-domain tasks at pass^1 — and consistency degraded sharply as k grew, with pass^8 falling far below the single-attempt rate. Same model, same tasks: the capability headline and the reliability floor were different numbers with different product implications. Every agent you ship has both numbers, whether or not you've measured them.

### Checkpoint
1. Compute end-to-end success for a 20-step task at 95% per-step reliability.
2. Wide pass@5-vs-pass^5 spread vs narrow-and-low: what does each diagnosis prescribe?
3. Name three structural techniques that stop per-step failures from compounding.

## 10. Build an Eval Harness from Scratch

**MOTTO:** A hundred lines of Python is the difference between "seems better" and "is better."

### The Problem
Everything in this phase becomes real the moment it's executable. We'll build a harness that runs tasks against an agent k times, grades outcome and trajectory, aggregates pass@k and pass^k, and diffs against a baseline — the skeleton every commercial platform wraps in a UI.

### The Concept
A harness is a pipeline: task set → repeated runs → graders → aggregate → compare. Keep each stage a plain function and the whole thing stays inspectable, versionable, and extendable.

### Build It
```python
import json, random, statistics

TASKS = [  # golden set: task + code-graded rubric (Lesson 01)
    {"id": "t1", "input": "2+2", "expect": "4", "must_use": "calc"},
    {"id": "t2", "input": "capital of France", "expect": "paris", "must_use": None},
    {"id": "t3", "input": "17*23", "expect": "391", "must_use": "calc"},
]

def agent(task, flaky=0.25):          # stand-in: swap for your real agent
    traj = []
    if "+" in task["input"] or "*" in task["input"]:
        traj.append({"tool": "calc", "args": task["input"]})
    ok = random.random() > flaky      # simulated non-determinism (Lesson 06)
    return (task["expect"] if ok else "unsure"), traj

def grade(task, answer, traj):        # outcome + trajectory (Lesson 02)
    outcome = task["expect"].lower() in answer.lower()
    used = {s["tool"] for s in traj}
    process = task["must_use"] is None or task["must_use"] in used
    return {"outcome": outcome, "process": process, "pass": outcome and process}

def evaluate(k=5, seed=0):
    random.seed(seed); results = {}
    for t in TASKS:
        runs = [grade(t, *agent(t)) for _ in range(k)]
        p = [r["pass"] for r in runs]
        results[t["id"]] = {"rate": statistics.mean(p),
                            "pass@k": any(p), "pass^k": all(p)}
    return results

baseline = evaluate(seed=0)
candidate = evaluate(seed=1)          # in real life: new prompt/model/config
for tid in baseline:
    b, c = baseline[tid], candidate[tid]
    flag = "REGRESSION?" if c["rate"] < b["rate"] else ""
    print(f"{tid}: base={b['rate']:.1f} cand={c['rate']:.1f} "
          f"pass@k={c['pass@k']} pass^k={c['pass^k']} {flag}")
print(json.dumps(candidate, indent=1))  # persist with a config hash (Lesson 05)
```
Every concept in this phase appears in miniature: rubric-as-data, trajectory grading, k repeats, pass@k vs pass^k, baseline diffing. Extensions in rough priority order: Wilson confidence intervals on `rate`, an LLM judge grader with a human-agreement audit, JSONL persistence keyed by config hash, and a `--gate` mode that exits nonzero for CI.

### Use It
Swap `agent()` for a call into your real agent (subprocess or SDK), grow `TASKS` from production incidents, wire the gate into CI, and you have a genuine regression suite. When you outgrow it, Inspect / Braintrust / LangSmith are this pipeline with persistence, UI, and collaboration attached — you'll now be able to read their docs and see the skeleton underneath.

### War Story
When Anthropic, OpenAI, and others publish model cards, the headline tables are outputs of harnesses structurally identical to this one — task sets, repeated sampling, pass@k aggregation, baseline comparison. The pass@k machinery traces straight back to the Codex paper (2021). There is no magic upstream of the leaderboards; there is a for-loop, graders, and statistics. Now you own one.

### Checkpoint
1. Where in the code do outcome and trajectory grading combine, and why keep both fields?
2. Why does `evaluate` reseed, and what would identical seeds across baseline and candidate actually compare?
3. What are the first three extensions you'd add before trusting this harness for a ship/no-ship call?
