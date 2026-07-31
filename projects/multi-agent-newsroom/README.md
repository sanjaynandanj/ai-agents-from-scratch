# Project: Multi-Agent Newsroom

Build a five-agent newsroom that takes one instruction — *"write a story about
X"* — and turns it into a published article with a sources box, including a
real **fact-check bounce-back** where a hallucinated claim gets caught and the
draft goes back to the writer.

No frameworks. No API keys. Pure Python stdlib and a scripted mock LLM, so
every run is deterministic and you can see exactly why each agent did what it
did.

## Why this project

Most "multi-agent" demos are three prompts in a trench coat. This one forces
you to build the parts that actually matter:

1. **Decomposition** — an orchestrator that turns one goal into a pipeline.
2. **Grounding** — a researcher that can only cite a local corpus (its whole
   universe of truth).
3. **Verification with teeth** — a fact-checker that *rejects work* and routes
   it back, not one that rubber-stamps.

## Architecture

```
                       "write a story about X"
                                 |
                                 v
                    +------------------------+
                    |    EDITOR-IN-CHIEF     |   (orchestrator)
                    |  decompose + route +   |
                    |  own the revision loop |
                    +-----------+------------+
             ______________/    |    \_______________________
            /               |       |               \        \
            v               v       v                v        v
      +---------+    +-----------+  +--------+  +---------+  +----------+
      | PLANNER |    | RESEARCHER|  | WRITER |  |  FACT-  |  |  COPY-   |
      | outline |    | search    |  | draft  |  | CHECKER |  |  EDITOR  |
      +---------+    | corpus    |  +---+----+  +----+----+  | polish   |
                     +-----------+      |            |       +----------+
                                        |   REJECT   |
                                        +<-----------+
                                          (round-trip: bad claim
                                           bounced back to writer)
```

Data flow: `plan -> research -> draft -> fact-check -> [revise] -> polish`.

The fact-checker is the only agent allowed to send work *backwards*. The
editor-in-chief owns that loop and caps it at two rounds — even a real
newsroom eventually spikes a story.

## The mock LLM

`MockLLM` is ~40 lines of scripted text generation. Crucially, its `draft()`
method **deliberately hallucinates one claim** on the first pass ("Bees can
recognize individual human faces from fifty meters away") that appears nowhere
in the corpus. This is the plot: your fact-checker must catch it by
cross-referencing every checkable sentence against source facts.

Swap `MockLLM` for a real API client later; the pipeline never needs to know.

## Milestones

Build it in this order. Each milestone runs on its own.

1. **Corpus + Researcher.** Hardcode 3-4 source documents (id, outlet, title,
   topic, facts). Write a keyword-overlap search. Test: query "urban
   beekeeping" returns S1-S3, query "public transit" returns S4 only.
2. **Planner + Writer.** Planner emits a 3-beat outline. Writer stitches an
   opener plus all researched facts into one draft string.
3. **Fact-Checker.** Split the draft into sentences, decide which are
   "checkable" (contains a digit is a fine heuristic), and verify each against
   the normalized set of source facts. Return the rejects.
4. **The round-trip.** Editor sees rejects, logs the bounce, calls the writer
   again with revision notes. Writer re-drafts without the poisoned claim.
   Fact-checker approves on round two. This is the money milestone.
5. **Copy-Editor + presentation.** Normalize whitespace, tighten units, then
   print the final story in a box with a labeled sources section.
6. **Transcript.** Every agent action logged as `[AGENT-NAME] message` so a
   reader can replay the whole run from the console output.

## Run it

```
python newsroom.py --demo
python newsroom.py --topic "public transit"
python newsroom.py --topic "celebrity gossip"   # no sources -> story spiked
```

`--demo` runs the full pipeline on "urban beekeeping" and exits by itself.
Expected shape of the transcript:

```
[EDITOR         ] Assignment received: write a story about 'urban beekeeping'.
[PLANNER        ] Outline: The numbers... | Why it is growing | ...
[RESEARCHER     ] Query 'urban beekeeping' -> 3 source(s): S1, S2, S3
[WRITER         ] First draft (XXX chars, 8 claims).
[FACT-CHECKER   ] REJECT unverified claim: "Bees can recognize..."
[EDITOR         ] Bouncing draft back to writer (round 1).
[WRITER         ] Revised draft ...
[FACT-CHECKER   ] All factual claims trace to a source. Approved.
[COPY-EDITOR    ] Polished style, normalized whitespace and units.
```

followed by the boxed final story and its sources.

## What "done" looks like

- Deterministic: same seed, same story, every run.
- The hallucinated claim never survives to print.
- The transcript alone is enough to reconstruct every decision.
- An unknown topic fails gracefully (story spiked, nonzero exit).

## Extension ideas

- **Second hallucination mode:** make the mock LLM *distort* a real fact
  (change 18 kg to 80 kg) and upgrade the checker from set-membership to
  fuzzy matching plus a numeric-mismatch detector.
- **Competing drafts:** run two writers with different seeds and let the
  editor pick using a scoring rubric (see the `agent-eval-harness` project).
- **Interview agent:** add a "quotes" field to sources and a reporter agent
  that must attribute at least one quote per story.
- **Real LLM drop-in:** replace `MockLLM` with an API call, keep the
  fact-checker exactly as-is, and watch it earn its salary.
- **Parallel desks:** give the editor two topics at once and interleave the
  transcripts with a per-story tag.
