"""Plan-and-execute: draft the whole plan up front, then adapt when it breaks.

Key insight: unlike pure ReAct (one step at a time), a planner commits to a
numbered plan, which makes progress inspectable and failures local. When a
step fails, only the *remaining* plan is redrawn, and a final verification
step checks the output against the original goal before declaring success.
"""

import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import json
import re

from mock_llm import MockLLM

# --- Tools available to the executor ---
METRICS = {"q3_revenue": 1_240_000, "q3_net_income": 186_000}
REPORT = []


def fetch_metric(name):
    if name not in METRICS:
        raise KeyError("metric %r does not exist; available: %s"
                       % (name, sorted(METRICS)))
    return METRICS[name]


def calc(expression):
    if not re.fullmatch(r"[\d\s\.\+\-\*\/\(\)]+", expression):
        raise ValueError("non-arithmetic expression")
    return eval(expression, {"__builtins__": {}})  # pre-validated arithmetic only


def append_report(line):
    REPORT.append(line)
    return "appended"

TOOLS = {"fetch_metric": fetch_metric, "calc": calc, "append_report": append_report}


def parse_plan(text):
    """Plan lines look like: '1. tool_name {"arg": "value"}'."""
    steps = []
    for line in text.strip().splitlines():
        m = re.match(r"\s*\d+\.\s+(\w+)\s+(\{.*\})", line)
        if m:
            steps.append((m.group(1), json.loads(m.group(2))))
    return steps


def execute(steps, results):
    """Run steps in order; on failure, return (failed_step, error)."""
    for i, (tool, args) in enumerate(steps, 1):
        # Late binding: "$last" refers to the previous step's result.
        args = {k: (results[-1] if v == "$last" else v) for k, v in args.items()}
        args = {k: (str(v) if tool == "calc" or tool == "append_report" else v)
                for k, v in args.items()}
        try:
            out = TOOLS[tool](**args)
            results.append(out)
            print("  step %d: %s(%s) -> %s" % (i, tool, args, out))
        except Exception as exc:
            print("  step %d: %s(%s) -> FAILED: %s" % (i, tool, args, exc))
            return steps[i:], "%s failed: %s" % (tool, exc)
    return [], None


if __name__ == "__main__":
    goal = "Compute Q3 profit margin and record it in the report."
    print("=== Plan-and-execute demo ===\nGoal: %s\n" % goal)

    planner = MockLLM(script=[
        # Initial plan guesses a metric name that does not exist.
        '1. fetch_metric {"name": "q3_revenue"}\n'
        '2. fetch_metric {"name": "q3_profit"}\n'
        '3. calc {"expression": "186000 / 1240000 * 100"}\n'
        '4. append_report {"line": "$last"}',
        # Replanner sees the error and swaps in the correct metric name.
        '1. fetch_metric {"name": "q3_net_income"}\n'
        '2. calc {"expression": "186000 / 1240000 * 100"}\n'
        '3. append_report {"line": "$last"}',
        # Verifier judges the final artifact against the goal.
        "PASS: report contains a margin of 15.0 percent, consistent with "
        "186000/1240000.",
    ])

    print("[plan] asking model for a plan...")
    plan_text = planner.complete([{"role": "user", "content": goal}])["content"]
    steps = parse_plan(plan_text)
    for i, (t, a) in enumerate(steps, 1):
        print("  %d. %s %s" % (i, t, a))

    print("\n[execute]")
    results = []
    remaining, error = execute(steps, results)

    if error:
        print("\n[replan] feeding failure back: %r" % error)
        print("  remaining steps that were abandoned: %s" % remaining)
        new_plan = planner.complete([
            {"role": "user", "content": goal},
            {"role": "tool", "content": error}])["content"]
        steps2 = parse_plan(new_plan)
        for i, (t, a) in enumerate(steps2, 1):
            print("  revised %d. %s %s" % (i, t, a))
        print("\n[execute revised plan]")
        remaining, error = execute(steps2, results)

    print("\n[verify]")
    verdict = planner.complete([
        {"role": "user", "content": "Goal: %s\nReport: %s" % (goal, REPORT)}])
    print("  verifier says: %s" % verdict["content"])
    print("\nFinal report artifact: %s" % REPORT)
    print("\nThe plan made the failure diagnosable (step 2, bad metric name),")
    print("and replanning replaced only what remained -- completed work stood.")
