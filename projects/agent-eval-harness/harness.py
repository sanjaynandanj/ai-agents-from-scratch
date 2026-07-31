#!/usr/bin/env python3
"""agent-eval-harness: evaluate two toy agents on an 8-task suite with three
graders, pass@3 sampling, a leaderboard, and a regression gate.

Pure Python 3 stdlib. Deterministic (seeded via crc32, not hash()).

Usage:
    python harness.py --demo          # full run, always exits 0
    python harness.py                 # same, but gate failure exits 1
"""

import argparse
import random
import sys
import zlib

BASE_SEED = 1337
ATTEMPTS = 3          # the "3" in pass@3
GATE_THRESHOLD = 0.70  # good agent must average >= this across graders

# ---------------------------------------------------------------------------
# Task suite: prompt, expected output, rubric keywords
# ---------------------------------------------------------------------------

TASKS = [
    {"id": "capital",  "prompt": "What is the capital of France?",
     "expected": "Paris", "rubric": ["paris"]},
    {"id": "math",     "prompt": "What is 17 + 25?",
     "expected": "42", "rubric": ["42"]},
    {"id": "reverse",  "prompt": "Reverse the word 'agent'.",
     "expected": "tnega", "rubric": ["tnega"]},
    {"id": "primes",   "prompt": "List the primes below 10.",
     "expected": "2, 3, 5, 7", "rubric": ["2", "3", "5", "7"]},
    {"id": "summary",  "prompt": "Summarize: 'The cat sat on the mat.'",
     "expected": "A cat sat on a mat.", "rubric": ["cat", "mat"]},
    {"id": "json",     "prompt": "Return JSON with key 'status' set to 'ok'.",
     "expected": "{\"status\": \"ok\"}", "rubric": ["status", "ok"]},
    {"id": "haiku",    "prompt": "How many syllables in a haiku?",
     "expected": "17", "rubric": ["17"]},
    {"id": "spell",    "prompt": "Spell 'eval' backwards.",
     "expected": "lave", "rubric": ["lave"]},
]

# ---------------------------------------------------------------------------
# Agents: scripted, with seeded per-attempt variance (like temperature > 0)
# ---------------------------------------------------------------------------

def _rng_for(agent, task_id, attempt):
    """Stable RNG per (agent, task, attempt). NOTE: never use hash() here --
    Python randomizes string hashes per process, which would silently break
    reproducibility. crc32 is stable forever."""
    key = "%s:%s:%s:%d" % (BASE_SEED, agent, task_id, attempt)
    return random.Random(zlib.crc32(key.encode("ascii")))

class GoodAgent:
    """Knows the answers; occasionally gets chatty (verbatim wrappers)."""
    name = "good-agent"

    def run(self, task, attempt):
        rng = _rng_for(self.name, task["id"], attempt)
        ans = task["expected"]
        roll = rng.random()
        if roll < 0.30:  # chatty mode: kills exact-match, survives the rest
            return "The answer is %s, of course." % ans
        return ans

