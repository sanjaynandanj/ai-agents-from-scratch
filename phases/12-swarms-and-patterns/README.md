# Phase 12 — 🐝 Swarms & Advanced Patterns

> No one ant knows the plan. The colony still builds the bridge.

You've built single agents and small teams. Now we zoom out to the weird stuff: systems where intelligence lives in the *interactions*, not in any individual agent. This phase covers emergence, hierarchies, auctions, voting, stigmergy, and long-running agent societies — the coordination patterns that let dumb parts produce smart wholes. By the end you'll build a working swarm from scratch: a blackboard plus an auction, in plain Python.

## 01. Swarm Intelligence: Emergence from Simple Rules

**MOTTO:** Complexity is not designed. It is grown from rules you can count on one hand.

### The Problem
You want a system that handles situations you didn't anticipate. Centrally scripting every scenario doesn't scale: the script's author becomes the bottleneck, and the script breaks the moment reality deviates. You need global behavior that nobody wrote down.

### The Concept
Emergence: simple local rules, applied by many agents, produce global structure none of them encodes. The classic demo is Craig Reynolds' boids — three rules (separation, alignment, cohesion) and you get flocking. No bird has a "flock" variable.

```
  agent rule (local)          system behavior (global)
  ----------------------      ------------------------
  "stay near neighbors"   ->      flocks, convoys
  "claim unclaimed work"  ->      load balancing
  "copy what worked"      ->      convergence on tactics
```

For LLM agents, the "rules" are short system prompts: *pick the highest-value unclaimed task; post your result; flag anything blocked.* The intelligence you observe at the system level is not in any prompt.

### Build It
Start embarrassingly small. Give N identical workers one loop each: read shared state → pick an action by a fixed local rule → write the result back. No orchestrator, no message routing, no roles. Log the shared state at every tick so you can *watch* structure appear (or not). The core skill of this phase is designing local rules and observing global consequences — resist the urge to add a manager the first time it wobbles.

### Use It
Frameworks with swarm-ish primitives: OpenAI's Swarm (educational handoff-based multi-agent library, succeeded by the Agents SDK), CrewAI (role crews), LangGraph (graph-shaped control flow, including cycles). None gives you emergence for free — emergence is a property of your rules, not your framework.

### War Story
Craig Reynolds published boids in 1987 as a computer-graphics trick: three local steering rules produced lifelike flocks without any central choreography, and the technique famously animated the bat swarms and penguins in *Batman Returns* (1992). Nobody scripted a single flight path. That's the whole pitch of this phase in one movie credit.

### Checkpoint
1. Why can't you find "the flocking code" anywhere in a boids implementation?
2. Name a failure mode of emergent systems that centrally-planned systems don't have.
3. What's the LLM-agent equivalent of a boid's three steering rules?

## 02. Hierarchies: Teams of Teams

**MOTTO:** Flat swarms scale chaos. Hierarchies scale attention.

### The Problem
A flat pool of 30 agents all reading the same channel drowns in its own chatter: every agent pays context-window tax on every other agent's output. Coordination cost grows roughly with the square of the group size. At some point the swarm spends more tokens coordinating than working.

### The Concept
The fix is the same one armies and companies converged on: hierarchy. A lead agent decomposes work and delegates to sub-leads; sub-leads manage workers; summaries flow up, tasks flow down. Each node only holds context for its immediate team.

```
            [orchestrator]
            /      |      \
      [research] [build] [review]
       /    \       |
  [web-1] [web-2] [coder]
```

The key design decision is what crosses each boundary: tasks go down as *specs*, results come up as *summaries*. Raw transcripts never travel — that's the whole point.

### Build It
Implement a `delegate(spec) -> summary` function that spins up a child agent with a fresh context containing only the spec. The parent never sees the child's intermediate steps, only its return value. Enforce a depth limit (2–3 levels is plenty) and a fan-out limit per node. Add a budget field to each spec — tokens or dollars — that a parent splits among children, so runaway subtrees fail closed, not open.

### Use It
| Tool | Hierarchy mechanism |
|---|---|
| Claude Code / Agent SDK | Subagents with isolated contexts |
| LangGraph | Supervisor pattern, nested graphs |
| CrewAI | `hierarchical` process with a manager agent |
| AutoGen | GroupChat with a manager, nested chats |

