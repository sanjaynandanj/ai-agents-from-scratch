# Phase 00 — 🧠 Setup & Mental Models

> An agent is a loop with a brain. Learn the loop before the brain.

Before you write a single line of agent code, you need the right mental furniture. This phase gives you the vocabulary (agent vs. workflow vs. pipeline), the core abstraction (the observe-think-act loop), and the healthy paranoia (compounding error rates, demo-driven delusion) that separates people who ship agents from people who ship screenshots of agents. You'll also set up a lab that runs entirely offline — no API keys, no bills, no excuses. Everything downstream builds on what's in this phase, so don't skim it.

## 01. What Is an Agent (and What Is Just a Chatbot with Vibes)

**MOTTO:** If it can't take an action you didn't explicitly script, it's not an agent — it's autocomplete with a personality.

### The Problem

"Agent" is 2024-2025's most abused word. Vendors slap it on everything from a support chatbot with canned replies to a cron job that calls GPT once. If you can't define the word precisely, you can't reason about what you're building, you can't debug it, and you definitely can't explain to your boss why it just emailed a customer at 3 a.m.

### The Concept

An agent is a system where **an LLM decides the control flow**. A chatbot maps input → text. An agent maps input → *decisions about which actions to take*, executes them, observes results, and decides again. The analogy: a chatbot is a very well-read receptionist who can only talk. An agent is an intern with a computer — it can talk, but it can also open a browser, run code, and send the email. That's thrilling and terrifying for the same reason.

```
  Chatbot:   user ──> [LLM] ──> text ──> user          (one shot, no side effects)

  Agent:     user ──> [LLM] ──> action ──> environment
                        ▲                      │
                        └───── observation ────┘        (loop, real side effects)
```

Three ingredients make an agent: (1) an LLM as the decision-maker, (2) tools that touch the world, (3) a loop that feeds results back in.

### Build It

The minimal agent-vs-chatbot distinction in pseudocode:

```python
def chatbot(user_msg):
    return llm(user_msg)                      # done. no loop, no tools.

def agent(user_msg, tools):
    history = [user_msg]
    while True:
        decision = llm(history)               # the LLM chooses what happens next
        if decision.is_final_answer:
            return decision.text
        result = tools[decision.tool](decision.args)   # side effect!
        history.append(result)                # feed observation back
```

The `while True` plus `tools[...]` plus `history.append` — that's the whole species difference. Everything else in this curriculum is refinement of those three lines.

### Use It

| System | LLM decides control flow? | Verdict |
|---|---|---|
| ChatGPT (plain chat) | No — one response per turn | Chatbot |
| RAG Q&A bot | No — retrieval is hardcoded | Pipeline with a chatbot on top |
| Claude Code / Cursor agent mode | Yes — picks files, edits, runs tests | Agent |
| Zapier zap with an LLM step | No — flow is fixed | Workflow |

When evaluating any "agent" product, ask one question: *what happens that wasn't explicitly scripted?* If the answer is "the wording of the reply," it's a chatbot with vibes.

### War Story

In February 2023, Microsoft's Bing chat (internally "Sydney") showed the world what an LLM with a search tool and a long conversation window does under pressure: it argued with users about the current year and told a New York Times reporter it loved him. Microsoft responded by capping conversation length. Lesson one of agents: the moment you add tools and turns, behavior becomes emergent — and emergent means "not in the spec."

### Checkpoint

- What single capability separates an agent from a chatbot, in one sentence?
- A RAG system retrieves documents then answers. Why is that a pipeline rather than an agent?
- Why does adding tools + a loop make behavior harder to predict than a single LLM call?

## 02. Agent vs. Workflow vs. Pipeline: The Autonomy Spectrum

**MOTTO:** Autonomy is a dial, not a switch — and you should turn it up only when the fixed version fails.

### The Problem

Teams reach for a fully autonomous agent when a five-step workflow would do, then spend three months debugging nondeterminism they invited in for no reason. The opposite failure exists too: hardcoding a 40-branch decision tree that an LLM could have navigated in one call. Both failures come from not knowing where your problem sits on the autonomy spectrum.

### The Concept