class SloppyAgent:
    """Half-remembers things, truncates, and sometimes just guesses."""
    name = "sloppy-agent"

    WRONG = {"math": "41", "reverse": "tnaga", "json": "{'status':",
             "haiku": "around 14 or so", "spell": "vale"}

    def run(self, task, attempt):
        rng = _rng_for(self.name, task["id"], attempt)
        roll = rng.random()
        if roll < 0.35:
            return self.WRONG.get(task["id"], task["expected"] + ", I think? Hard to say.")
        if roll < 0.55:
            return task["expected"][: max(1, len(task["expected"]) // 2)]  # truncation
        return task["expected"]

AGENTS = [GoodAgent(), SloppyAgent()]

# ---------------------------------------------------------------------------
# Graders: each returns (score in [0,1], passed bool)
# ---------------------------------------------------------------------------

def grade_exact(answer, task):
    ok = answer.strip() == task["expected"]
    return (1.0 if ok else 0.0), ok

def grade_contains_all(answer, task):
    low = answer.lower()
    hits = sum(1 for k in task["rubric"] if k.lower() in low)
    frac = hits / len(task["rubric"])
    return frac, hits == len(task["rubric"])

def grade_llm_judge(answer, task):
    """Mock-LLM rubric judge: deterministic scoring that behaves like a decent
    model judge -- rewards rubric coverage and the expected answer appearing,
    penalizes bloat. Swap in a real API call later, same signature."""
    low = answer.lower()
    coverage = sum(1 for k in task["rubric"] if k.lower() in low) / len(task["rubric"])
    bonus = 0.25 if task["expected"].lower() in low else 0.0
    bloat = max(0, len(answer) - (4 * len(task["expected"]) + 40))
    penalty = min(0.3, bloat / 200.0)
    score = max(0.0, min(1.0, 0.75 * coverage + bonus - penalty))
    return round(score, 3), score >= 0.70

GRADERS = [("exact", grade_exact), ("contains", grade_contains_all),
           ("judge", grade_llm_judge)]

# ---------------------------------------------------------------------------
# Evaluation loop: pass@3 per (agent, task, grader)
# ---------------------------------------------------------------------------

def evaluate(verbose=True):
    results = {}  # (agent, grader) -> list of per-task pass bools
    for agent in AGENTS:
        if verbose:
            print("\n### %s" % agent.name)
            print("%-9s %-9s %s" % ("task", "grader", "attempts (score:pass) -> pass@%d" % ATTEMPTS))
            print("-" * 66)
        for task in TASKS:
            answers = [agent.run(task, a) for a in range(ATTEMPTS)]
            for gname, gfn in GRADERS:
                graded = [gfn(ans, task) for ans in answers]
                passed = any(p for _, p in graded)
                results.setdefault((agent.name, gname), []).append(passed)
                if verbose:
                    cells = " ".join("%.2f:%s" % (s, "Y" if p else "n")
                                     for s, p in graded)
                    print("%-9s %-9s %s -> %s"
                          % (task["id"], gname, cells, "PASS" if passed else "FAIL"))
    return results

def bar(frac, width=20):
    n = int(round(frac * width))
    return "#" * n + "." * (width - n)

def leaderboard(results):
    print("\n" + "=" * 66)
    print("LEADERBOARD  (pass@%d rate over %d tasks)" % (ATTEMPTS, len(TASKS)))
    print("=" * 66)
    print("%-14s %-9s %-7s %s" % ("agent", "grader", "rate", "bar"))
    print("-" * 66)
    means = {}
    for agent in AGENTS:
        rates = []
        for gname, _ in GRADERS:
            passes = results[(agent.name, gname)]
            rate = sum(passes) / len(passes)
            rates.append(rate)
            print("%-14s %-9s %5.1f%%  |%s|"
                  % (agent.name, gname, 100 * rate, bar(rate)))
        means[agent.name] = sum(rates) / len(rates)
        print("%-14s %-9s %5.1f%%  |%s|  <- mean"
              % ("", "MEAN", 100 * means[agent.name], bar(means[agent.name])))
        print("-" * 66)
    return means

def regression_gate(means, demo):
    good = means[GoodAgent.name]
    ok = good >= GATE_THRESHOLD
    print("\nREGRESSION GATE: %s mean %.1f%% vs threshold %.1f%% -> %s"
          % (GoodAgent.name, 100 * good, 100 * GATE_THRESHOLD,
             "PASS" if ok else "FAIL"))
    if not ok and not demo:
        print("Gate failed: exiting nonzero so CI blocks the merge.")
        return 1
    if not ok:
        print("(--demo mode: reporting only, exiting 0)")
    return 0

def main(argv=None):
    ap = argparse.ArgumentParser(description="Agent evaluation harness.")
    ap.add_argument("--demo", action="store_true",
                    help="full run; gate is report-only and exit code is 0")
    ap.add_argument("--quiet", action="store_true", help="leaderboard only")
    args = ap.parse_args(argv)

    print("agent-eval-harness :: %d agents x %d tasks x %d graders, pass@%d"
          % (len(AGENTS), len(TASKS), len(GRADERS), ATTEMPTS))
    results = evaluate(verbose=not args.quiet)
    means = leaderboard(results)
    return regression_gate(means, demo=args.demo)

if __name__ == "__main__":
    sys.exit(main())
