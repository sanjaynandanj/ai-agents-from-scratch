# Phase 11 — 👥 Multi-Agent Fundamentals

> One agent is a worker. Many agents are an organization — with org problems.

You know how to build one good agent; this phase is about what happens when you hire several. Multi-agent systems buy you parallelism, specialization, and clean context boundaries — and charge you coordination overhead, duplicated work, and a whole taxonomy of communication failures that will feel suspiciously like your last job. We'll treat the patterns as organizational design: bosses, handoffs, routing desks, shared whiteboards, and interns who need better briefs. By the end you'll build a working orchestrator-worker system from scratch and know when a single agent was the right answer all along.

## 01. Why Multi-Agent: Parallelism, Specialization, Context Isolation

**MOTTO:** You don't hire a second employee to think twice as hard — you hire them to think about something else.

### The Problem
One agent, one context window, one thread of attention. Wide tasks — research twenty sources, review forty files — force a single agent to serialize the work and cram every intermediate finding into one context until quality collapses under its own transcript.

### The Concept
Three distinct payoffs, often conflated:
```
Parallelism        N agents explore simultaneously   -> wall-clock wins
Specialization     each agent: narrow prompt + tools -> quality wins
Context isolation  each agent: own clean window      -> the sleeper win
```
Context isolation is the one people miss: a sub-agent can burn 100k tokens of messy exploration and return a 500-token summary, keeping the parent's context pristine. It's not about intelligence — it's about attention hygiene.

### Build It
Take a task with three independent sub-questions. Run it (a) as one agent sequentially, (b) as three agents with isolated contexts whose summaries feed a finalizer. Compare wall-clock, total tokens, and parent-context size at the end. Notice (b) costs *more* tokens while the parent context stays *smaller* — that trade is this entire phase.

### Use It
Frameworks with first-class sub-agents: Claude Agent SDK subagents, OpenAI Agents SDK, LangGraph subgraphs, AutoGen/AG2. But every pattern in this phase is implementable with the raw loop from Phase 9 — and this phase will do exactly that.

### War Story
Anthropic's June 2025 post on its multi-agent research system reported that an orchestrator (Opus 4) directing parallel Sonnet 4 workers beat a single-agent Opus 4 baseline by 90.2% on their internal research eval — with token usage roughly 15x a normal chat. Both numbers are the lesson: big wins on parallelizable breadth, at a very real price.

### Checkpoint
1. Which of the three payoffs applies even when sub-tasks *can't* run in parallel?
2. Why does context isolation improve the parent agent's output quality?
3. What class of task gets the least benefit from multiple agents?

## 02. When Multi-Agent Is Worse: The Coordination Tax

**MOTTO:** Every agent you add is another employee who wasn't in the meeting.

### The Problem
Multi-agent demos look great on read-only research tasks, then faceplant on tasks with tight coupling: two agents each make reasonable local decisions that are jointly incoherent — one names the module `auth/`, the other imports from `login/`.

### The Concept
Actions carry *implicit decisions*, and parallel agents can't see each other's. Cognition's "Don't Build Multi-Agents" essay (June 2025) makes the case bluntly: agents that don't share full context will make conflicting assumptions, so for tightly coupled work (like coding) you want one agent with full history, not a committee. Anthropic's research post — published the same month — isn't actually a rebuttal: their system wins on *read-heavy, parallelizable, loosely coupled* research, and they document the coordination effort it took. Read together, the two posts agree on the variable:

```
Coupling between sub-tasks:  low ──────────────────── high
Verdict:                     parallelize          single agent
```

### Build It
Deliberately trigger the failure: give two parallel agents halves of one coding task with a shared interface, no communication. Diff their outputs and catalog the conflicting implicit decisions (naming, error handling, data shapes). Then re-run with a shared spec document and count what survives.

### Use It
Decision test before going multi-agent: Can sub-tasks be verified independently? Is the shared state small enough to serialize into each brief? Is the task read-heavy? Three yeses, proceed. Any hard no — especially write-heavy coupling — stay single-agent and buy a bigger context window instead.

### War Story
Cognition (makers of Devin) published "Don't Build Multi-Agents" in June 2025, arguing from production coding-agent experience that context-sharing failures make parallel agents fragile, and distilling principles like "share full context" and "actions carry implicit decisions." That it landed the same month as Anthropic's pro-multi-agent research post gave the field its clearest matched pair of evidence — different task structures, different verdicts.