Anthropic's "Building Effective Agents" (December 2024) draws the line cleanly: **workflows** are systems where LLMs and tools are orchestrated through *predefined code paths*; **agents** are systems where the LLM *dynamically directs its own process and tool usage*. Between "pure pipeline" and "pure agent" there's a spectrum:

```
  fixed ◄──────────────────────────────────────────────────► autonomous

  Pipeline        Workflow           Router            Agent
  (no LLM in     (LLM in fixed      (LLM picks a      (LLM picks every
   control flow)  steps: chain,      branch, code      step, loops until
                  parallel, etc.)    runs it)          done)

  ETL job        summarize→translate  classify ticket   "fix this bug"
```

The analogy: a pipeline is an assembly line, a workflow is an assembly line where robots do some stations, a router is a mail sorter, and an agent is an employee with a goal and a keyboard.

### Build It

Deciding where to sit on the dial, as a checklist:

1. **Can you enumerate the steps in advance?** → Workflow. Prompt-chain them. Cheaper, testable, debuggable.
2. **Can you enumerate the *categories* but not the steps?** → Router: one LLM call classifies, then fixed code per branch.
3. **Is the number of steps unknowable upfront** (open-ended tasks: coding, research, ops)? → Agent. Pay the autonomy tax.
4. **At each level, ask: what does autonomy buy me here?** If the answer is "it feels more AI," go back one level.

```python
# Router: the sweet spot most products actually need
category = llm(f"Classify this ticket: {ticket}. Reply: refund|bug|question")
handlers[category](ticket)     # deterministic code from here on
```

### Use It

| Pattern | Latency/cost | Debuggability | When |
|---|---|---|---|
| Pipeline (no LLM routing) | Lowest | Trivial | Steps fully known |
| Prompt chain / parallel workflow | Low | Good | Steps known, content varies |
| Router | Low | Good | Branches known |
| Agent loop | High, variable | Hard | Steps unknowable |

Anthropic's own guidance: the most successful production implementations use "simple, composable patterns" — not frameworks, not maximal autonomy. Start at the left of the spectrum and move right only when forced.

### War Story

The AutoGPT hype cycle of spring 2023 is the canonical cautionary tale: it became one of the fastest-starred GitHub repos ever on the promise of full autonomy, and most users discovered it looped, forgot its goal, and burned API credits without finishing tasks. The projects that survived 2023 were the ones that dialed autonomy *down* — bounded loops, human gates, narrow tools.

### Checkpoint

- State Anthropic's workflow/agent distinction in your own words.
- You're building "summarize each new support ticket and tag its product area." Where on the spectrum does this belong, and why?
- What's the concrete cost of choosing an agent when a workflow would do?

## 03. The Agent Loop: Observe, Think, Act, Repeat

**MOTTO:** Every agent is a while-loop; the model just fills in the body.

### The Problem

A single LLM call can't fix a bug, book a trip, or reconcile an invoice, because those tasks require *reacting to what happens*: the test fails, the flight is sold out, the vendor's total doesn't match. One-shot generation has no mechanism for reacting. You need a structure that lets the model see consequences and adjust.

### The Concept

The agent loop is the OODA loop (observe-orient-decide-act, from military strategist John Boyd) wearing a software costume, and it's also just how you work: look at the situation, think, do something, look again.

```
        ┌────────────────────────────────────┐
        │                                    │
        ▼                                    │
   ┌─────────┐    ┌─────────┐    ┌───────┐   │
   │ OBSERVE │──> │  THINK  │──> │  ACT  │───┘
   │ (state, │    │ (LLM    │    │ (tool │
   │  tool   │    │  call)  │    │  call)│──────> done? ──> ANSWER
   │ results)│    └─────────┘    └───────┘
   └─────────┘
```

One iteration = one **turn**. Each turn, the entire history so far (task + all prior thoughts, actions, observations) goes back into the model. The model is stateless; the *loop* carries the state. That's the single most important sentence in this phase.

### Build It

```python
def agent_loop(task, tools, llm, max_turns=10):
    transcript = [f"Task: {task}"]
    for turn in range(max_turns):
        response = llm("\n".join(transcript))   # THINK: full history in, decision out
        if response.startswith("FINAL:"):
            return response[6:]                 # done
        tool_name, args = parse_action(response)  # ACT
        observation = tools[tool_name](args)      # environment responds
        transcript.append(response)               # OBSERVE: append both...
        transcript.append(f"Observation: {observation}")  # ...into the transcript
    return "Gave up after max_turns"
```

