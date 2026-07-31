#!/usr/bin/env python3
"""multi-agent-newsroom: an editor-in-chief orchestrator running a five-agent
newsroom pipeline with a real fact-check revision round-trip.

Pure Python 3 stdlib. Deterministic. ASCII-only output.

Usage:
    python newsroom.py --demo
    python newsroom.py --topic "urban beekeeping"
"""

import argparse
import random
import re
import sys
import textwrap

# ---------------------------------------------------------------------------
# Local source corpus (the researcher's entire universe of truth)
# ---------------------------------------------------------------------------

CORPUS = [
    {
        "id": "S1",
        "outlet": "City Wire",
        "title": "Rooftop hives pass the 3,000 mark",
        "topic": "urban beekeeping",
        "facts": [
            "The city registered 3,112 rooftop beehives in 2025, up from 1,900 in 2022.",
            "Registration became mandatory under the 2021 Apiary Ordinance.",
        ],
    },
    {
        "id": "S2",
        "outlet": "The Ledger",
        "title": "Honey yields defy the drought",
        "topic": "urban beekeeping",
        "facts": [
            "Average yield per urban hive reached 18 kg of honey in 2025.",
            "Urban hives out-produced rural hives by roughly 20 percent last season.",
        ],
    },
    {
        "id": "S3",
        "outlet": "Science Desk",
        "title": "What city bees actually eat",
        "topic": "urban beekeeping",
        "facts": [
            "Pollen samples show city bees forage from over 150 plant species.",
            "Linden trees supplied nearly a third of summer nectar in sampled hives.",
        ],
    },
    {
        "id": "S4",
        "outlet": "City Wire",
        "title": "Transit ridership rebounds",
        "topic": "public transit",
        "facts": [
            "Weekday subway ridership hit 92 percent of 2019 levels in June 2026.",
            "The night bus network expanded to 14 routes this spring.",
        ],
    },
]

# A claim the mock LLM will hallucinate on the first draft. It is NOT in the
# corpus, so the fact-checker must bounce it back. That's the whole lesson.
HALLUCINATION = "Bees can recognize individual human faces from fifty meters away."

# ---------------------------------------------------------------------------
# Mock LLM: a tiny deterministic text engine. No network, no weights, no magic.
# ---------------------------------------------------------------------------

class MockLLM:
    """Scripted 'language model'. Given a role and structured inputs, it emits
    deterministic text. Swap this for a real API later; the pipeline won't care."""

    def __init__(self, seed=7):
        self.rng = random.Random(seed)

    def plan(self, topic):
        return [
            "The numbers: how big is %s now?" % topic,
            "Why it is growing",
            "What the sources say about what comes next",
        ]

    def draft(self, topic, facts, revision_notes=None):
        openers = [
            "Something is buzzing in this city, and it is not just the traffic.",
            "Quietly, block by block, %s has gone mainstream." % topic,
        ]
        opener = openers[self.rng.randrange(len(openers))]
        claims = list(facts)
        if revision_notes is None:
            # First draft: the model confidently invents one extra "fact".
            claims.insert(2, HALLUCINATION)
        else:
            claims = [c for c in claims if c not in revision_notes["remove"]]
        body = " ".join(claims)
        return "%s %s" % (opener, body)

    def polish(self, text):
        text = re.sub(r"\s+", " ", text).strip()
        text = text.replace(" percent", "%")
        if not text.endswith("."):
            text += "."
        return text

# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------

class Transcript:
    def __init__(self):
        self.lines = []

    def log(self, agent, msg):
        line = "[%s] %s" % (agent.ljust(15), msg)
        self.lines.append(line)
        print(line)

class Planner:
    name = "PLANNER"

    def __init__(self, llm, t):
        self.llm, self.t = llm, t

    def run(self, topic):
        outline = self.llm.plan(topic)
        self.t.log(self.name, "Outline: " + " | ".join(outline))
        return outline

class Researcher:
    name = "RESEARCHER"

    def __init__(self, corpus, t):
        self.corpus, self.t = corpus, t

    def run(self, topic):
        words = set(topic.lower().split())
        hits = []
        for doc in self.corpus:
            score = len(words & set(doc["topic"].lower().split()))
            if score > 0:
                hits.append((score, doc))
        hits.sort(key=lambda p: (-p[0], p[1]["id"]))
        docs = [d for _, d in hits]
        self.t.log(self.name, "Query '%s' -> %d source(s): %s"
                   % (topic, len(docs), ", ".join(d["id"] for d in docs)))
        return docs

