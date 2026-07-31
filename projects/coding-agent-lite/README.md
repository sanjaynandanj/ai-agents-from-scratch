# Project: Coding Agent Lite

> **MOTTO:** A coding agent is a while-loop that reads test failures and
> refuses to take "red" for an answer.

Devin, Claude Code, Copilot Workspace -- strip the branding and the demo
videos and you find the same skeleton: run the tests, read the failure,
edit a file, run the tests again. This project builds that skeleton in a
single stdlib-only Python file, with a scripted mock LLM standing in for
the model. When the loop makes sense to you, swapping in a real API is a
one-function change.

## What you're building

An agent that receives a task ("make this test suite pass"), works inside
a disposable sandbox containing a small buggy module, and iterates until
the suite is green -- narrating every observe/think/act step as it goes.

```
                 +--------------------------------------+
                 |            CODING AGENT LITE          |
                 +--------------------------------------+

   +-----------+      +------------+      +--------------+
   | read task |----->| run tests  |----->| green?       |
   +-----------+      | (subproc)  |      +------+-------+
                      +------------+             |
                            ^              yes   |   no
                            |              +-----+------+
                            |              |            v
                      +-----+------+   +-------+  +------------+
                      | apply edit |   | DONE  |  | read files |
                      +-----+------+   +-------+  +-----+------+
                            ^                           |
                            |                           v
                      +-----+-------------+   +-----------------+
                      | LLM proposes edit |<--| failure text +  |
                      | (mock: scripted)  |   | file contents   |
                      +-------------------+   +-----------------+
```

The sandbox holds two files:

- `mathkit.py` -- three functions, two planted bugs (an off-by-one in
  `average`, a wrong-bound return in `clamp`)
- `test_mathkit.py` -- a plain `unittest` suite that catches both

The agent finds and fixes both bugs across multiple iterations, exactly
one minimal edit per turn.

## Why a mock LLM?

Because the interesting part is the *loop*, not the model. The mock's
`propose_edit(task, file_contents, test_output)` has the same signature a
real model adapter would have. It pattern-matches the failing test name
and returns an edit dict `{file, old, new, rationale}` -- the same
old-string/new-string edit format real coding agents use. Deterministic,
offline, free, and it never hallucinates a fix for a test that passes.

## Milestones

Build it yourself in this order; each milestone runs on its own.

1. **Sandbox builder.** Write `mathkit.py` and `test_mathkit.py` into a
   `tempfile.mkdtemp()` directory. Verify with a manual
   `python -m unittest` that the suite fails.
2. **Test-runner tool.** Wrap `subprocess.run([sys.executable, "-m",
   "unittest", ...], cwd=sandbox)` and return `(green, output)`. The
   subprocess matters: it re-imports edited code fresh every run, which a
   long-lived in-process import would not.
3. **File tools.** `read_files` (whole sandbox into a dict) and
   `apply_edit` (exact-match string replace; raise if the target string
   is missing -- silent no-op edits are how agents lie to themselves).
4. **Mock LLM.** A fix script keyed on failing-test names, filtered by
   "has this edit already been applied?" so it never repeats itself.
5. **The loop.** run tests -> if red, read files -> ask LLM -> apply ->
   repeat, capped by an iteration budget, with three exit states: green,
   stuck (LLM out of ideas), or budget exhausted.
6. **Narration + cleanup.** Print each observe/think/act beat, then
   `shutil.rmtree` the sandbox in a `finally` block so a crash never
   leaves litter behind.

## How to run

```bash
python agent.py --demo
```

No arguments prints help. The demo needs no network, no keys, and no
setup; it creates its own temp directory and deletes it on the way out.
Expected shape of the run:

- Iteration 1: suite RED (2 failures) -> fix `average`
- Iteration 2: suite RED (1 failure) -> fix `clamp`
- Iteration 3: suite GREEN -> done, sandbox removed

Exit code is 0 on green, 1 otherwise -- so the agent itself is testable
from CI.

## What to notice while it runs

- **The agent never trusts itself.** It does not declare victory after
  applying an edit; it reruns the tests. Verification is the loop's
  backbone.
- **One minimal edit per iteration.** Batch edits feel faster but make
  failure attribution impossible. When a batch turns the suite red-der,
  which edit did it?
- **`running_total` is never touched.** A correct function plus a
  failing suite tempts sloppy agents into "refactoring" innocent code.
  The failure text keeps the mock honest; a good prompt does the same
  for a real model.
- **The budget.** `MAX_ITERATIONS = 5` is the difference between an
  agent and an infinite loop with API costs.

## Extension ideas

1. **Plug in a real model.** Replace `MockLLM.propose_edit` with a call
   to any chat API: send the task, the file contents, and the last test
   output; ask for JSON `{file, old, new, rationale}`; parse and return.
   The loop, tools, and narration need zero changes -- that's the point
   of the interface.
2. **Harder bugs.** Plant a bug whose failure message doesn't name the
   broken function (e.g., a helper used by two tests). Now the agent
   needs a localization step -- grep, or reading tracebacks properly.
3. **Edit safety rails.** Reject edits that touch `test_mathkit.py`.
   Real incident class: agents "fixing" tests by deleting assertions.
4. **Diff-based edits.** Swap old/new string replacement for unified
   diffs and a tiny patch applier. Compare failure modes: which format
   survives a slightly-wrong model output better?
5. **Two-phase loop.** Add a "plan" turn before the first edit and a
   "reflect" turn after each red rerun. Measure whether iterations drop.
6. **A second sandbox task.** Parameterize the sandbox builder so the
   same agent fixes a different module -- the moment your fix script
   stops generalizing is the moment you understand why real models earn
   their keep.

## Checkpoint

- Why run tests in a subprocess instead of importing the module and
  calling `unittest` in-process?
- What are the three ways the loop can end, and why must "stuck" exist?
- Why should `apply_edit` raise when the old string isn't found, instead
  of silently doing nothing?