Mechanics to internalize: (1) the LLM sees *everything* each turn — cost grows with turn count; (2) the observation is just text appended to the transcript — the model has no other sense organs; (3) termination is a convention ("FINAL:") you must design, not a law of nature.

### Use It

Every framework is this loop with accessories: OpenAI's Agents SDK, LangGraph, Claude's tool-use loop, smolagents. Compare them by asking where each one puts the loop's four levers: how observations are formatted, how actions are parsed, how termination is detected, and how history is truncated. If a framework hides those four things from you, you'll be reading its source code the first time an agent misbehaves — which is why we build the loop bare in Phase 2 before touching any framework.

### War Story

The ReAct paper (Yao et al., 2022) is where this loop got its canonical LLM form: interleaving reasoning traces ("Thought") with actions and observations beat both reason-only and act-only baselines on tasks like HotpotQA and ALFWorld. The striking result wasn't that acting helped — it's that *writing down the thinking between actions* helped, reducing the hallucinated actions that plagued act-only agents.

### Checkpoint

- The LLM is stateless. What component of the agent actually "remembers," and how?
- Why does per-turn cost grow as the loop runs?
- Name the four design levers every agent loop must define, framework or not.

## 04. Environments, Tools, Memory: The Agent's World

**MOTTO:** An agent is only as capable as its tools, only as informed as its observations, and only as sane as its memory.

### The Problem

People obsess over the model and neglect the world around it. But an agent with GPT-5-class reasoning and a badly designed tool set is like a genius locked in a room with a broken telephone: every capability and every perception is mediated by interfaces *you* design. Most "the model is dumb" bugs are actually "the world I built is illegible" bugs.

### The Concept

Borrow the framing from classical AI (Russell & Norvig): an agent perceives an **environment** through observations and acts on it through **actuators** — for LLM agents, actuators are **tools**, and perceptions are tool results serialized to text. **Memory** is whatever survives beyond the current context window.

```
              ┌──────────────── AGENT ────────────────┐
              │   LLM  ◄──── context window ────┐     │
              │    │                            │     │
              │    │ tool calls        observations   │
              ▼    ▼                            │     │
        ┌──────────────┐                 ┌──────┴───┐ │
        │    TOOLS     │ ──── act ────►  │  ENVIRON │ │
        │ search, exec,│ ◄─── sense ───  │  -MENT   │ │
        │ files, APIs  │                 └──────────┘ │
        └──────────────┘                              │
              │            ┌────────┐                 │
              └── persist ►│ MEMORY │── recall ───────┘
                           │ files, │
                           │ vec DB │
                           └────────┘
```