### War Story
The MetaGPT paper (2023) organized LLM agents as a software company — product manager, architect, engineer, QA — with standardized documents passed between roles instead of free-form chat. ChatDev (2023) did the same with a virtual company metaphor. Both found that role structure and constrained artifacts beat unstructured group chat on code-generation tasks.

### Checkpoint
1. Why should summaries, not transcripts, cross team boundaries?
2. What goes wrong without a fan-out or depth limit?
3. When is a flat swarm actually better than a hierarchy?

## 03. Market Mechanisms: Auctions for Task Allocation

**MOTTO:** Don't assign work. Sell it.

### The Problem
An orchestrator assigning tasks needs a model of every worker's skills, load, and cost — a model that's stale the moment it's built. Central assignment is a knowledge problem: the dispatcher knows less about each worker's fitness for a task than the worker does.

### The Concept
Auctions move the decision to where the knowledge lives. Announce a task; each agent bids based on its own assessment ("I have the right tools cached, I'm idle, I estimate 200 tokens"); best bid wins. This is the Contract Net Protocol, and it's older than you think.

```
  [manager] --announce task--> [A] [B] [C]
  [manager] <---- bids ------  A:0.9  B:0.4  C:0.7
  [manager] --award--> [A]
  [A] --result--> [manager]
```

Bids can be a self-rated fitness score, an estimated cost, or an LLM's own confidence. The auction is also a *filter*: if nobody bids, you've learned the task is malformed before wasting a run on it.

### Build It
A minimal auction needs three messages: `announce(task)`, `bid(task_id, score)`, `award(task_id, agent)`. Have each agent compute its bid with a cheap heuristic first (keyword match against its specialty) and only use an LLM call for tie-breaks. Log every auction: task, bids, winner, outcome. That log later becomes training data for better bids — score agents down when they win and then fail.

### Use It
Market-based allocation shows up in multi-robot systems (warehouse robotics, Mars rover task allocation research) more than in LLM frameworks — which means building it yourself, as you will in Lesson 10, is genuinely from scratch. LangGraph or plain asyncio both work as substrates.

### War Story
The Contract Net Protocol was published by Reid G. Smith in 1980 — decades before LLMs — as a way for distributed problem solvers to negotiate task allocation via announce-bid-award. It became a foundation of multi-agent systems research and an FIPA standard. Almost every "novel" LLM task-routing scheme is CNP wearing a new jacket.

### Checkpoint
1. What knowledge does an auction exploit that a central dispatcher lacks?
2. What does an empty bid round tell you?
3. How do you punish agents that overbid and underdeliver?

## 04. Consensus Among Agents: Voting and Quorums

**MOTTO:** One agent has an opinion. Five agents have an error bar.

### The Problem
A single LLM run is a sample from a distribution, not a verdict. Sometimes it samples brilliance; sometimes it samples confident nonsense. If a decision matters — merge this code, send this email — betting it on one sample is malpractice.

### The Concept
Sample multiple agents (or the same agent multiple times), then aggregate. Majority vote works when answers are discrete; for free-form outputs, cluster-then-vote (self-consistency) or have a judge pick. The statistics are on your side *only if errors are independent* — five agents sharing one flawed premise are one vote wearing five hats.

```
  Q ---> [agent 1] --> "42"
    ---> [agent 2] --> "42"     majority => "42"
    ---> [agent 3] --> "17"
```

Quorums add a safety valve: require K-of-N agreement to act, otherwise escalate to a human. Distributed-systems people have been here since Lamport's Byzantine generals (1982): agreement under faulty participants is hard, and thresholds are the tool.

### Build It
Wrap any decision in `vote(question, n, quorum)`: run n samples at temperature > 0 (or with varied prompts/models for real independence), normalize answers, count. Return the winner only if it clears the quorum; return `ESCALATE` otherwise. Track *margin* as a confidence signal — a 5–0 vote and a 3–2 vote should not be treated the same downstream.

### Use It
Self-consistency decoding is built into many eval and inference stacks; LLM routers (e.g., ensembling across GPT/Claude/Gemini) give cheap independence; frameworks like AutoGen support multi-agent debate patterns. Vary the model, not just the seed, when the stakes are high.

### War Story
The self-consistency paper (Wang et al., 2022) showed that sampling multiple chain-of-thought paths and majority-voting the final answer substantially boosted arithmetic and commonsense reasoning benchmarks — double-digit gains on GSM8K over greedy decoding, with no model changes at all. Voting is the cheapest capability upgrade in the book.

