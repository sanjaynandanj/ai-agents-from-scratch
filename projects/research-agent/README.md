# Project: Research Agent

> **MOTTO:** A research agent is a librarian with a to-do list and a
> paranoid fact-checker standing behind it.

"Deep research" products all decompose into the same pipeline: break the
question into sub-questions, search, read the hits, keep notes, write a
report, and cite everything. This project builds that whole pipeline in
one stdlib-only file over a local ten-article corpus -- with real TF-IDF
search doing real ranking, a scripted mock LLM doing the "thinking," and
a mechanical verifier that refuses to publish uncited claims.

## What you're building

An agent that takes a research task ("how did coffee spread, and what
does caffeine do?"), plans three searchable sub-questions, retrieves and
filters sources, and emits a markdown report where every claim ends in a
`[n]` citation mapped to a source list.

```
   +----------------------------- TASK -----------------------------+
   | "Write a fully cited report on coffee's spread and caffeine."  |
   +--------------------------------+--------------------------------+
                                    v
                      +-------------------------+
                      | PLAN (mock LLM)          |
                      | 3 keyword-rich questions |
                      +------------+------------+
                                   v         for each question
        +--------------------------+---------------------------+
        |  +-----------+    +-----------+    +--------------+  |
        |  | SEARCH    |--->| READ hits |--->| TAKE NOTE    |  |
        |  | TF-IDF    |    | (corpus)  |    | or DISCARD   |  |
        |  +-----------+    +-----------+    +------+-------+  |
        +-------------------------------------------|----------+
                                                    v
                      +-------------------------+   notes + sources
                      | SYNTHESIZE (mock LLM)   |
                      | markdown, [n] per claim |
                      +------------+------------+
                                   v
                      +-------------------------+     fail -> reject
                      | VERIFY: every claim     |------------------->
                      | cited? every [n] real?  |
                      +------------+------------+
                                   v  pass
                            FINAL REPORT + SOURCES
```

The corpus is six coffee articles plus four deliberate distractors (tea,
chocolate, printing, the Silk Road) so the ranking step has something to
actually reject.

## The parts, and which are real

| Stage | Real or mocked? |
|---|---|
| Planning sub-questions | Mocked (scripted list) |
| Search | **Real** TF-IDF + cosine similarity, ~40 lines |
| Relevance filtering | Mocked (note script returns None for off-topic docs) |
| Synthesis | Mocked (assembles notes into sections) |
| Citation verification | **Real** -- regex over every line, no exceptions |

That split is deliberate: retrieval and verification are deterministic
machinery you should own; the fuzzy language steps are the model's job.

## Milestones

1. **Corpus + tokenizer.** Ten `(title, body)` articles in a dict; a
   tokenizer that lowercases, splits on `[a-z]+`, and drops stopwords.
2. **TF-IDF index.** Compute `idf = log(N/df)` per term, build one
   normalized vector per document, score queries by dot product. Add a
   deterministic tie-break (sort by `(-score, doc_id)`) -- unordered
   dicts are where "it works on my machine" agents are born.
3. **Planner.** Mock LLM returns `(heading, question)` pairs. Note the
   questions are stuffed with searchable keywords ("Sufi monasteries",
   "penny universities") -- real research agents are prompted the same
   way, because conversational questions retrieve poorly.
4. **Note-taker.** For each hit, the mock either extracts one claim or
   returns `None` (off-topic). Assign each *document* one stable source
   number the first time it is kept, so repeat hits reuse a citation.
5. **Synthesizer.** Group claims under their question's heading; append
   ` [n].` to every claim line.
6. **Verifier.** Every non-heading, non-blank line must end with
   `[n]`, and every cited `n` must exist in the source table. Any
   violation rejects the whole report (exit code 1).

## How to run

```bash
python agent.py --demo
```

Offline, no keys, seeded, exits on its own. You'll see four phases:
the plan, per-question search hits with scores, the note log, the
verification verdict, then the report with its numbered source list.

## What to notice while it runs

- **Distractors get filtered twice.** Once by ranking (low cosine
  score), once by the note-taker (returns None). Defense in depth is
  cheaper than a retraction.
- **Citations are assigned at note time, not write time.** The report
  writer never invents source numbers; it can only spend the ones the
  research phase earned. This is the single best anti-hallucination
  trick in the retrieval playbook.
- **The verifier is dumb on purpose.** It checks *form*, not truth --
  but form is checkable at zero cost, and an uncited sentence is a
  hallucination with nowhere to hide.

## Extension ideas

1. **Plug in a real model.** Replace `plan`, `take_note`, and
   `synthesize` with API calls (JSON out). Keep TF-IDF and the verifier
   exactly as they are -- watch how often the verifier catches a real
   model emitting an uncited flourish.
2. **Real retrieval.** Point the corpus loader at a directory of `.txt`
   or `.md` files instead of a dict. TF-IDF doesn't care.
3. **Claim-level verification.** Upgrade the verifier: for each cited
   claim, check word overlap between the claim and its cited source
   text. Now `[3]` pasted onto the wrong sentence gets caught too.
4. **Iterative research.** After synthesis, have the planner read the
   draft and emit follow-up questions for thin sections -- the loop is
   what turns "search" into "research."
5. **BM25.** Swap cosine TF-IDF for BM25 scoring and compare rankings
   on the same queries; it's ~15 changed lines and a classic exercise.
6. **Contradiction hunting.** Add two corpus articles that disagree and
   make the synthesizer surface the disagreement instead of silently
   picking a side.

## Checkpoint

- Why do the planned sub-questions look like keyword soup instead of
  natural questions?
- The verifier can't tell a true claim from a false one. Why is it still
  worth having?
- Why assign source numbers during research instead of letting the
  synthesizer number its own citations?