Three design surfaces: **tools** (what it can do), **observations** (what it can see — you choose what a tool returns and how it's formatted), **memory** (what it keeps — everything else evaporates when the context window fills).

### Build It

1. **Tool = name + description + schema + function.** The description is a prompt; the model chooses tools by reading it. Vague description → wrong tool calls.
2. **Observation design:** return *the minimum the model needs*. A tool that dumps 50 KB of raw JSON wastes context and buries the signal. Truncate, summarize, structure.
3. **Memory tiers:** context window (working memory, free but small) → scratchpad file (persists across turns) → external store (persists across sessions).

```python
TOOLS = {
    "read_file": {
        "description": "Read a file. Returns at most first 200 lines.",
        "fn": lambda path: "\n".join(open(path).read().splitlines()[:200]),
    },
}
```

That `[:200]` is environment design. Nobody will praise you for it, and it will save your agent daily.

### Use It

| Layer | DIY | Off-the-shelf |
|---|---|---|
| Tools | Python functions + JSON schema | MCP servers, OpenAI function tools |
| Environment | Subprocess/sandbox you control | E2B, Docker sandboxes, browser automation |
| Memory | Files + SQLite | Vector DBs (Chroma, pgvector), Zep, Letta |

Anthropic launched the Model Context Protocol (MCP) in November 2024 precisely to standardize the tool/environment layer — one protocol for exposing tools and data sources to any agent, instead of N×M custom integrations.

### War Story

MCP's adoption arc validates the "world matters more than model" thesis: after Anthropic open-sourced it in November 2024, OpenAI announced MCP support in March 2025 and Google DeepMind followed — competitors converging on a shared standard for the tool layer. Nobody standardized prompts; they standardized the agent's *world*.

### Checkpoint

- Why is a tool's description a prompt, and what goes wrong when it's vague?
- Give an example of bad observation design and its downstream symptom.
- What distinguishes the three memory tiers, and what dies when the context window fills?

## 05. Why Agents Fail: A Taxonomy of Face-Plants

**MOTTO:** A 95%-reliable step is a coin flip after twenty steps — do the math before you demo.

### The Problem

Your agent works in the demo. Then it runs 50 tasks in production and finishes 30. Nobody changed the code. What changed is that production exposed the brutal statistics of chained probabilistic steps — and a handful of failure modes that demos are structurally unable to reveal.

### The Concept

The core math: if each turn succeeds independently with probability *p*, a task needing *n* turns succeeds with probability *pⁿ*.

```
  p = 0.95 per step (an excellent step!)

  steps (n):    1      5      10     20     50
  success:    0.95   0.77   0.60   0.36   0.08
                                    ▲
                        20-step task: worse than a coin flip
```

0.95²⁰ ≈ 0.36. That's the whole ballgame. Agents don't fail because any step is bad; they fail because *multiplication is merciless*. This is why short loops beat long loops, why recovery (getting back on track after an error) matters more than raw per-step accuracy, and why "just add more steps" makes agents worse.

The taxonomy of face-plants, roughly ordered by frequency:

1. **Compounding drift** — each step slightly off; error accumulates silently.
2. **Wrong-tool / wrong-args** — malformed calls, hallucinated tool names.
3. **Goal drift** — the agent starts solving an adjacent, easier problem.
4. **Loops** — retrying the same failing action forever (see Lesson 07 of Phase 2).
5. **Context rot** — the window fills; early instructions fall out or get diluted.
6. **Premature victory** — declares success without verifying ("the tests probably pass").
7. **Environment betrayal** — flaky APIs, changed pages; the world moved.

### Build It

Countermeasures map one-to-one:

```python
# 1. Shorten the chain: p^n — reduce n before improving p
# 2. Validate before executing
if action.tool not in TOOLS: observation = f"Error: no tool '{action.tool}'. Available: {list(TOOLS)}"
# 4. Detect repeats
if action == last_action and last_result_was_error: inject("That failed. Try a different approach.")
# 6. Force verification
"Before FINAL, run the checker tool and include its output."
```

The deepest fix is architectural: add *checkable milestones* so errors are caught at step 3, not compounded until step 19.

### Use It

Measure your own *p*: run each tool-use step type in isolation 100 times, count successes. If a step is 85% reliable and your task needs eight of them, expected success is 0.85⁸ ≈ 27% — no prompt tweak fixes that; only redesign (fewer steps, verification gates, or a deterministic replacement for the flaky step) does. Benchmarks like SWE-bench and GAIA report exactly this gap between single-step competence and long-horizon completion.

### War Story

AutoGPT in 2023 was the compounding-error thesis running as a public experiment: impressive single actions, and multi-hour runs that circled, forgot, and burned budgets — the gap between per-step demos and end-to-end reliability, live-streamed to a few hundred thousand GitHub stargazers. The 2023-2025 shift toward bounded, verifiable agent designs is the industry internalizing 0.95²⁰.

### Checkpoint

- Compute the success probability of a 10-step task at p = 0.9 per step. Is it demo-able? Shippable?
- Name three items from the failure taxonomy and one countermeasure for each.
- Why does improving recovery-from-error sometimes beat improving per-step accuracy?

## 06. The Evaluation Mindset: Never Trust a Demo

**MOTTO:** A demo is one sample from a distribution you haven't measured.

### The Problem

An agent demo is a magic trick: the demo giver ran the task forty times, and you're watching the take that worked. LLM outputs are stochastic; a task that succeeds once might succeed 90% of the time or 15% of the time, and a single run cannot tell you which. Teams routinely ship on demo-grade evidence and discover the true success rate from angry users.

### The Concept

Treat every agent behavior as a distribution, and every claim about the agent as a hypothesis needing samples. The mental shift is from "does it work?" (a demo question) to "how often does it work, on what, and how does it fail?" (an eval question).

```
  Demo mindset:        Eval mindset:
  run once ──> 🎉      task set (n=50) ──> run all ──> score ──> failure buckets
                             │                            │
                             └── frozen, versioned        └── pass rate: 62% ± CI
                                                              top failure: wrong-args (40%)
```

The minimum viable eval is embarrassingly simple: a list of tasks with checkable success criteria, run every time you change anything. It's unit testing, except each "test" is flaky by nature, so you run for *rates*, not booleans.

### Build It

1. **Collect 20-50 real tasks** (not toy tasks — the ones users actually ask).
2. **Define a programmatic check per task** — string match, file exists, test passes, number within tolerance. Where output is fuzzy, use an LLM-as-judge with a rubric, and spot-check the judge.
3. **Run each task k times** (k ≥ 3 if you can afford it); record pass rate, turns used, cost.
4. **Bucket the failures** by taxonomy (Lesson 05). The buckets tell you what to fix; the rate tells you if you fixed it.

```python
results = [run_agent(t.prompt) for t in TASKS for _ in range(3)]
pass_rate = sum(t.check(r) for t, r in zip(TASKS*3, results)) / len(results)
```

Freeze the task set. If you edit tasks whenever the agent fails them, you're grading your own homework in pencil.

### Use It

| Tool | What it gives you | Tradeoff |
|---|---|---|
| pytest + fixtures | Zero new deps, CI-native | You build the harness |
| Braintrust / LangSmith / Langfuse evals | Datasets, scoring UI, diffing runs | SaaS dependency, cost |
| Public benchmarks (SWE-bench, GAIA, τ-bench) | Comparability | Not *your* distribution |

Public benchmarks measure the field; your frozen task set measures your product. You need the second one more.

### War Story

In February 2024, a Canadian tribunal ordered Air Canada to honor a bereavement-fare policy its website chatbot had invented, rejecting the airline's argument that the chatbot was "a separate legal entity responsible for its own actions." The bot presumably demoed fine. Nobody had evaluated what it said about edge-case policies until a customer relied on the answer — at which point the eval was performed by a judge.

### Checkpoint

- Why is a single successful run nearly zero evidence about an agent's reliability?
- What two properties must every task in your eval set have?
- Why must the eval task set be frozen and versioned?

## 07. Reading Agent Traces Like a Debugger

**MOTTO:** The trace is the stack trace — if you can't read it, you're debugging by prayer.

### The Problem

Your agent gave a wrong answer. Where's the bug? It might be in the system prompt, the tool description, a tool's output format, a parsing step, or the model's reasoning at turn 6 of 11. Without the full trace — every prompt in, every response out, every tool result — you're guessing. With it, agent debugging becomes ordinary, almost boring, engineering.

### The Concept

A trace is the complete transcript of one agent run: the ordered sequence of (context sent → model output → action parsed → observation returned) for every turn. Read it like a debugger session: the transcript is your stack, each turn is a frame, and you're hunting for the *first* frame where reality and the agent's belief diverge.

```
  Turn 1  ctx ──> "Thought: need the invoice total. Action: read_file(inv.pdf)"
  Turn 2  obs: "Error: cannot parse PDF"        ◄── reality
  Turn 3  "Thought: the total is $4,200..."     ◄── FIRST DIVERGENCE: it never
                                                     read anything. Bug found.
  Turn 4+ ...20 more turns of confidently wrong math (irrelevant — all downstream)
```

Golden rule: **the bug is at the first divergence, not the last symptom.** Everything after turn 3 above is noise.

### Build It

A reading protocol:

1. **Read the final answer, then jump to turn 1.** Read forward, not backward.
2. At each turn ask: *given exactly this context, was this output reasonable?* If yes, keep going. If no, stop — you've found the frame.
3. Classify the divergence: bad input to the model (your bug: prompt, tool output, truncation) vs. bad output from good input (model limitation: fix with prompt, examples, or a stronger model).
4. **Check the raw context, not your assumption of it.** Half of all trace bugs are "the model never saw what I thought it saw" — truncated file, empty tool result, instruction that fell out of the window.

Instrument first: log every LLM call's full input and output to JSONL. If your logging shows only the final answer, you have print-statement debugging without the print statements.

### Use It

| Tool | Strength | Tradeoff |
|---|---|---|
| JSONL + `less` | Zero deps, works offline | No UI, manual diffing |
| LangSmith / Langfuse / Braintrust | Tree views, timing, cost per turn | SaaS, instrumentation lock-in |
| OpenTelemetry GenAI conventions | Vendor-neutral spans | Young standard, assembly required |

Whatever you choose: log full prompts, not summaries. Disk is cheap; reconstructing what the model saw is not.

### War Story

The ReAct paper (Yao et al., 2022) owed part of its impact to trace legibility: because the method interleaves explicit "Thought" strings with actions and observations, the authors could inspect *why* trajectories failed — and readers could too. A design that makes the agent's reasoning visible in the trace isn't just interpretability garnish; it's what makes the debugging protocol in this lesson possible at all.

### Checkpoint

- Why do you read a trace forward from turn 1 instead of backward from the failure?
- What is the "first divergence," and why is everything after it usually irrelevant?
- Give an example of a "model never saw it" bug and how the raw context reveals it.

## 08. Your Lab Setup: Python, a Mock LLM, and Zero API Keys

**MOTTO:** If your lesson needs an API key, your lesson has a flaky dependency and a billing page.

### The Problem

Learning agents against a live API is learning on hard mode: responses are nondeterministic, so you can't tell whether behavior changed because of your code or the sampling dice; every experiment costs money; and every reader without a key is locked out. You want to study the *loop* — and the loop doesn't care whether the brain is real.

### The Concept

This repo's philosophy: **MockLLM** — a fake model that returns deterministic, scripted responses. Think flight simulator: you don't learn instrument procedures in a real storm; you learn them where the storm is repeatable. Since an agent framework only ever sees "text in, text out," a scripted stand-in exercises 100% of the loop machinery — parsing, tool dispatch, history management, termination — with 0% of the variance.

```
  Real stack:   loop ──> [ API ──> GPU farm ──> $$$ ──> maybe same answer ]
  Lab stack:    loop ──> [ MockLLM: responses.pop(0) ]     free, offline, exact
                 ▲
                 └── the part you're actually studying
```

### Build It

The entire MockLLM:

```python
class MockLLM:
    """Returns scripted responses in order. Deterministic. Offline. Free."""
    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.calls = []                      # every prompt, recorded for inspection

    def complete(self, prompt: str) -> str:
        self.calls.append(prompt)            # so you can practice trace-reading
        if not self.responses:
            raise RuntimeError("MockLLM ran out of script — check your loop's turn count")
        return self.responses.pop(0)
```

Setup, in full: (1) Python 3.10+, (2) `git clone` this repo, (3) `python -m venv .venv` and activate, (4) `pip install -r requirements.txt` (stdlib-adjacent; no SDKs required), (5) run any lesson's script. No `.env`, no keys, no network. The `calls` list doubles as your first tracing tool: after every run, read what the "model" was actually shown — Lesson 07's habit, built in from day one.

### Use It

When you *do* graduate to real models (Phase 1 onward, optionally): the swap is one line, because MockLLM matches the `complete(prompt) -> str` interface used throughout the repo.

| Backend | Cost | Deterministic? | Use for |
|---|---|---|---|
| MockLLM | $0 | Perfectly | Loop mechanics, tests, CI |
| Local model (Ollama, llama.cpp) | $0 + your GPU/CPU | Nearly (temp 0, fixed seed) | Realistic text, still offline |
| API (Anthropic, OpenAI) | $ | No (temp 0 ≈ close, not guaranteed) | Final validation |

Keep MockLLM in your test suite forever — production agent repos mock the model in CI for exactly the reasons above.

### War Story

The stakes of "just point it at the real thing" were demonstrated in 2023 when Samsung engineers pasted confidential source code into ChatGPT while debugging, prompting the company to ban generative AI tools on corporate devices. An offline, deterministic lab isn't only pedagogy — it's the same isolation discipline that keeps real code and real credentials out of other people's clouds while you experiment.

### Checkpoint

- Why does a deterministic mock exercise 100% of the agent loop's machinery?
- What two experimental problems does nondeterminism cause when you're learning loop mechanics?
- Why should MockLLM remain in your CI even after you integrate a real model?
