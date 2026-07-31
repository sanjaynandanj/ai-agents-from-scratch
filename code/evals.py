"""Eval harness: task suites, graders, pass@k, and a scorecard.

Key insight: agents are stochastic software, so a single green run proves
nothing. You need a fixed task suite, mechanical graders (exact / contains /
LLM-judge), and pass@k across seeds to separate "reliably works" from "got
lucky once" -- the scorecard is the agent's real interface contract.
"""

import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import re

from mock_llm import MockLLM
from agent_loop import ReActAgent, make_tools, KB


# --- Agent under test: a small policy that turns a task into an LLM script ---
def agent_fn(task_input: str, seed: int) -> str:
    """Builds the same ReAct agent per task; seed drives answer variance."""
    math_expr = re.search(r"[\d\.\s\+\-\*\/\(\)]{3,}", task_input)
    kb_key = next((k for k in KB if k.split("_")[0] in task_input.lower()), None)
    if math_expr:
        expr = math_expr.group().strip()
        script = [
            {"type": "tool_call", "name": "calculator",
             "arguments": {"expression": expr}},
            lambda msgs: {"type": "text", "content": "The answer is %s."
                          % msgs[-1]["content"].split("-> ")[-1]},
        ]
    elif kb_key:
        script = [
            {"type": "tool_call", "name": "kb_lookup", "arguments": {"key": kb_key}},
            lambda msgs: {"type": "text", "content":
                          msgs[-1]["content"].split("-> ")[-1]},
        ]
    else:
        script = ["I could not find that in my sources."]
    # flakiness makes ~1 in 3 seeds fumble the final phrasing: real variance.
    llm = MockLLM(script=script, seed=seed, flakiness=0.34)
    return ReActAgent(llm, make_tools(), max_turns=4).run(task_input, verbose=False)


# --- Graders ---
def grade_exact(answer, expected, rubric=None):
    return answer.strip() == expected

def grade_contains(answer, expected, rubric=None):
    return expected.lower() in answer.lower()

def grade_llm_judge(answer, expected, rubric):
    # Mock judge: passes iff the rubric's key requirement shows up. A real
    # judge would be a strong model prompted with the rubric.
    judge = MockLLM(rules=[(expected.lower(), "PASS")])
    verdict = judge.complete([
        {"role": "user", "content": "Rubric: %s\nAnswer: %s" % (rubric, answer)}])
    return verdict["content"] == "PASS"

GRADERS = {"exact": grade_exact, "contains": grade_contains, "judge": grade_llm_judge}

SUITE = [
    {"id": "math-1", "input": "What is 12 * (3 + 5)?", "expected": "96",
     "grader": "contains", "rubric": "must state the product 96"},
    {"id": "kb-1", "input": "Who is the acme CEO?", "expected": "Dana Reyes",
     "grader": "judge", "rubric": "must name the CEO found in the KB"},
    {"id": "math-2", "input": "Compute 100 / 4 exactly.", "expected": "25",
     "grader": "contains", "rubric": "must state 25"},
    # Fails: the KB has no such entry, but the suite expects a real answer.
    {"id": "kb-2", "input": "What is the capital of Freedonia?",
     "expected": "Freedonia City", "grader": "contains",
     "rubric": "must name Freedonia City"},
]


def run_suite(suite, k=3):
    print("=== Eval run: %d tasks, pass@%d over seeds 0..%d ===\n"
          % (len(suite), k, k - 1))
    rows = []
    for task in suite:
        passes = []
        for seed in range(k):
            answer = agent_fn(task["input"], seed) or ""
            ok = GRADERS[task["grader"]](answer, task["expected"], task["rubric"])
            passes.append(ok)
            print("[%s seed=%d] %-42s -> %r  %s"
                  % (task["id"], seed, task["input"][:42], answer[:40],
                     "PASS" if ok else "FAIL"))
        rows.append((task["id"], task["grader"], passes))
        print()
    return rows


def scorecard(rows, k):
    print("=== Scorecard ===")
    header = "%-8s %-9s %-8s %-8s %s" % ("task", "grader", "pass@1", "pass@%d" % k,
                                         "verdict")
    print(header)
    print("-" * len(header))
    total = 0
    for task_id, grader, passes in rows:
        p1, pk = passes[0], any(passes)
        total += pk
        verdict = "ok" if pk else "BROKEN" if not any(passes) else ""
        if pk and not all(passes):
            verdict = "flaky"
        print("%-8s %-9s %-8s %-8s %s"
              % (task_id, grader, "yes" if p1 else "no", "yes" if pk else "no",
                 verdict))
    print("-" * len(header))
    print("suite pass@%d: %d/%d" % (k, total, len(rows)))


if __name__ == "__main__":
    k = 3
    rows = run_suite(SUITE, k=k)
    scorecard(rows, k)
    print("\nkb-2 fails at every seed (missing capability, not bad luck), while")
    print("flaky rows fail only at some seeds -- pass@k is what tells those two")
    print("failure modes apart, and they need completely different fixes.")