### Checkpoint
1. What is an "implicit decision," and why do parallel agents collide on them?
2. Why does coding stress multi-agent systems more than research does?
3. State the three-question test for whether a task can afford the coordination tax.

## 03. Orchestrator-Worker: The Boss Pattern

**MOTTO:** The boss's job is to plan, delegate, and synthesize — not to do the work twice.

### The Problem
Someone must decompose the task, decide how many workers to spawn, give each a brief, and merge results. Without a designated coordinator, you get either duplicated effort or orphaned sub-tasks nobody owns.

### The Concept
One orchestrator agent owns the goal; N workers own sub-tasks; results flow back up. The org chart is the architecture:

```
              ┌──────────────┐
   user ────> │ ORCHESTRATOR │ plan -> spawn -> wait -> synthesize
              └──┬────┬────┬─┘
                 ▼    ▼    ▼
              ┌────┐┌────┐┌────┐
              │ W1 ││ W2 ││ W3 │   isolated contexts, scoped tools
              └────┘└────┘└────┘
```
Key design decisions: does the orchestrator fix the plan upfront or adapt as results return; how many workers per task (effort scaling); and do workers ever talk to each other (in the pure pattern: never — all communication routes through the boss).

### Build It
Prototype the control flow with functions before LLMs: `plan(goal) -> briefs`, `run_worker(brief) -> result`, `synthesize(results) -> answer`, with workers in a thread pool. Lesson 12 fills in real prompts; the skeleton here is what you'll reuse.

### Use It
This is the pattern behind Anthropic's research system and Claude Code's subagents, and it's LangGraph's canonical "supervisor" example. Rule of thumb from practice: scale worker count to task complexity — one for a lookup, several for breadth — and cap it, because workers are the cost multiplier.

### War Story
Anthropic's June 2025 write-up describes exactly this shape: a lead agent plans and spawns parallel subagents, each searching independently and returning findings for synthesis. Among their published lessons: the orchestrator had to be explicitly taught effort scaling — how many subagents and tool calls a query deserves — or it over-hired for simple questions.

### Checkpoint
1. In the pure pattern, why don't workers communicate directly?
2. What is effort scaling, and what failure happens without it?
3. Which two responsibilities must the orchestrator never delegate?

## 04. Handoffs: Passing the Conversation

**MOTTO:** A handoff changes who's answering, not what's been said.

### The Problem
Some conversations outgrow their agent mid-stream: triage realizes this is a billing dispute; billing realizes it's actually fraud. Restarting the conversation with a new agent loses everything the user already said.

### The Concept
A handoff transfers *ownership of the ongoing conversation*: the transcript stays, the system prompt and tools swap. Mechanically (the Swarm/Agents SDK convention) it's a tool call — `transfer_to_billing` — whose effect is control flow: the loop continues with a different agent reading the same history. Contrast with delegation:

```
Delegation (Lesson 03): boss ──ask──> worker ──result──> boss   (boss keeps the mic)
Handoff:                agent A ──passes the mic──> agent B     (A exits the call)
```
Design tensions: does B see A's full transcript or a filtered version? Can B hand back? What stops triage ping-pong (A→B→A→B)?

### Build It
In your raw loop, register `transfer_to_<name>` tools per peer agent. On such a call: swap the active system prompt and tool list, append a handoff marker to the transcript, continue the same loop. Add a hop counter that halts after N transfers — you'll need it sooner than you think.

### Use It
OpenAI Agents SDK has handoffs as a first-class primitive (with input filters to shape what the receiver sees); the pattern ports to any loop. Best for sequential ownership transfer — support triage, escalation tiers — not for parallel work, which is Lesson 03's job.

### War Story
OpenAI's Swarm (October 2024) was essentially a teaching artifact for this one idea — handoffs as tool calls returning the next agent — and when the production Agents SDK replaced it in March 2025, handoffs survived as a core primitive. A pattern that outlived its own framework is a pattern worth learning framework-free.

### Checkpoint
1. Mechanically, what two things change at a handoff and what one thing persists?
2. When is a handoff wrong and delegation right?
3. What guardrail prevents infinite transfer loops?

## 05. Routing: The Right Agent for the Job

**MOTTO:** The receptionist doesn't fix your problem — they make sure the right person does.

### The Problem
One agent with every tool and a kitchen-sink prompt degrades: instructions dilute, wrong tools tempt, and every request pays for capabilities it doesn't need. But making users pick a specialist is worse.