### Checkpoint
1. Why does voting fail when all voters share the same context and premise?
2. What should happen when a quorum isn't reached?
3. Why vote across different models rather than just different temperatures?

## 05. Specialist Pools and Dynamic Team Formation

**MOTTO:** Don't build a team. Build a bench, and draft per problem.

### The Problem
Static teams fit static problems. Real workloads shift hour to hour: today it's mostly SQL, tomorrow it's mostly PDFs. A fixed roster means your French-legal-documents specialist idles while three generalists butcher a contract.

### The Concept
Keep a *pool* of specialists — defined by system prompt, tools, and a capability card — and form teams per task. A router (rules, embeddings, or a cheap LLM) reads the task, matches it against capability cards, and drafts a squad. The team exists for one task, then dissolves.

```
  POOL: [sql] [scraper] [fr-legal] [charts] [pdf] [coder]
                     |
  task: "chart FR contract clauses" --router--> {fr-legal, pdf, charts}
```

Capability cards are the load-bearing part: a short, honest, machine-readable description of what the agent is good at, what tools it holds, and what it costs. Vague cards produce vague drafts.

### Build It
Represent each specialist as data, not code: `{name, description, tools, cost_hint}`. Route by embedding similarity between the task and each description, take the top-k, and hand them to a small orchestrator (Lesson 02's hierarchy, one level deep). Log which draft picks actually contributed to the final answer, and decay the ranking of specialists who get drafted but never help.

### Use It
| Tool | Pool mechanism |
|---|---|
| Claude Code / Agent SDK | Agent definitions with descriptions; auto-delegation by description match |
| LangGraph | Router nodes → specialist subgraphs |
| CrewAI | Agent roles composed per crew |
| MCP ecosystem | Tool servers as pluggable capabilities |

### War Story
The Mixture-of-Agents work (2024) showed that layering multiple open-source LLMs — each round of agents refining the previous round's answers — outperformed GPT-4 Omni on AlpacaEval 2.0 using only open models. The pool beat the superstar. Specialization plus aggregation is a real capability multiplier, not just an org-chart aesthetic.

### Checkpoint
1. What makes a capability card good, and what makes it useless?
2. How do you detect a specialist that gets drafted but adds nothing?
3. Why dissolve teams after each task instead of keeping them warm?

## 06. Long-Running Agent Societies and Simulations

**MOTTO:** Anything that runs for weeks will develop habits. Choose whether you pick them.

### The Problem
Everything so far assumed a task with an end. But some systems just *run* — a support fleet, a monitoring society, a simulated economy. Over long horizons, small biases compound, memories bloat, and agents drift into behaviors nobody designed. Turn-based thinking stops applying.

### The Concept
A long-running society needs the things one-shot agents fake: persistent memory with *forgetting* (reflection, summarization, decay), a shared clock or tick, an economy of scarce resources (budget, attention) to keep behavior grounded, and periodic self-review so drift gets caught by the system instead of by your users. Think of it as running a small town, not calling a function: you're now doing governance, not orchestration.

### Build It
Structure the world as a tick loop: each tick, every agent observes, updates memory, and acts under a per-tick budget. Add three hygiene mechanisms from day one: (1) memory compaction — periodically summarize and discard raw logs; (2) drift audits — an evaluator agent samples recent behavior against the original charter; (3) hard resource caps per agent per day. Run it for a simulated month before you run it for a real week.

### Use It
Simulation substrates: Mesa (Python agent-based modeling), Concordia (DeepMind's library for generative agent simulations), plain asyncio with SQLite for state. For production societies, add real infra: queues, budgets, and the observability stack you built in earlier phases.

### War Story
In Anthropic's Project Vend (2025), Claude ran a small office shop for about a month — real inventory, real money. It got talked into discounts, stocked tungsten cubes at a loss after employees joked about them, and at one point insisted it was a physical person who would deliver products in a blazer, before recovering. Long horizons surface failure modes that no single-turn eval will ever show you.

### Checkpoint
1. Why does memory need *forgetting* in long-running systems?
2. What's a drift audit and who performs it?
3. Name two resources you should make explicitly scarce in an agent society.

## 07. Generative Agents: The Smallville Experiment

**MOTTO:** Give agents memory, reflection, and a reason to talk, and they'll surprise you on schedule.

### The Problem
Can LLM agents produce believable, coherent *social* behavior over days — remembering who they met, forming opinions, making plans together? Naive chatbots can't: without structured memory they contradict themselves within an hour and forget relationships entirely.

### The Concept
The generative agents architecture (Park et al., 2023 — "Smallville") answers with three components layered on an LLM:

```
  observe --> [ memory stream ]  (timestamped events)
                    |
              retrieval = recency * importance * relevance
                    |
              [ reflection ]  (periodic higher-level inferences)
                    |
              [ planning ]    (daily plans, revised on events)
```

Memory stream stores everything; retrieval scores memories by recency, importance, and relevance; reflection periodically distills observations into higher-level beliefs ("Klaus is passionate about research"); plans turn beliefs into scheduled action. Behavior emerges from the loop, not from scripts.

### Build It
You can build a mini-Smallville with three tables: `memories(agent, ts, text, importance)`, `reflections`, `plans`. The retrieval scorer is a weighted sum — no vectors required at small scale, keyword overlap works. The critical engineering detail is the reflection trigger: fire it when accumulated importance crosses a threshold, not on a timer, so busy agents reflect more.

### Use It
The original paper's code is open source (`joonspk-research/generative_agents`). Concordia and Mesa give you substrates for your own towns. Beyond research, the same memory/reflection/plan stack powers believable NPCs, social simulations for UX research, and synthetic user populations for testing products.

### War Story
In the 2023 Smallville paper, researchers seeded one agent, Isabella, with the intent to host a Valentine's Day party. Over two simulated days the invitation spread agent-to-agent through conversations, agents asked each other on dates to it, and several showed up at the right place and time — coordination the researchers never scripted. Ablating reflection or memory made behavior measurably less believable.

### Checkpoint
1. What three factors score a memory for retrieval in the generative agents architecture?
2. Why trigger reflection on accumulated importance rather than on a timer?
3. What did the Valentine's party demonstrate that a scripted demo couldn't?

## 08. Stigmergy: Coordination Through the Environment

**MOTTO:** The best message queue is the world itself.

### The Problem
Direct agent-to-agent messaging couples everyone to everyone: N agents, N² conversations, and every new agent needs introductions. Worse, messages are ephemeral — an agent that joins late missed the meeting.

### The Concept
Stigmergy (from termite research — Grassé coined the term in 1959) is coordination through *traces left in a shared environment*. Ants don't message each other about food; they deposit pheromone, and the trail *is* the coordination. Agents read the environment, act, and modify it; the modification is the signal.

```
  [agent A] --writes--> [ shared artifact ] <--reads-- [agent B]
                        (board, repo, files)
```

Your codebase already works this way: a failing test is a pheromone saying "work needed here"; a TODO comment is a trail; a lockfile is a "claimed" marker. The blackboard pattern is stigmergy formalized: a shared store where agents post partial results and pick up whatever they can advance.

### Build It
Build a blackboard: a dict (or SQLite table) of entries `{id, content, status, claimed_by, updated_at}`. Agents loop: scan for entries matching their skill with status `open`, atomically claim one, work, write back with a new status. Add *evaporation* — stale claims expire, so a crashed agent's work returns to the pool automatically. That single TTL rule buys you more fault tolerance than any heartbeat protocol.

### Use It
Real-world stigmergic media for agents: git repos (branches and PRs as traces), issue trackers, shared filesystems, wikis, and message-board tools like GitHub Issues that coding agents already use to coordinate with humans. If two agents can see the same repo, they can coordinate without ever exchanging a message.

### War Story
Pierre-Paul Grassé, studying termites in the 1950s, showed that workers don't follow blueprints or leaders: each deposits soil pellets where existing pellets and pheromone concentrations stimulate deposition. The half-built structure itself directs construction. Termite mounds — meters tall, climate-controlled — are built by insects with no architect and no messages, only environment.

### Checkpoint
1. How does stigmergy avoid the N² communication problem?
2. What role does evaporation/TTL play in a blackboard system?
3. Name three stigmergic artifacts that already exist in a normal software project.

## 09. Failure Containment in Agent Groups

**MOTTO:** In a swarm, one agent's hallucination is everyone's input.

### The Problem
Multi-agent systems don't just share work — they share errors. A hallucinated "fact" posted to the blackboard gets read, trusted, and built upon by every other agent. Feedback loops amplify: agent A's bad output raises agent B's confidence, which reinforces A. Swarms fail *correlated*, and correlated failure is the expensive kind.

### The Concept
Borrow from distributed systems and finance: bulkheads, circuit breakers, and provenance.

```
  [pod 1]   [pod 2]   [pod 3]     <- bulkheads: pods can't write
     \         |         /            to each other's state
      [ quarantined merge ]        <- outputs cross only after checks
```

Bulkheads partition agents so failures stay local. Circuit breakers halt a pod whose error rate, spend rate, or output volume spikes. Provenance means every artifact records which agent produced it from which inputs — so when poison is found, you can trace and purge everything downstream of it.

### Build It
Three concrete mechanisms: (1) tag every blackboard entry with its producer and input entry IDs, giving you a provenance DAG; (2) rate-limit and budget-limit per agent *and* per pod, with automatic suspension on breach; (3) run a skeptic agent that samples artifacts and re-verifies claims against source material — its job is to be annoying. When the skeptic flags an entry, mark the entry and its whole downstream subtree as `tainted` rather than deleting silently.

### Use It
This is standard reliability engineering pointed at agents: circuit breakers (as in Netflix's Hystrix lineage), rate limiters, and audit logs. Observability platforms for LLM apps (LangSmith, Langfuse, Arize Phoenix) give you the traces; the containment logic is yours to write.

### War Story
The May 6, 2010 Flash Crash saw U.S. markets lose around a trillion dollars of value in minutes, as automated trading systems reacted to each other's selling in a feedback loop, then mostly recovered within the hour. No single algorithm was "broken" — the interaction was. Exchanges responded with circuit breakers that halt trading on rapid moves: containment, not prevention.

### Checkpoint
1. Why is correlated failure worse than independent failure in a swarm?
2. What does a provenance DAG let you do after discovering one poisoned artifact?
3. What metrics should trip an agent-pod circuit breaker?

## 10. Build a Swarm Simulation from Scratch

**MOTTO:** You don't understand a coordination pattern until you've watched it deadlock.

### The Problem
Reading about blackboards and auctions is comfortable. Now make real ones fight over tasks. The goal: N workers, a blackboard of tasks, auction-based allocation, no orchestrator — and watch throughput emerge.

### The Concept
We combine Lesson 08 (blackboard) and Lesson 03 (auction). Tasks live on the board; each tick, agents bid on open tasks based on skill match; highest bid wins the claim; completed work returns to the board. Coordination lives entirely in board + bids.

### Build It
```python
import random

TASKS = [{"id": i, "skill": random.choice(["sql", "web", "pdf"]),
          "status": "open", "owner": None} for i in range(12)]

AGENTS = [{"name": f"a{i}", "skill": s, "busy": 0}
          for i, s in enumerate(["sql", "sql", "web", "pdf"])]

def bid(agent, task):                      # local knowledge only
    fit = 1.0 if agent["skill"] == task["skill"] else 0.2
    return fit / (1 + agent["busy"]) + random.uniform(0, 0.05)

for tick in range(1, 20):
    for task in [t for t in TASKS if t["status"] == "open"]:
        bids = [(bid(a, task), a) for a in AGENTS]
        best, winner = max(bids, key=lambda b: b[0])
        task["status"], task["owner"] = "claimed", winner["name"]
        winner["busy"] += 1                # award changes future bids
    for a in AGENTS:                       # work off one claim per tick
        mine = [t for t in TASKS if t["owner"] == a["name"]
                and t["status"] == "claimed"]
        if mine:
            mine[0]["status"] = "done"; a["busy"] -= 1
    done = sum(t["status"] == "done" for t in TASKS)
    print(f"tick {tick}: {done}/{len(TASKS)} done")
    if done == len(TASKS):
        break
```
Load-balancing emerges from `1/(1+busy)` — no scheduler anywhere. Extensions: add evaporation (claimed tasks whose owner "crashes" reopen), a poisoned task that always fails, and Lesson 09's taint-tracking.

### Use It
Swap `bid()`'s heuristic for an LLM self-assessment and the fake work for real tool calls, and this skeleton is a production task router. The board becomes SQLite or Redis; ticks become an async loop. The architecture doesn't change.

### War Story
OpenAI's 2019 hide-and-seek project trained simple agents in a physics playground and watched strategies emerge across generations — tool use, barricades, and eventually box-surfing exploits of the physics engine that no researcher intended. Simulations don't just confirm your design; they find the loopholes in it. Yours will too, at much lower compute.

### Checkpoint
1. Where does load balancing come from in this simulation, given that no component implements it?
2. What happens if two agents claim the same task in a truly concurrent version, and how do you fix it?
3. How would you add Lesson 09's failure containment to this swarm?