class Writer:
    name = "WRITER"

    def __init__(self, llm, t):
        self.llm, self.t = llm, t

    def run(self, topic, sources, revision_notes=None):
        facts = [f for d in sources for f in d["facts"]]
        draft = self.llm.draft(topic, facts, revision_notes)
        label = "Revised draft" if revision_notes else "First draft"
        self.t.log(self.name, "%s (%d chars, %d claims)."
                   % (label, len(draft), len(split_claims(draft))))
        return draft

class FactChecker:
    name = "FACT-CHECKER"

    def __init__(self, t):
        self.t = t

    def run(self, draft, sources):
        known = {norm(f) for d in sources for f in d["facts"]}
        bad = []
        for claim in split_claims(draft):
            if looks_factual(claim) and norm(claim) not in known:
                bad.append(claim)
        for c in bad:
            self.t.log(self.name, "REJECT unverified claim: \"%s\"" % c)
        if not bad:
            self.t.log(self.name, "All factual claims trace to a source. Approved.")
        return bad

class CopyEditor:
    name = "COPY-EDITOR"

    def __init__(self, llm, t):
        self.llm, self.t = llm, t

    def run(self, draft):
        polished = self.llm.polish(draft)
        self.t.log(self.name, "Polished style, normalized whitespace and units.")
        return polished

# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def split_claims(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]

def norm(s):
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()

def looks_factual(claim):
    """Heuristic: sentences with numbers or absolute assertions are 'checkable'."""
    return bool(re.search(r"\d", claim)) or claim.startswith("Bees can")

# ---------------------------------------------------------------------------
# Editor-in-chief: the orchestrator
# ---------------------------------------------------------------------------

class EditorInChief:
    name = "EDITOR"

    def __init__(self, seed=7):
        self.t = Transcript()
        llm = MockLLM(seed)
        self.planner = Planner(llm, self.t)
        self.researcher = Researcher(CORPUS, self.t)
        self.writer = Writer(llm, self.t)
        self.checker = FactChecker(self.t)
        self.copyed = CopyEditor(llm, self.t)

    def assign(self, topic):
        self.t.log(self.name, "Assignment received: write a story about '%s'." % topic)
        self.t.log(self.name, "Decomposing: plan -> research -> draft -> check -> polish.")
        outline = self.planner.run(topic)
        sources = self.researcher.run(topic)
        if not sources:
            self.t.log(self.name, "No sources found. Spiking the story.")
            return None
        draft = self.writer.run(topic, sources)

        # Fact-check loop (max 2 rounds; a real desk would also cap this)
        for round_no in range(1, 3):
            bad = self.checker.run(draft, sources)
            if not bad:
                break
            self.t.log(self.name, "Bouncing draft back to writer (round %d)." % round_no)
            draft = self.writer.run(topic, sources, revision_notes={"remove": bad})

        final = self.copyed.run(draft)
        self.t.log(self.name, "Story approved for publication. Outline honored: %d beats."
                   % len(outline))
        return final, sources

# ---------------------------------------------------------------------------
# Presentation
# ---------------------------------------------------------------------------

def print_story(final, sources, topic):
    width = 72
    print()
    print("=" * width)
    print(("FINAL STORY: " + topic.upper()).center(width))
    print("=" * width)
    for line in textwrap.wrap(final, width=width - 2):
        print("  " + line)
    print("-" * width)
    print("  SOURCES")
    for d in sources:
        print("   [%s] %s -- \"%s\"" % (d["id"], d["outlet"], d["title"]))
    print("=" * width)

def main(argv=None):
    ap = argparse.ArgumentParser(description="Five-agent newsroom pipeline.")
    ap.add_argument("--demo", action="store_true", help="run the canned demo and exit")
    ap.add_argument("--topic", default="urban beekeeping")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args(argv)

    topic = "urban beekeeping" if args.demo else args.topic
    print("multi-agent-newsroom :: transcript")
    print("-" * 50)
    desk = EditorInChief(seed=args.seed)
    result = desk.assign(topic)
    if result is None:
        print("\nNo story today. Try --topic \"urban beekeeping\" or \"public transit\".")
        return 1
    final, sources = result
    print_story(final, sources, topic)
    return 0

if __name__ == "__main__":
    sys.exit(main())
