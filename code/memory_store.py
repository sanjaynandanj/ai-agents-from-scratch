"""Three-layer agent memory: buffer, rolling summary, long-term store.

Key insight: context windows are finite, so memory is a hierarchy. Recent
turns stay verbatim in a buffer; evicted turns get compressed into a rolling
summary; and only facts a write policy deems memorable are promoted to the
long-term store, recalled later by similarity rather than recency.
"""

import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import math
import re
from collections import Counter

from mock_llm import MockLLM


def _tokens(text):
    return re.findall(r"[a-z0-9]+", text.lower())


def cosine_overlap(a: str, b: str) -> float:
    """Cosine similarity over keyword counts (a tiny stand-in for embeddings)."""
    va, vb = Counter(_tokens(a)), Counter(_tokens(b))
    dot = sum(va[t] * vb[t] for t in va)
    na = math.sqrt(sum(c * c for c in va.values()))
    nb = math.sqrt(sum(c * c for c in vb.values()))
    return dot / (na * nb) if na and nb else 0.0


class ConversationBuffer:
    """Verbatim recent turns; evicts oldest when the window overflows."""

    def __init__(self, window: int):
        self.window = window
        self.turns = []

    def add(self, role, content):
        self.turns.append({"role": role, "content": content})
        evicted = []
        while len(self.turns) > self.window:
            evicted.append(self.turns.pop(0))
        return evicted


class RollingSummary:
    """Compresses evicted turns with the (mock) LLM into one running summary."""

    def __init__(self, llm: MockLLM):
        self.llm = llm
        self.text = "(empty)"

    def absorb(self, evicted):
        if not evicted:
            return
        prompt = ("Summarize, keeping key facts. Current summary: %s. New turns: %s"
                  % (self.text, [t["content"] for t in evicted]))
        self.text = self.llm.complete([{"role": "user", "content": prompt}])["content"]


class LongTermStore:
    """Durable facts with similarity recall and a selective write policy."""

    def __init__(self, policy_llm: MockLLM):
        self.policy_llm = policy_llm
        self.facts = []

    def maybe_save(self, utterance: str):
        # Write policy: ask the model "is this worth remembering forever?"
        verdict = self.policy_llm.complete(
            [{"role": "user", "content": "Memorable? " + utterance}])["content"]
        if verdict.startswith("SAVE"):
            self.facts.append(utterance)
            return True
        return False

    def recall(self, query: str, k: int = 2, min_sim: float = 0.1):
        scored = sorted(((cosine_overlap(query, f), f) for f in self.facts),
                        reverse=True)
        return [(round(s, 3), f) for s, f in scored[:k] if s >= min_sim]


if __name__ == "__main__":
    summarizer = MockLLM(rules=[
        ("gluten", "User runs MarginX, prefers Python, and is gluten intolerant."),
        ("marginx", "User runs a startup called MarginX and prefers Python."),
        ("weather", "User opened with small talk about the weather."),
    ])
    # Policy: durable personal/business facts get saved; small talk does not.
    policy = MockLLM(rules=[
        ("my company", "SAVE"), ("i prefer", "SAVE"), ("intolerant", "SAVE"),
        ("weather", "SKIP"), ("", "SKIP"),
    ])

    print("=== Three-layer memory demo ===\n-- Session 1 --")
    buffer = ConversationBuffer(window=4)
    summary = RollingSummary(summarizer)
    longterm = LongTermStore(policy)

    session1 = [
        "Nice weather today, isn't it?",
        "My company is called MarginX, we build audit tools.",
        "I prefer Python for all backend services.",
        "By the way, I am gluten intolerant.",
        "Anyway, what time is it in Tokyo?",
        "And can you recommend a good sci-fi book?",
    ]
    for utterance in session1:
        saved = longterm.maybe_save(utterance)
        evicted = buffer.add("user", utterance)
        summary.absorb(evicted)
        flags = ("[-> long-term]" if saved else "") + \
                (" [evicted %d -> summary]" % len(evicted) if evicted else "")
        print("user: %-55s %s" % (utterance, flags))

    print("\nBuffer (last %d turns): %s" % (buffer.window,
          [t["content"][:30] for t in buffer.turns]))
    print("Rolling summary:        %s" % summary.text)
    print("Long-term facts:        %s" % longterm.facts)

    print("\n-- Session 2 (fresh buffer, same long-term store) --")
    buffer2 = ConversationBuffer(window=4)
    query = "Which language do I prefer for my company's new backend service?"
    print("user: %s" % query)
    recalled = longterm.recall(query, k=2)
    print("recall(query) -> %s" % recalled)
    context = "; ".join(f for _, f in recalled)
    answerer = MockLLM(rules=[("prefer python", "Given that you prefer Python at "
                               "MarginX, build the new service in Python.")])
    reply = answerer.complete([{"role": "system", "content": "Known: " + context},
                               {"role": "user", "content": query}])
    print("assistant: %s" % reply["content"])
    print("\nSession 2 never saw session 1's transcript -- only the facts the")
    print("write policy chose to keep. That selectivity is what makes long-term")
    print("memory useful instead of noisy.")