### The Concept
A router classifies the request *before* real work starts, then dispatches to a specialist — and, unlike a handoff, the router never does domain work itself. Routers come in ascending cost: keyword rules, embedding similarity, a small classifier LLM, or a full agent that can ask one clarifying question first.

```
request ──> ROUTER ──┬──> refunds agent
  (classify only)    ├──> tech-support agent
                     ├──> sales agent
                     └──> fallback/human   <- always have this arm
```
Routing also picks *models*, not just prompts: cheap model for easy intents, frontier model for hard ones.

### Build It
Build a two-stage router: rules first (regex on obvious intents), LLM classifier for the remainder, emitting `{"route": ..., "confidence": ...}` — below a confidence floor, route to fallback. Evaluate as the classifier it is: a labeled set of 50 requests and a confusion matrix, before any downstream agent runs.

### Use It
Anthropic's "Building Effective Agents" (December 2024) lists routing among its core workflow patterns for exactly this reason: separation of concerns lets each downstream prompt stay sharp. For model-level routing, the RouteLLM work (LMSYS, 2024) is the reference point.

### War Story
RouteLLM (from the LMSYS group, 2024) showed that a learned router sending easy queries to a weak model and hard ones to a strong model could cut costs dramatically — by more than 85% on some benchmarks — while retaining most of the strong model's quality. Routing is the rare pattern that improves the bill and the latency at the same time.

### Checkpoint
1. What distinguishes a router from a handoff agent?
2. Why must a router be evaluated like a classifier, and with what artifact?
3. What belongs in the fallback arm, and why is it non-optional?

## 06. Shared State and Blackboards

**MOTTO:** Stop forwarding emails; get a whiteboard.

### The Problem
With N agents, point-to-point sharing means N² conversations, and each message re-serializes state that three other agents also need. Meanwhile no one holds the current best picture of the task.

### The Concept
The blackboard pattern — borrowed from 1970s AI — inverts the flow: a shared store holds the evolving solution; agents read it, contribute what their specialty allows, and write findings back for others to build on. Detectives around an evidence board, not a group chat.

```
        ┌───────────────────────────┐
        │        BLACKBOARD         │  facts / hypotheses / open questions
        └───┬────────┬─────────┬────┘
      read/write  read/write  read/write
        ┌───┴──┐  ┌──┴───┐  ┌──┴───┐
        │ Agt A│  │ Agt B│  │ Agt C│
        └──────┘  └──────┘  └──────┘
```
Modern incarnations: a scratchpad file agents edit, a shared task list, a keyed dict in your graph state. The hard problems are the write rules: who may overwrite whom, how conflicts resolve, and what stops the board becoming a landfill of stale notes.

### Build It
Implement a blackboard as a JSON file with sections (`facts`, `open_questions`, `draft`) and write-discipline: agents append to facts, claim questions before working them, and only a designated agent edits the draft. Run three agents against it round-robin and watch for the two classic failures: lost updates and stale reads.

### Use It
LangGraph's shared typed state *is* a blackboard with reducers as write rules; MetaGPT's shared message pool is the same idea; Claude-style agents using a `NOTES.md` file are the folk version. Use blackboards when many agents need the same evolving picture; use messages (next lesson) for directed requests.

### War Story
The blackboard architecture predates LLMs by half a century: CMU's Hearsay-II speech-understanding system (1970s) coordinated independent specialist modules through exactly this shared-hypothesis store. Multi-agent LLM systems rediscovered it because the org problem it solves — many specialists, one evolving solution — didn't change, only the specialists did.

### Checkpoint
1. What communication problem does a blackboard solve that point-to-point messaging doesn't?
2. Name the two classic concurrent-write failures and one mitigation for each.
3. When are directed messages the better choice than shared state?

## 07. Message Passing Between Agents

**MOTTO:** If it's not addressed, typed, and answerable, it's not a message — it's a vibe.

### The Problem
Agents that communicate by dumping prose into each other's prompts create untraceable systems: no record of who asked whom for what, no way to retry a lost request, no way to run agents on separate machines.

### The Concept
Treat inter-agent communication like a distributed system, because it is one. A message has an envelope and a typed payload:

