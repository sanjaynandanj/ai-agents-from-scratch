#!/usr/bin/env python3
"""coding-agent-lite: a tiny coding agent that fixes a buggy module.

The loop: read task -> run tests -> read failure -> propose edit ->
apply edit -> rerun tests -> repeat until green.

Pure stdlib. Deterministic. The "LLM" is a scripted mock that knows the
fixes -- swap it for a real API and the loop does not change.

Run:  python agent.py --demo
"""

import argparse
import os
import random
import shutil
import subprocess
import sys
import tempfile

MAX_ITERATIONS = 5

# ---------------------------------------------------------------------------
# The sandbox: a buggy module + a test file, written to a temp dir.
# ---------------------------------------------------------------------------

BUGGY_MODULE = '''\
"""mathkit: a tiny numeric toolbox. (Contains two planted bugs.)"""


def average(nums):
    """Return the arithmetic mean of a non-empty list."""
    return sum(nums) / (len(nums) + 1)


def clamp(value, low, high):
    """Constrain value to the closed interval [low, high]."""
    if value < low:
        return high
    if value > high:
        return high
    return value


def running_total(nums):
    """Return the list of cumulative sums. (This one is correct.)"""
    out, total = [], 0
    for n in nums:
        total += n
        out.append(total)
    return out
'''

TEST_MODULE = '''\
import unittest

import mathkit


class TestMathkit(unittest.TestCase):
    def test_average(self):
        self.assertEqual(mathkit.average([2, 4, 6]), 4.0)
        self.assertEqual(mathkit.average([10]), 10.0)

    def test_clamp(self):
        self.assertEqual(mathkit.clamp(-5, 0, 10), 0)
        self.assertEqual(mathkit.clamp(15, 0, 10), 10)
        self.assertEqual(mathkit.clamp(7, 0, 10), 7)

    def test_running_total(self):
        self.assertEqual(mathkit.running_total([1, 2, 3]), [1, 3, 6])


if __name__ == "__main__":
    unittest.main()
'''


# ---------------------------------------------------------------------------
# The mock LLM. Real agents send (task + file contents + test output) to a
# model and get back an edit. Ours pattern-matches the failure text against
# a script of known fixes. Same interface, zero network calls.
# ---------------------------------------------------------------------------

class MockLLM:
    """A scripted stand-in for a coding model.

    propose_edit() receives everything a real model would receive and
    returns an edit dict: {file, old, new, rationale}. It returns fixes
    one at a time, just like a cautious real model asked for minimal diffs.
    """

    FIX_SCRIPT = [
        {
            "trigger": "test_average",
            "file": "mathkit.py",
            "old": "    return sum(nums) / (len(nums) + 1)",
            "new": "    return sum(nums) / len(nums)",
            "rationale": (
                "test_average expects mean([2,4,6]) == 4.0 but got 3.0. "
                "The denominator is len(nums) + 1 -- a classic off-by-one. "
                "Divide by len(nums)."
            ),
        },
        {
            "trigger": "test_clamp",
            "file": "mathkit.py",
            "old": "    if value < low:\n        return high",
            "new": "    if value < low:\n        return low",
            "rationale": (
                "test_clamp expects clamp(-5, 0, 10) == 0 but got 10. "
                "The below-range branch returns the HIGH bound. It should "
                "return low."
            ),
        },
    ]

    def propose_edit(self, task, file_contents, test_output):
        """Return one edit for the first known failure, or None."""
        for fix in self.FIX_SCRIPT:
            failing = fix["trigger"] in test_output
            not_yet_applied = fix["old"] in file_contents.get(fix["file"], "")
            if failing and not_yet_applied:
                return dict(fix)
        return None


# ---------------------------------------------------------------------------
# Tools the agent can use: read files, edit files, run the test suite.
# ---------------------------------------------------------------------------

def tool_read_files(sandbox):
    contents = {}
    for name in sorted(os.listdir(sandbox)):
        if name.endswith(".py"):
            with open(os.path.join(sandbox, name), "r", encoding="utf-8") as f:
                contents[name] = f.read()
    return contents


def tool_apply_edit(sandbox, edit):
    path = os.path.join(sandbox, edit["file"])
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    if edit["old"] not in text:
        raise ValueError("edit target not found in %s" % edit["file"])
    with open(path, "w", encoding="utf-8") as f:
        f.write(text.replace(edit["old"], edit["new"], 1))


def tool_run_tests(sandbox):
    """Run the suite in a subprocess so edited code is re-imported fresh."""
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", "test_mathkit", "-v"],
        cwd=sandbox,
        capture_output=True,
        text=True,
        timeout=60,
    )
    output = proc.stdout + proc.stderr
    return proc.returncode == 0, output


# ---------------------------------------------------------------------------
# The agent loop.
# ---------------------------------------------------------------------------

def banner(text, char="="):
    print()
    print(char * 66)
    print(text)
    print(char * 66)


def show_test_summary(output):
    lines = [ln for ln in output.splitlines()
             if ln.startswith(("test_", "FAILED", "OK", "AssertionError"))]
    for ln in lines:
        print("    | " + ln)


def run_agent(sandbox):
    task = "Make the mathkit test suite pass without deleting any tests."
    llm = MockLLM()

    banner("CODING AGENT LITE")
    print("Task    : %s" % task)
    print("Sandbox : %s" % sandbox)

    for iteration in range(1, MAX_ITERATIONS + 1):
        banner("ITERATION %d" % iteration, "-")

        print("[act]     running tests: python -m unittest test_mathkit")
        green, output = tool_run_tests(sandbox)
        show_test_summary(output)

        if green:
            banner("DONE: suite is green after %d iteration(s)." % iteration)
            return True

        print("[observe] suite is RED. Reading source files...")
        files = tool_read_files(sandbox)

        print("[think]   asking the LLM for a minimal edit...")
        edit = llm.propose_edit(task, files, output)
        if edit is None:
            banner("STUCK: LLM has no further fixes. A real agent would "
                   "escalate to a human here.")
            return False

        print("[think]   rationale: %s" % edit["rationale"])
        print("[act]     editing %s:" % edit["file"])
        for ln in edit["old"].splitlines():
            print("    - " + ln)
        for ln in edit["new"].splitlines():
            print("    + " + ln)
        tool_apply_edit(sandbox, edit)

    banner("GAVE UP after %d iterations (budget exhausted)." % MAX_ITERATIONS)
    return False


# ---------------------------------------------------------------------------
# Entry point: build sandbox, run agent, always clean up.
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="A tiny self-testing coding agent.")
    parser.add_argument("--demo", action="store_true", help="run the scripted demo")
    args = parser.parse_args()
    if not args.demo:
        parser.print_help()
        return 0

    random.seed(42)  # nothing random today, but agents should be seeded
    sandbox = tempfile.mkdtemp(prefix="coding_agent_lite_")
    try:
        with open(os.path.join(sandbox, "mathkit.py"), "w", encoding="utf-8") as f:
            f.write(BUGGY_MODULE)
        with open(os.path.join(sandbox, "test_mathkit.py"), "w", encoding="utf-8") as f:
            f.write(TEST_MODULE)
        ok = run_agent(sandbox)
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)
        print("\nSandbox cleaned up: %s" % sandbox)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
