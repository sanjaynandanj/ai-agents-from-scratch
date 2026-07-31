# Project: Agent Eval Harness

You cannot improve an agent you cannot measure. This project builds the
measuring stick: a task suite, three different graders (which will happily
disagree with each other), pass@3 sampling, a leaderboard, and a regression
gate fit for CI.

Everything is stdlib, deterministic, and self-contained — including the two
agents under test and a mock-LLM judge, all scripted so runs are reproducible
down to the byte.

## Why this project

Three uncomfortable truths about agent evals, and this harness makes you feel
each one:

1. **The grader IS the benchmark.** The same answer scores differently under
   exact-match, keyword rubric, and a judge. "The answer is Paris, of course."
   fails exact-match and aces the other two. Which grader is right? Depends
   what you're shipping.
2. **Agents are stochastic; single runs lie.** With temperature-like variance,
   one attempt tells you almost nothing. pass@k answers "can it do this at
   all?" while single-shot answers "does it do this reliably?" — different
   questions, different numbers.
3. **Evals only matter if they can block a merge.** Hence the regression gate
   with a nonzero exit code.

## Architecture

```
   +------------+     +-------------+       +--------------------------+
   | TASK SUITE |     |   AGENTS    |       |         GRADERS          |
   | 8 tasks:   |     | good-agent  |       |  exact     (strict ==)   |
   |  prompt    |---->| sloppy-agent|--+--->|  contains  (rubric kws)  |
   |  expected  |     | (seeded     |  |    |  judge     (mock-LLM     |
   |  rubric    |     |  variance)  |  |    |            rubric score) |
   +------------+     +-------------+  |    +------------+-------------+
                                       |                 |
                            x3 attempts (pass@3)         v
                                       |    +--------------------------+
                                       +--->|  LEADERBOARD (ascii bars)|
                                            |  REGRESSION GATE         |
                                            |  exit 1 if good-agent    |
                                            |  drops below threshold   |
                                            +--------------------------+
```

## The cast

- **good-agent** knows every answer but has a 30% chance per attempt of
  getting chatty ("The answer is 42, of course.") — verbatim correct content,
  wrapped in fluff. Watch which graders forgive it.
- **sloppy-agent** half-remembers: sometimes wrong ("41"), sometimes truncated
  ("Pa" for "Paris"), sometimes fine. pass@3 rescues it more often than you'd
  expect — which is exactly the caveat with pass@k metrics.
- **The judge** is a deterministic stand-in for an LLM grader: rewards rubric
  coverage and the expected answer appearing verbatim, penalizes bloat. Same
  signature as a real API-backed judge, so it's a drop-in swap later.

## Milestones

1. **Task suite.** 8 tasks as dicts: `prompt`, `expected`, `rubric` keywords.
   Mix trivially-checkable tasks (math, spelling) with fuzzy ones (summary).
2. **Two agents.** A `run(task, attempt)` interface. Seed variance per
   `(agent, task, attempt)` — use `zlib.crc32` for the key, **never `hash()`**
   (Python randomizes string hashes per process; your "deterministic" eval
   would change every run and you would lose an afternoon to it).
3. **Three graders.** Uniform signature: `(answer, task) -> (score, passed)`.
   Exact match, contains-all rubric keywords, and the mock judge.
4. **pass@3.** For each agent x task x grader: 3 attempts, task passes if any
   attempt passes. Print every attempt as `score:pass` cells so disagreements
   between graders are visible in the raw table.
5. **Leaderboard.** Agent x grader pass-rate matrix with ASCII bars, plus a
   per-agent mean row.
6. **Regression gate.** If good-agent's mean falls below the threshold, exit
   nonzero (CI blocks the merge). In `--demo` mode, report the gate verdict
   but always exit 0.

## Run it

```
python harness.py --demo       # full detail, gate is report-only, exit 0
python harness.py --quiet      # leaderboard + gate only
python harness.py              # gate failure would exit 1 (CI mode)
```

Exits by itself. Expected shape:

```
### good-agent
task      grader    attempts (score:pass) -> pass@3
capital   exact     1.00:Y 0.00:n 1.00:Y -> PASS
capital   contains  1.00:Y 1.00:Y 1.00:Y -> PASS
...
LEADERBOARD  (pass@3 rate over 8 tasks)
good-agent     exact      87.5%  |##################..|
good-agent     contains  100.0%  |####################|
...
REGRESSION GATE: good-agent mean 95.8% vs threshold 70.0% -> PASS
```

(Your exact numbers are fixed by the seed but may differ from the sketch
above — the point is they will be *identical every run*.)

## What "done" looks like

- Two consecutive runs produce byte-identical output.
- At least one task where the three graders disagree on the same answer.
- The gate demonstrably exits 1: temporarily raise `GATE_THRESHOLD` to 1.01
  and run without `--demo`.

## Extension ideas

- **pass@1 vs pass@3 side-by-side** — quantify exactly how much sampling
  flatters the sloppy agent.
- **Grader agreement matrix** — Cohen's-kappa-style pairwise agreement
  between graders; low agreement means your benchmark is measuring grader
  choice, not agent quality.
- **Judge calibration** — hand-label 10 answers, then tune the judge's
  weights until it matches your labels; this is real eval work in miniature.
- **Cost column** — charge each agent fake tokens per answer and rank by
  quality-per-token instead of raw pass rate.
- **Adversarial task** — add a task whose rubric keywords appear in the
  prompt itself, and watch the contains grader get gamed by an agent that
  just echoes the prompt.