```json
{"id": "m-042", "from": "researcher", "to": "writer",
 "type": "FINDINGS", "reply_to": "m-039",
 "payload": {"claims": [...], "sources": [...]}}
```
This buys you the actor model's virtues — agents as isolated processes reacting to mail — plus auditability (the message log is your trace) and topology freedom (in-process queue today, Redis or a real broker tomorrow). The LLM-specific catch: payloads get *interpreted* by the receiver's model, so schema discipline on payloads matters as much as on tool calls.

### Build It
Refactor Lesson 03's skeleton onto `queue.Queue` mailboxes: each agent is a loop of `receive -> think -> send`. Define three message types (`TASK`, `RESULT`, `ERROR`), log every envelope to a JSONL file, and replay the log to reconstruct any run. That log is also your eval dataset later.

### Use It
AutoGen's conversation transcripts, AG2, and actor frameworks generally; LangGraph edges carry state rather than messages, which is the other valid answer. Escalate infrastructure only with need: in-process queues → Redis streams → a proper broker. Most systems die before needing Kafka.

### War Story
Microsoft's AutoGen 0.4 rewrite (January 2025) rebuilt the framework around an event-driven, actor-style architecture with asynchronous message passing — replacing the original's more tightly coupled conversation model. When a framework's 1.0-scale rewrite converges on forty-year-old distributed-systems patterns, take the hint about where multi-agent plumbing ends up.

### Checkpoint
1. What belongs in a message envelope, and what does each field enable?
2. Why does schema discipline matter *more* when the receiver is an LLM?
3. What can you reconstruct from a complete message log?

## 08. Sub-Agent Context: What to Tell the Intern

**MOTTO:** A sub-agent knows exactly what you told it — and will improvise the rest.

### The Problem
Context isolation cuts both ways: the sub-agent that can't see the parent's clutter also can't see the parent's *intent*. Underspecified workers return the wrong thing confidently; overspecified ones inherit the bloated context you spawned them to avoid.

### The Concept
Writing a worker brief is delegating to a smart intern with amnesia. The load-bearing sections:

```
OBJECTIVE   the sub-goal, plus one line of parent intent ("this feeds a pricing memo")
OUTPUT      exact format and length of what to return
TOOLS       which tools, with any usage guidance
BOUNDARIES  what NOT to do, when to stop, budget (calls/tokens/time)
CONTEXT     the minimal excerpt of parent state that's actually relevant
```
The craft is the CONTEXT line: too little and the worker re-derives (or contradicts) parent decisions — Lesson 02's implicit-decision collision; too much and you've re-created the monolith.

### Build It
Take one worker from your Lesson 03 skeleton and write three brief variants: minimal (one sentence), structured (the template above), and full-dump (entire parent transcript). Run each five times; score correctness, relevance of what came back, and tokens spent. The structured brief should win — but *see* the failure shapes of the other two.

### Use It
Claude Agent SDK subagents (each defined by its own scoped prompt and tool list), OpenAI Agents SDK handoff input filters, and CrewAI task descriptions are all this template wearing different syntax. The template is portable; write it once as a function, `brief(objective, output_spec, tools, boundaries, context)`.

### War Story
Anthropic's June 2025 multi-agent post reports this lesson from production: early subagents given vague instructions duplicated each other's work and wandered off-task, and the fix was orchestrator prompts that spell out each subagent's objective, output format, tool guidance, and task boundaries. The intern brief isn't a nicety; it was one of their headline engineering lessons.

### Checkpoint
1. Why does a worker need a line of parent *intent*, not just its sub-goal?
2. What failure modes do the too-little and too-much context extremes produce?
3. Why do budgets belong in the brief rather than only in the runtime?

## 09. Result Synthesis: Merging Parallel Work

**MOTTO:** Ten good reports stapled together is not one good report.

### The Problem
Parallel workers return overlapping, partially contradictory, differently formatted results. Naive concatenation produces a document with three introductions and two answers; naive summarization silently drops the one finding that mattered.

### The Concept
Synthesis is its own job with its own steps — deduplicate, reconcile conflicts, weigh evidence, restructure around the original question, and preserve attribution:

```
worker outputs ──> DEDUPE ──> CONFLICT CHECK ──> WEIGH ──> COMPOSE ──> ATTRIBUTE
                    same claim    A says X,        source     answer the   which worker/
                    twice? drop   B says ¬X:       quality,   QUESTION,    source backs
                                  flag, don't      recency    not the      each claim?
                                  average          count      task list
```
Two structural choices: a dedicated synthesizer agent reading structured worker outputs (clean contexts, extra hop) versus the orchestrator synthesizing inline (fewer hops, context pressure). Conflicts deserve special respect — surfacing "sources disagree" is synthesis; averaging disagreement into mush is malpractice.

