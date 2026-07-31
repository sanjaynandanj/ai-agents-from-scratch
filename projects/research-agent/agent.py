#!/usr/bin/env python3
"""research-agent: plan -> search -> read -> note -> synthesize -> verify.

A miniature deep-research agent over a local hardcoded corpus. Search is
real (TF-IDF + cosine). Planning, note-taking, and synthesis are a
scripted mock LLM. Every claim in the final report carries a [n]
citation, and a verifier checks that mechanically before publishing.

Run:  python agent.py --demo
"""

import argparse
import math
import random
import re
import sys

# ---------------------------------------------------------------------------
# The corpus: ten mini-articles. Six are about coffee; four are distractors
# so the search step has something to actually discriminate against.
# ---------------------------------------------------------------------------

CORPUS = {
    "kaldi": ("The Goat Herder Legend",
        "Ethiopian tradition credits a goat herder named Kaldi with "
        "discovering coffee after his goats grew energetic from eating red "
        "berries. Historians treat the tale as legend, but botanical "
        "evidence does place the coffee plant's origin in the highland "
        "forests of Ethiopia."),
    "yemen": ("Coffee Crosses the Red Sea",
        "By the fifteenth century, Sufi monasteries in Yemen brewed coffee "
        "to stay awake during night devotions. The port of Mocha became "
        "the hub of the early coffee trade, giving its name to a drink "
        "centuries later."),
    "ottoman": ("Coffeehouses of Constantinople",
        "Coffeehouses opened in Constantinople in the 1550s and became "
        "centers of conversation, chess, and politics. Ottoman "
        "authorities periodically banned them, fearing sedition was "
        "being poured along with the coffee."),
    "europe": ("The Penny Universities",
        "Coffee reached Venice through trade, and London's coffeehouses "
        "of the 1650s were nicknamed penny universities: a penny bought "
        "a cup and access to debate. Lloyd's of London began as a "
        "coffeehouse for ship owners and insurers."),
    "caffeine": ("What Caffeine Does",
        "Caffeine works mainly by blocking adenosine receptors in the "
        "brain. Adenosine accumulates during waking hours and promotes "
        "sleepiness, so blocking its receptors postpones the feeling of "
        "fatigue rather than adding energy."),
    "halflife": ("The Five-Hour Half-Life",
        "Caffeine has a half-life of roughly five hours in healthy "
        "adults, which is why an afternoon espresso can disturb sleep at "
        "midnight. Genetics and pregnancy can stretch that half-life "
        "considerably."),
    "tea": ("A Brief History of Tea",
        "Tea moved from China along caravan routes centuries before "
        "coffee left Africa. The British East India Company built an "
        "empire of leaves, and tea remains the most consumed drink on "
        "earth after water."),
    "chocolate": ("Cacao and the Aztecs",
        "The Aztecs prized cacao beans enough to use them as currency. "
        "Chocolate arrived on European tables as a bitter drink for "
        "aristocrats long before anyone pressed it into bars."),
    "printing": ("Gutenberg's Press",
        "Johannes Gutenberg's movable-type press, built around 1440, cut "
        "the cost of books by orders of magnitude and accelerated the "
        "circulation of ideas across the continent."),
    "silk": ("The Silk Road",
        "The Silk Road was a web of overland routes linking Han China to "
        "the Mediterranean, moving silk, spices, paper, and ideas for "
        "well over a millennium."),
}

STOPWORDS = set("a an and are as at be by did do does for from had has how "
                "in is it its of on or s that the this to was what where "
                "why with".split())


# ---------------------------------------------------------------------------
# Real tool: TF-IDF search over the corpus.
# ---------------------------------------------------------------------------

def tokenize(text):
    return [t for t in re.findall(r"[a-z]+", text.lower()) if t not in STOPWORDS]


class TfIdfIndex:
    def __init__(self, corpus):
        doc_tokens = {d: tokenize(title + " " + body)
                      for d, (title, body) in corpus.items()}
        n_docs = len(corpus)
        df = {}
        for tokens in doc_tokens.values():
            for term in set(tokens):
                df[term] = df.get(term, 0) + 1
        self.idf = {t: math.log(n_docs / c) for t, c in df.items()}
        self.doc_vecs = {d: self._vectorize(toks)
                         for d, toks in doc_tokens.items()}

    def _vectorize(self, tokens):
        vec = {}
        for t in tokens:
            vec[t] = vec.get(t, 0.0) + self.idf.get(t, 0.0)
        norm = math.sqrt(sum(w * w for w in vec.values())) or 1.0
        return {t: w / norm for t, w in vec.items()}

    def search(self, query, k=2):
        qvec = self._vectorize(tokenize(query))
        scored = []
        for doc_id, dvec in self.doc_vecs.items():
            sim = sum(w * dvec.get(t, 0.0) for t, w in qvec.items())
            scored.append((round(sim, 4), doc_id))
        scored.sort(key=lambda s: (-s[0], s[1]))  # deterministic tie-break
        return [(doc_id, sim) for sim, doc_id in scored[:k] if sim > 0.05]


# ---------------------------------------------------------------------------
# The mock LLM: scripted planning, note-taking, and synthesis. A real
# model slots into these three methods without touching the loop.
# ---------------------------------------------------------------------------

