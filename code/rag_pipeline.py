"""RAG from scratch: chunk -> TF-IDF index -> retrieve -> cite -> verify.

Key insight: retrieval turns an open-book exam into a closed one. The model
only sees the top-k chunks, must cite them as [1][2], and a faithfulness
check rejects answers whose citations point at nothing -- catching the most
common RAG hallucination mechanically, without another model call.
"""

import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import math
import re
from collections import Counter

from mock_llm import MockLLM

DOCS = {
    "solar.md": "Solar panels convert sunlight into electricity using photovoltaic "
                "cells.\n\nA typical home installation pays for itself in 7 to 10 "
                "years depending on local sunshine.",
    "wind.md": "Wind turbines generate power from moving air.\n\nOffshore wind "
               "farms produce roughly 50 percent more energy than onshore ones.",
    "hydro.md": "Hydroelectric dams store energy as elevated water.\n\nPumped "
                "storage is the largest form of grid energy storage today.",
    "battery.md": "Lithium-ion batteries dominate grid storage projects.\n\nBattery "
                  "costs fell nearly 90 percent between 2010 and 2023.",
    "nuclear.md": "Nuclear plants provide steady baseload power with no carbon "
                  "emissions during operation.",
    "geothermal.md": "Geothermal plants tap heat from underground reservoirs.\n\n"
                     "Iceland heats most of its buildings geothermally.",
    "coal.md": "Coal remains the single largest source of electricity-sector "
               "carbon emissions worldwide.",
    "grid.md": "Modern grids balance supply and demand every few seconds.\n\n"
               "Storage smooths the gap between renewable supply and demand.",
}


def chunk(text: str, overlap_sentences: int = 1):
    """Split on paragraphs; prepend the tail of the previous paragraph so
    boundary-straddling facts survive chunking."""
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks = []
    for i, para in enumerate(paras):
        if i > 0 and overlap_sentences:
            tail = re.split(r"(?<=[.!?])\s+", paras[i - 1])[-overlap_sentences:]
            para = " ".join(tail) + " " + para
        chunks.append(para)
    return chunks


def _tok(text):
    return re.findall(r"[a-z0-9]+", text.lower())


class TfIdfIndex:
    def __init__(self):
        self.chunks = []   # (source, text)
        self.vectors = []

    def add(self, source, text):
        self.chunks.append((source, text))

    def build(self):
        df = Counter()
        bags = [Counter(_tok(t)) for _, t in self.chunks]
        for bag in bags:
            df.update(bag.keys())
        n = len(bags)
        self.idf = {t: math.log(n / (1 + c)) + 1 for t, c in df.items()}
        self.vectors = [{t: c * self.idf[t] for t, c in bag.items()} for bag in bags]

    def search(self, query, k=3):
        q = Counter(_tok(query))
        qv = {t: c * self.idf.get(t, 1.0) for t, c in q.items()}
        def cos(v):
            dot = sum(qv.get(t, 0) * w for t, w in v.items())
            na = math.sqrt(sum(w * w for w in qv.values()))
            nb = math.sqrt(sum(w * w for w in v.values()))
            return dot / (na * nb) if na and nb else 0.0
        scored = sorted(((cos(v), i) for i, v in enumerate(self.vectors)), reverse=True)
        return [(round(s, 3),) + self.chunks[i] for s, i in scored[:k] if s > 0]


def check_faithfulness(answer: str, n_contexts: int):
    """Every [n] citation must point at a context that was actually provided."""
    cited = {int(m) for m in re.findall(r"\[(\d+)\]", answer)}
    bad = sorted(c for c in cited if not 1 <= c <= n_contexts)
    return (not cited or not bad,
            "cites %s; invalid: %s" % (sorted(cited) or "nothing", bad or "none"))


def answer(index, llm, query, k=3):
    hits = index.search(query, k)
    print("Query: %s" % query)
    for rank, (score, src, text) in enumerate(hits, 1):
        print("  [%d] (%.3f, %s) %s" % (rank, score, src, text[:70]))
    prompt = "Contexts:\n" + "\n".join(
        "[%d] %s" % (i, t) for i, (_, _, t) in enumerate(hits, 1)) + "\nQ: " + query
    resp = llm.complete([{"role": "user", "content": prompt}])["content"]
    ok, detail = check_faithfulness(resp, len(hits))
    print("  Answer: %s" % resp)
    print("  Faithfulness: %s (%s)\n" % ("PASS" if ok else "FAIL", detail))


if __name__ == "__main__":
    print("=== RAG pipeline demo ===\n")
    index = TfIdfIndex()
    for name, text in DOCS.items():
        for c in chunk(text):
            index.add(name, c)
    index.build()
    print("Indexed %d chunks from %d docs.\n" % (len(index.chunks), len(DOCS)))

    llm = MockLLM(rules=[
        ("battery", "Grid storage is dominated by lithium-ion batteries [1], whose "
                    "costs fell nearly 90 percent since 2010 [2]."),
        ("offshore", "Offshore wind farms produce about 50 percent more energy "
                     "than onshore ones [1]."),
        ("unicorn", "Unicorn power supplies 40 percent of the grid [7]."),  # bad cite
    ])
    answer(index, llm, "How have battery costs changed for grid storage?")
    answer(index, llm, "How much more energy do offshore wind farms produce?")
    print("-- A fabricated citation gets caught mechanically --")
    answer(index, llm, "Tell me about unicorn power.", k=2)