### Build It
Have workers return a fixed schema — `claims: [{statement, evidence, confidence, source}]` — never prose. Write the synthesizer prompt to (1) answer the *original* question, (2) list conflicts explicitly, (3) cite the contributing worker per claim. Test it on manufactured disagreement: plant contradictory claims and verify they surface rather than vanish.

### Use It
Anthropic's research system routes subagent findings through the lead agent for exactly this compose step, with citation handling as a distinct concern. Structured worker outputs (Phase 10, Lesson 08 techniques) are what make synthesis tractable — prose in, mush out.

### War Story
Together AI's Mixture-of-Agents work (2024) made synthesis itself the architecture: layers of open-source models propose answers and an aggregator synthesizes them, and the ensemble outperformed GPT-4o on AlpacaEval 2.0 (65.1% vs 57.5% reported). The aggregation step wasn't overhead — it was where the quality came from.

### Checkpoint
1. Why must conflicts be surfaced rather than averaged?
2. What does requiring a claims schema from workers buy the synthesizer?
3. When does inline orchestrator synthesis beat a dedicated synthesizer, and vice versa?

## 10. Debate and Critique: Adversarial Collaboration

**MOTTO:** If everyone in the room agrees instantly, the room is too small.

### The Problem
A single model grading its own work inherits its own blind spots; ask it to double-check and it mostly congratulates itself. Errors that survive one forward pass tend to survive self-review too.

### The Concept
Split the roles so incentives differ: a *critic* agent is prompted to find flaws (and only that); *debate* runs multiple agents proposing answers, reading each other's reasoning, and revising over rounds. It's peer review versus proofreading your own paper.

```
PROPOSE ──> agents answer independently
EXCHANGE ─> each reads the others' answers + reasoning
REVISE ───> each updates (or defends) its position
JUDGE ────> converge, vote, or a judge agent decides
```
Honest limits: debaters drift toward consensus (sycophancy) rather than truth; confident-wrong agents can drag the group; and rounds multiply cost. Critique works best on *checkable* claims — code, math, citations — and worst on matters of taste.

### Build It
Add a critic to any earlier pipeline: producer emits work plus claimed properties; critic gets *only* the work and a rubric (no producer reasoning — avoid anchoring); producer revises once against specific objections. Measure pass-rate delta on your eval versus the single-pass baseline, and the token multiple you paid for it.

### Use It
Reviewer/critic roles in AutoGen and CrewAI ship this pattern off-the-shelf; reflection loops (Phase 3) are its single-agent cousin. Spend the critique budget where errors are expensive and verifiable — generated code before execution, claims before publication — not on every step.

### War Story
Du et al. (MIT and Google, 2023) showed in "Improving Factuality and Reasoning in Language Models through Multiagent Debate" that multiple LLM instances debating over rounds improved accuracy on math and reasoning benchmarks and reduced hallucinated facts versus single-model baselines. Follow-up work has mapped the limits — convergence isn't truth — but the core effect established critique as a legitimate accuracy tool, not theater.

### Checkpoint
1. Why is a separate critic more effective than asking the producer to self-check?
2. What is the sycophancy failure in debate, and what design choices dampen it?
3. On what kinds of claims does critique pay best, and why?

## 11. Delegation Depth: Agents Spawning Agents

**MOTTO:** Middle management multiplies — cost, latency, and blame all compound with depth.

### The Problem
If an orchestrator can spawn workers, a worker can spawn its own workers — and now you have recursion with an API bill. Depth amplifies everything: each level adds latency, multiplies tokens, garbles intent like a game of telephone, and blurs who's accountable for the final answer.

### The Concept
Treat delegation like stack depth — legal, useful, and in need of hard limits:

