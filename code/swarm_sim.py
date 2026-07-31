"""Swarm coordination: blackboard + contract-net auctions + stigmergy.

Key insight: no agent is in charge. Tasks are posted to a shared blackboard,
agents bid what the work would cost them, and the cheapest bid wins. Because
winning a task makes an agent better (cheaper) at that skill, specialization
*emerges* from the auction mechanics -- nobody assigns roles.
"""

import random


class WorkerAgent:
    def __init__(self, name, skills):
        self.name = name
        self.skills = dict(skills)          # skill -> base cost
        self.experience = {s: 0 for s in skills}  # stigmergy counters
        self.completed = 0

    def bid(self, skill):
        """Cost shrinks 10% per completed task of this skill (learning curve)."""
        if skill not in self.skills:
            return None
        return round(self.skills[skill] * (0.9 ** self.experience[skill]), 2)

    def win(self, skill):
        self.experience[skill] += 1
        self.completed += 1


class Blackboard:
    """Shared task board: anyone can post, anyone can see, auctions decide."""

    def __init__(self, agents):
        self.agents = agents
        self.log = []

    def auction(self, task_id, skill):
        bids = {a.name: a.bid(skill) for a in self.agents}
        valid = {n: b for n, b in bids.items() if b is not None}
        print("  task %-14s (skill=%-8s) bids: %s"
              % (task_id, skill, {n: bids[n] for n in sorted(bids)}))
        if not valid:
            print("    -> no capable agent; task stays on the board")
            return None
        # Contract-net award: lowest bid wins; name order breaks ties (determinism).
        winner_name = min(sorted(valid), key=lambda n: valid[n])
        winner = next(a for a in self.agents if a.name == winner_name)
        winner.win(skill)
        self.log.append((task_id, skill, winner_name, valid[winner_name]))
        print("    -> awarded to %s at cost %.2f" % (winner_name, valid[winner_name]))
        return winner_name


if __name__ == "__main__":
    agents = [
        WorkerAgent("ant-1", {"scrape": 5.0, "summarize": 6.0}),
        WorkerAgent("ant-2", {"summarize": 5.5, "translate": 7.0}),
        WorkerAgent("ant-3", {"scrape": 5.2, "translate": 6.5, "summarize": 7.5}),
    ]
    board = Blackboard(agents)
    rng = random.Random(42)  # seeded: identical run every time

    skills = ["scrape", "summarize", "translate"]
    print("=== Swarm demo: blackboard + contract-net auction ===\n")
    task_no = 0
    for round_no in range(1, 4):
        print("--- Round %d ---" % round_no)
        # Each round posts 4 tasks with a seeded random mix of skills.
        for _ in range(4):
            task_no += 1
            board.auction("T%02d" % task_no, rng.choice(skills))
        print()

    print("=== Emergent specialization (stigmergy counters) ===")
    print("%-8s %-28s completed" % ("agent", "experience by skill"))
    for a in agents:
        exp = {s: c for s, c in a.experience.items() if c}
        print("%-8s %-28s %d" % (a.name, exp, a.completed))

    print("\nAllocation log:")
    for task_id, skill, winner, cost in board.log:
        print("  %s %-9s -> %-6s (%.2f)" % (task_id, skill, winner, cost))

    print("\nEarly wins lower an agent's future bids for that skill, so it keeps")
    print("winning that skill: positive feedback -> division of labour, with no")
    print("manager and no global plan. That is stigmergy, straight from ants.")