class MockLLM:
    # Sub-questions are keyword-rich on purpose: real research agents are
    # prompted to emit *searchable* queries, not conversational ones.
    PLAN = [
        ("Origins",
         "Where did coffee originate: the Ethiopian goat herder legend "
         "and the Sufi monasteries of Yemen?"),
        ("The Spread West",
         "How did coffeehouses spread from Constantinople to London's "
         "penny universities?"),
        ("What Caffeine Does",
         "What does caffeine do to adenosine in the brain, and how long "
         "is its half-life?"),
    ]

    # note-taking script: doc_id -> the one claim worth extracting
    NOTES = {
        "kaldi": "Coffee's botanical origin is the highland forests of "
                 "Ethiopia, though the Kaldi goat-herder story is legend "
                 "rather than history",
        "yemen": "By the fifteenth century, Yemeni Sufi monasteries brewed "
                 "coffee for night devotions, with the port of Mocha "
                 "anchoring the early trade",
        "ottoman": "Coffeehouses opened in Constantinople in the 1550s and "
                   "were periodically banned as hotbeds of sedition",
        "europe": "London's 1650s coffeehouses were nicknamed penny "
                  "universities, and Lloyd's of London began as one",
        "caffeine": "Caffeine blocks adenosine receptors, postponing "
                    "sleepiness rather than adding energy",
        "halflife": "Caffeine's roughly five-hour half-life explains why "
                    "an afternoon espresso can disturb midnight sleep",
    }

    def plan(self, task):
        return list(self.PLAN)

    def take_note(self, question, doc_id, title, body):
        """Return the claim worth keeping, or None if the doc is off-topic."""
        return self.NOTES.get(doc_id)

    def synthesize(self, task, sections):
        """sections: list of (heading, [(claim, source_num), ...])."""
        lines = ["# Research Report: How Coffee Conquered the World", ""]
        for heading, claims in sections:
            lines.append("## " + heading)
            for claim, num in claims:
                lines.append("%s [%d]." % (claim, num))
            lines.append("")
        return lines


# ---------------------------------------------------------------------------
# The verifier: every claim line must end in a [n] citation, every n must
# map to a gathered source. No citation, no publication.
# ---------------------------------------------------------------------------

def verify_report(body_lines, sources):
    problems = []
    for ln in body_lines:
        text = ln.strip()
        if not text or text.startswith("#"):
            continue
        if not re.search(r"\[\d+\]\.?$", text):
            problems.append("uncited claim: %r" % text[:60])
        for n in (int(m) for m in re.findall(r"\[(\d+)\]", text)):
            if n not in sources:
                problems.append("citation [%d] has no source" % n)
    return problems


# ---------------------------------------------------------------------------
# The agent loop.
# ---------------------------------------------------------------------------

def banner(text, char="="):
    print()
    print(char * 66)
    print(text)
    print(char * 66)


def run_agent():
    task = ("Write a short, fully cited report on how coffee spread around "
            "the world and what caffeine does.")
    llm = MockLLM()
    index = TfIdfIndex(CORPUS)

    banner("RESEARCH AGENT")
    print("Task: %s" % task)

    banner("PHASE 1: PLAN", "-")
    plan = llm.plan(task)
    for i, (heading, q) in enumerate(plan, 1):
        print("  Q%d [%s]" % (i, heading))
        print("      %s" % q)

    banner("PHASE 2: SEARCH + READ + NOTE", "-")
    sources = {}    # source_num -> (doc_id, title)
    seen = {}       # doc_id -> source_num (cite each doc once)
    sections = []   # (heading, [(claim, num), ...])
    for i, (heading, q) in enumerate(plan, 1):
        print("\n[search] Q%d: %s" % (i, q))
        claims = []
        hits = index.search(q, k=2)
        if not hits:
            print("  no hits above threshold")
        for doc_id, score in hits:
            title, body = CORPUS[doc_id]
            print("  hit %-9s score=%.4f  %s" % (doc_id, score, title))
            claim = llm.take_note(q, doc_id, title, body)
            if claim is None:
                print("      -> judged off-topic, discarded")
                continue
            if doc_id not in seen:
                seen[doc_id] = len(sources) + 1
                sources[seen[doc_id]] = (doc_id, title)
            print("      -> note [%d]: %s..." % (seen[doc_id], claim[:46]))
            claims.append((claim, seen[doc_id]))
        sections.append((heading, claims))

    banner("PHASE 3: SYNTHESIZE", "-")
    body = llm.synthesize(task, sections)
    n_claims = sum(len(c) for _, c in sections)
    print("Drafted %d lines from %d notes across %d sources."
          % (len(body), n_claims, len(sources)))

    banner("PHASE 4: VERIFY CITATIONS", "-")
    problems = verify_report(body, sources)
    if problems:
        for p in problems:
            print("  FAIL: %s" % p)
        banner("REPORT REJECTED: %d citation problem(s)." % len(problems))
        return False
    print("  OK: every claim line ends in a citation that maps to a source.")

    banner("FINAL REPORT")
    for ln in body:
        print(ln)
    print("## Sources")
    for num in sorted(sources):
        doc_id, title = sources[num]
        print("[%d] %s  (corpus:%s)" % (num, title, doc_id))
    return True


def main():
    parser = argparse.ArgumentParser(description="A tiny cited research agent.")
    parser.add_argument("--demo", action="store_true", help="run the scripted demo")
    args = parser.parse_args()
    if not args.demo:
        parser.print_help()
        return 0
    random.seed(42)  # determinism is a habit, not an accident
    ok = run_agent()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