```
depth 0  orchestrator          budget: 100 units
depth 1  ├─ worker A           gets 30, may sub-delegate
depth 2  │   └─ sub-worker A1  gets 10, MAY NOT delegate
         └─ worker B           gets 30
```
Three disciplines: a *depth cap* (2 is almost always enough; the orchestrator plans, workers execute, sub-workers fetch); *budget inheritance* (children draw from the parent's allowance, so total cost is bounded by construction); and *provenance* (every result carries its path — `orchestrator/A/A1` — so you can debug the tree). Intent decay is the quiet killer: each re-briefing loses parent context, so deep leaves optimize for goals nobody actually has.

### Build It
Add `depth` and `budget` to Lesson 08's brief function. Enforce in the spawn path: refuse spawns beyond the cap, deduct child budgets from the parent, and tag results with the full delegation path. Then write the test that tries to blow the stack — an agent whose task says "delegate this" — and confirm the runtime, not the model's good manners, stops it.

### Use It
Real systems are conservative here: Claude Code's subagents don't spawn their own subagents (depth 1 by construction), and Anthropic's research system runs a lead agent over one layer of parallel subagents. When you're tempted by depth 3+, the usual right answer is a better plan at depth 0.

### War Story
AutoGPT (March 2023) became one of the fastest repositories ever to 100k GitHub stars on the promise of recursive, self-directed task decomposition — and became equally famous for spinning in loops, re-deriving its own sub-tasks, and burning users' API credits without converging. It remains the canonical demonstration that unbounded delegation is an outage, not an architecture.

### Checkpoint
1. Why does budget inheritance bound total cost "by construction"?
2. What is intent decay, and which discipline mitigates it?
3. Why must the depth cap live in the runtime rather than the prompt?

## 12. Build an Orchestrator-Worker System From Scratch

**MOTTO:** If you can build it with a mock LLM, you actually understand the pattern.

### The Problem
Final exam. Every pattern in this phase — decomposition, briefs, parallel workers, budgets, synthesis — assembled into one runnable system, with a mock LLM so the *coordination logic* is what's under test, deterministic and free.

### The Concept
The mock returns scripted responses per role, which forces an honest architecture: if your system only works because a frontier model papers over sloppy coordination, the mock will expose it. Swapping the mock for a real client at the end should change one function.

### Build It
```python
import json
from concurrent.futures import ThreadPoolExecutor

class MockLLM:                                # swap for a real client later
    def complete(self, role, prompt):
        if role == "planner":
            return json.dumps([
                {"id": "T1", "objective": "gather facts on topic A"},
                {"id": "T2", "objective": "gather facts on topic B"}])
        if role == "worker":
            task = prompt.split("OBJECTIVE: ")[1].splitlines()[0]
            return json.dumps({"claims": [{"statement": f"finding for {task}",
                                           "confidence": 0.9, "source": task}]})
        return "SYNTHESIS: " + prompt[:120]   # synthesizer

LLM = MockLLM()

def brief(task):                              # Lesson 08's template
    return (f"OBJECTIVE: {task['objective']}\n"
            "OUTPUT: JSON {claims:[{statement,confidence,source}]}\n"
            "BOUNDARIES: budget 10 units, no sub-delegation")

def run_worker(task):
    return json.loads(LLM.complete("worker", brief(task)))

def orchestrate(goal, max_workers=4):
    tasks = json.loads(LLM.complete("planner", f"Decompose: {goal}"))
    assert len(tasks) <= max_workers, "effort scaling cap (Lesson 03)"
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        results = list(pool.map(run_worker, tasks))         # parallel, isolated
    merged = [c for r in results for c in r["claims"]]      # dedupe/conflict-check here
    return LLM.complete("synthesizer",
                        f"Question: {goal}\nClaims: {json.dumps(merged)}")

print(orchestrate("Compare topic A and topic B"))
```
Extensions, in order: real dedupe and conflict flagging in the merge; per-worker budgets with deduction; a `MockLLM` that returns malformed JSON 20% of the time (now your retry logic matters); a JSONL message log per Lesson 07; and finally the real-client swap.

### Use It
This ~50-line skeleton is structurally what LangGraph supervisors, Agents SDK orchestration, and Claude Agent SDK subagents give you with more polish. Having built it, you can now read any of their docs and name each component — which was the point of the phase.

### War Story
The "Generative Agents" paper (Park et al., 2023) dropped 25 LLM-driven agents into a simulated town — Smallville — and watched coordination emerge: one agent, prompted to plan a Valentine's Day party, spread invitations agent-to-agent until others autonomously showed up. It was a landmark for what multi-agent coordination *can* do, and its cost profile (continuous simulation of 25 agents) was an early preview of Lesson 01's token bill.

### Checkpoint
1. What does the mock LLM prove about your system that a real model would hide?
2. Where in the code do Lessons 03, 08, and 09 each appear?
3. What must change — and what must not — when you swap in a real LLM client?
