# Phase 09 — 🤖 The Frameworks Tour

> Learn what they abstract, then decide if you need the abstraction.

You've built agents from raw parts, so you're now qualified to judge the frameworks that package those parts. This phase is a fair tour, not a takedown: every framework here solves a real problem for someone, and every one of them charges rent in indirection, dependencies, and churn. The goal is to be able to read any framework's docs and say "ah, that's just a while loop with checkpointing" — and then decide whether you want to maintain that while loop yourself. By the end you'll have a decision procedure, not a favorite logo.

## 01. Raw SDK First: Agents Without Frameworks

**MOTTO:** You can't evaluate an abstraction you've never lived without.

### The Problem
Most people meet agents *through* a framework, so they can't tell which behaviors come from the model, which from the loop, and which from the framework's opinions. When something breaks — and it will — they're debugging three layers they never saw assembled.

### The Concept
An agent is a while loop around a chat API: send messages, check for tool calls, execute them, append results, repeat until the model stops asking. That's it. Think of a framework as a pre-built kitchen: convenient, but you should cook on a camp stove once so you know what a stove actually does.

```
messages ──> LLM ──> tool_calls? ──yes──> run tools ──> append results ──┐
                        │no                                              │
                        └──> final answer                <───────────────┘
```

### Build It
```python
while True:
    resp = client.chat(model=MODEL, messages=messages, tools=TOOLS)
    if not resp.tool_calls:
        break
    for call in resp.tool_calls:
        result = TOOL_IMPLS[call.name](**call.arguments)
        messages.append(tool_result(call.id, result))
```
Twelve lines. Everything else in this phase is decoration on this loop.

### Use It
The raw SDKs: `openai`, `anthropic`, `google-genai`. Add `litellm` or an OpenAI-compatible endpoint if you want one call signature across providers. This is the baseline every framework must beat.

### War Story
Anthropic's "Building Effective Agents" post (December 2024) reported that the most successful agent implementations they saw used "simple, composable patterns" rather than frameworks, and explicitly advised starting with LLM APIs directly. The people selling you a harness told you to try the camp stove first.

### Checkpoint
1. What are the four steps of the minimal agent loop?
2. Which parts of an agent's behavior come from the model versus the loop code?
3. Why does building raw-SDK first make you a better framework consumer?

## 02. LangChain: The Kitchen Sink, Examined

**MOTTO:** Six hundred integrations is a feature and a liability — often in the same afternoon.

### The Problem
Real applications need loaders, splitters, vector stores, retrievers, output parsers, and model clients from a dozen vendors. Writing glue for each combination is tedious, and everyone writes the same glue slightly differently.

### The Concept
LangChain's core abstraction is the `Runnable`: anything with `invoke`/`stream`/`batch`, composable with a pipe operator (LCEL — LangChain Expression Language). It's Unix pipes for LLM components: `prompt | model | parser`. The value is the enormous integration catalog behind one interface; the cost is that a five-line API call can become a stack trace through eight layers of composed Runnables.

### Build It
```python
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

chain = ChatPromptTemplate.from_template("Summarize: {text}") | model | StrOutputParser()
chain.invoke({"text": doc})
```
Now write the same three lines with a raw SDK and compare stack traces when the model errors.

### Use It
| Strength | Weakness |
|---|---|
| Vast integration catalog (models, stores, loaders) | Deep call stacks, hard debugging |
| One interface: invoke/stream/batch everywhere | Historically fast-churning APIs |
| LangSmith tracing plugs in cleanly | Abstractions can obscure the actual prompt sent |

Best when you genuinely need many integrations. Worst as a thin wrapper over one model call.

### War Story
LangChain launched in October 2022 and became one of the fastest-growing open-source projects of 2023 — and then a lightning rod: in July 2024, dev-tools company Octomind published "Why we no longer use LangChain for building our AI agents," arguing its abstractions made simple code harder to write and change. Both the growth and the backlash were about the same thing: abstraction density.

### Checkpoint
1. What is a Runnable, and what three methods define it?
2. Name a scenario where LangChain's integration catalog clearly pays for its indirection.
3. Why do deep abstraction stacks specifically hurt *prompt* debugging?

## 03. LangGraph: Agents as State Graphs

**MOTTO:** When your agent is a loop with branches, draw the branches.

### The Problem
Linear chains can't express real agent control flow: retry this node, branch on that condition, pause for human approval, resume from a crash. Encoding that in nested callbacks is how you get unmaintainable spaghetti.

### The Concept
LangGraph models an agent as a state machine: nodes are functions that read and update a shared typed state; edges (including conditional edges) decide what runs next. Because the graph is explicit, you get checkpointing (persist state after each node), time travel (rewind to a prior state), and human-in-the-loop (interrupt at an edge) almost for free. It's a flowchart that executes.

```
        ┌──────────┐  needs_tools   ┌────────┐
START ─>│  agent   │───────────────>│ tools  │──┐
        └──────────┘                └────────┘  │
             │ done          ▲__________________│
             ▼
            END
```

### Build It
```python
graph = StateGraph(AgentState)
graph.add_node("agent", call_model)
graph.add_node("tools", run_tools)
graph.add_conditional_edges("agent", route)   # -> "tools" or END
graph.add_edge("tools", "agent")
app = graph.compile(checkpointer=MemorySaver())
```
Note: this *is* Lesson 01's while loop, reified as data. That's the whole trick.

### Use It
LangGraph (Python/JS) is the "agents got serious" tier of the LangChain ecosystem — durable execution, streaming, human approval gates. Comparable ideas: state machines in Temporal, or hand-rolled loops with a checkpoint table.

### War Story
LangChain shipped LangGraph in early 2024, partly a concession that chains were the wrong abstraction for cyclic, stateful agents — the flagship framework rebuilding its own foundation. LangChain's published case studies (Klarna's support assistant among them) lean on LangGraph plus LangSmith tracing rather than classic chains.

### Checkpoint
1. What do nodes and conditional edges correspond to in the raw agent loop?
2. What does checkpointing after every node buy you that a plain loop lacks?
3. Where exactly would you interrupt the graph for human approval?

## 04. CrewAI: Role-Playing Crews

**MOTTO:** Give each agent a job title and a to-do list, then let HR sort it out.

### The Problem
You want multiple specialized agents — a researcher, a writer, a reviewer — without hand-writing the orchestration that passes work between them.

### The Concept
CrewAI's mental model is a small company: an `Agent` has a role, goal, and backstory (all compiled into its system prompt); a `Task` has a description and expected output; a `Crew` executes tasks via a `Process` — sequential (assembly line) or hierarchical (a manager agent delegates). The analogy is literal: you're writing job descriptions, and the framework writes the meetings.

### Build It
```python
researcher = Agent(role="Researcher", goal="Find facts on {topic}", backstory="...")
writer = Agent(role="Writer", goal="Draft a brief", backstory="...")
crew = Crew(agents=[researcher, writer],
            tasks=[research_task, write_task],
            process=Process.sequential)
crew.kickoff(inputs={"topic": "GGUF quantization"})
```
Print the compiled prompts. Notice: role/goal/backstory are just system-prompt templating.

### Use It
CrewAI is fast to demo and genuinely pleasant for sequential pipelines. Tradeoffs: the role-play framing burns tokens on persona text, and fine-grained control flow means fighting the abstraction. Compare with LangGraph (explicit control, more code) before committing.

### War Story
CrewAI was created by João Moura and open-sourced in early 2024; it became one of GitHub's fastest-growing agent frameworks that year, riding the accessibility of its "agents as coworkers" metaphor. The same metaphor drew criticism from practitioners who found that backstories are decoration and the hard part — reliable task handoff — still needed engineering.

### Checkpoint
1. What do role, goal, and backstory actually compile down to?
2. When does sequential process suffice, and what does hierarchical add?
3. What's the token cost of persona-heavy prompting, and when is it worth it?

## 05. AutoGen: Conversational Multi-Agent

**MOTTO:** Everything is a conversation — even the code execution.

### The Problem
Some workflows are naturally a dialogue: a coder agent proposes code, an executor runs it, a critic reviews, and they iterate until tests pass. You need infrastructure for agents that talk *to each other*, not just to a user.

### The Concept
AutoGen (Microsoft Research) models everything as conversable agents exchanging messages. An `AssistantAgent` (LLM-backed) chats with a `UserProxyAgent` (which can execute code and stand in for a human); a `GroupChat` adds a manager that picks the next speaker. The analogy is a Slack channel with bots: the transcript *is* the shared state, and termination is "someone says TERMINATE."

### Build It
```python
assistant = AssistantAgent("coder", llm_config=cfg)
executor = UserProxyAgent("executor", code_execution_config={"work_dir": "wd"},
                          human_input_mode="NEVER")
executor.initiate_chat(assistant, message="Plot NVDA vs TSLA YTD and save png")
```
The assistant writes Python; the executor runs it and replies with output or the traceback; the loop continues until it works.

### Use It
Strong for code-generation-and-execution loops and research prototyping. Watch for: conversations that circle without converging, and speaker-selection in group chats being its own prompt-engineering problem. Sandbox the executor — Phase 3 rules apply double when the agent writes the code.

### War Story
AutoGen came out of Microsoft Research (Wu et al., 2023) and won a best-paper award at an ICLR 2024 workshop. In late 2024 the project famously forked: original creators launched AG2 to continue the classic API, while Microsoft rewrote AutoGen 0.4 (January 2025) as an event-driven, actor-model system — one codebase, two philosophies about what the abstraction should be.

### Checkpoint
1. In AutoGen, what serves as the shared state between agents?
2. Why is the UserProxyAgent's code execution a security-critical component?
3. What goes wrong with LLM-driven speaker selection in group chats?

## 06. OpenAI Agents SDK and Handoffs

**MOTTO:** Small surface, sharp edges filed down: agents, tools, handoffs, guardrails.

### The Problem
Heavy frameworks impose their worldview; raw SDKs leave you rebuilding the same loop, tracing, and multi-agent transfer logic every project. There's a market for a thin, opinionated middle.

### The Concept
The OpenAI Agents SDK has four primitives: an `Agent` (instructions + tools + model), `function_tool` (a decorated Python function), *handoffs* (an agent transfers the conversation to another agent — implemented as a tool call whose "result" is a change of ownership), and *guardrails* (validators that run alongside). A handoff is a call-center transfer: the conversation history moves; the person answering changes.

### Build It
```python
triage = Agent(name="Triage", instructions="Route to the right specialist.",
               handoffs=[billing_agent, support_agent])
result = Runner.run_sync(triage, "I was double-charged last month")
```
Under the hood, the model sees a `transfer_to_billing_agent` tool. Handoff = tool call with control-flow side effects. Demystified.

### Use It
Thin loop, built-in tracing, provider-pluggable via OpenAI-compatible APIs (though it defaults home to OpenAI — that's the gravity to price in). Compare: LangGraph is a graph you draw; Agents SDK is a relay race you staff.

### War Story
OpenAI shipped Swarm in October 2024 explicitly labeled experimental and educational — a few hundred lines demonstrating handoffs. In March 2025 they replaced it with the production Agents SDK, keeping the handoff primitive. An "educational demo" becoming the flagship abstraction six months later tells you the simple version was the right version.

### Checkpoint
1. Mechanically, what is a handoff in this SDK?
2. What's the difference between a handoff and just calling another agent as a tool?
3. What lock-in consideration comes with an SDK "defaulting home" to one provider?

## 07. Claude Agent SDK: The Harness Approach

**MOTTO:** Don't ship a loop; ship the whole workbench.

### The Problem
Even with a good loop, production agents need the boring parts: file and shell tools, permission gates, context compaction, subagent spawning, session management. Rebuilding that per project is where teams actually bleed time.

### The Concept
The Claude Agent SDK inverts the usual deal. Instead of a library you assemble, it's a *harness* — the same agent runtime that powers Claude Code, exposed programmatically. You get file editing, bash, and search tools out of the box; hooks that fire on tool events; a permission system (allow/deny/ask per tool); subagents with isolated contexts; automatic context compaction; and MCP for external tools. Think renting a fully equipped workshop versus buying a toolbox: less to build, more to accept as-is.

### Build It
```python
from claude_agent_sdk import query, ClaudeAgentOptions
opts = ClaudeAgentOptions(allowed_tools=["Read", "Grep", "Bash"],
                          permission_mode="acceptEdits", cwd="/repo")
async for msg in query(prompt="Find and fix the failing test", options=opts):
    print(msg)
```
Note what you did *not* write: no loop, no tool schemas, no executor. That's the harness trade.

### Use It
Strongest when your agent's job resembles "operate on a computer/codebase." The tradeoff is the inverse of Lesson 01: maximal leverage, minimal control over the inner loop — and it's Anthropic-models-only, the vendor-neutrality caveat to state plainly.

### War Story
Anthropic released this as the Claude Code SDK, then renamed it the Claude Agent SDK in late 2025 — an explicit signal that the coding-agent harness (loop, tools, permissions, compaction) generalizes to non-coding agents. The rename was the thesis: the harness, not the model call, is the product.

### Checkpoint
1. What does a "harness" provide that a library-style framework doesn't?
2. Which control do you give up in exchange, and when does that hurt?
3. Why do permission modes matter more in a harness with built-in bash access?

## 08. smolagents and Code-Acting Agents

**MOTTO:** Why emit JSON describing an action when you can just write the action?

### The Problem
JSON tool calling is one action per round trip. Composing tools — "search three terms, dedupe, take the top result of each" — takes many turns of expensive, error-prone back-and-forth.

### The Concept
CodeAct flips the output format: the model writes a Python snippet as its action, and the runtime executes it. Tools become plain functions the code can call, and the model gets loops, variables, and composition natively — LLMs have seen far more Python than bespoke JSON dialects. It's the difference between mailing someone one instruction at a time and handing them a script.

```
JSON agent:  think -> {"tool": "search", ...} -> result -> think -> ... (N round trips)
CodeAct:     think -> for q in queries: hits[q] = search(q)          (1 round trip)
```

### Build It
```python
from smolagents import CodeAgent, WebSearchTool, InferenceClientModel
agent = CodeAgent(tools=[WebSearchTool()], model=InferenceClientModel())
agent.run("Compare the release dates of Llama 2 and Mistral 7B")
```
Inspect the logs: the "tool call" is a code block, executed in a sandboxed interpreter.

### Use It
Hugging Face's smolagents is the flagship CodeAct library — deliberately tiny, model-agnostic (open models via HF, or any API). The catch is obvious: the agent writes arbitrary code, so sandboxing (restricted interpreter, E2B/Docker) is not optional. Phase 3 was the rehearsal for this.

### War Story
The CodeAct paper ("Executable Code Actions Elicit Better LLM Agents," Wang et al., 2024) reported up to ~20% higher success rates for code actions over JSON/text actions across agent benchmarks. Hugging Face released smolagents around the end of 2024, advertising that its core agent logic fits in roughly a thousand lines of code — a pointed contrast in a field of heavyweight frameworks.

### Checkpoint
1. Why does code-as-action reduce round trips versus JSON tool calls?
2. Why are LLMs often *better* at emitting Python than custom JSON schemas?
3. What security requirement does CodeAct make absolutely mandatory?

## 09. Pydantic AI: Types as Guardrails

**MOTTO:** If the output doesn't parse, the run didn't happen.

### The Problem
Agents return strings; your program needs structs. Validating LLM output by hand — and deciding what to do when it's malformed — is repetitive, and most frameworks bolt it on as an afterthought.

### The Concept
Pydantic AI makes the type the contract: you declare an `output_type` (a Pydantic model), and the framework validates every response against it — and here's the good part — feeds validation errors *back to the model* for a retry. It's FastAPI's trick applied to agents: the schema isn't documentation, it's enforcement. Dependency injection (`deps_type`) gives tools typed access to your DB connections and config instead of globals.

### Build It
```python
class Verdict(BaseModel):
    approved: bool
    risk_score: float = Field(ge=0, le=1)
    reasons: list[str]

agent = Agent("openai:gpt-4o", output_type=Verdict, deps_type=Database)
result = agent.run_sync("Assess invoice INV-3021", deps=db)
result.output.risk_score  # a float, guaranteed, or the run raised
```
Malformed output triggers an automatic retry with the validation error in context.

### Use It
Model-agnostic (OpenAI, Anthropic, Gemini, local via OpenAI-compatible endpoints). Best fit: agents embedded in typed production codebases where "probably JSON" is not an acceptable return type. Pairs naturally with the structured-output techniques from Phase 10, Lesson 08.

### War Story
Pydantic AI was announced in December 2024 by the Pydantic team itself (Samuel Colvin) — notable because Pydantic is already a dependency of essentially every framework in this phase, including the OpenAI SDK and LangChain. The validation layer everyone was using decided to come upstairs and run the show.

### Checkpoint
1. What happens in Pydantic AI when the model's output fails validation?
2. Why is dependency injection preferable to globals for tool implementations?
3. How does "types as contract" change how you write evals for an agent?

## 10. Orchestration vs Library vs Platform

**MOTTO:** Know whether you're buying a hammer, a scaffold, or a landlord.

### The Problem
"Framework" hides three different products with different costs. Teams compare LangGraph to Pydantic AI to LangSmith as if they were peers; they aren't, and category confusion is how you end up owning infrastructure you meant to rent.

### The Concept
Three tiers, by what they want to own:

```
Library        ->  owns some FUNCTIONS   (you call it)        e.g. Pydantic AI, smolagents
Orchestrator   ->  owns the CONTROL FLOW (it calls you)       e.g. LangGraph, AutoGen, Temporal-style runtimes
Platform       ->  owns the RUNTIME/DATA (you deploy into it) e.g. LangSmith/LangGraph Platform, Bedrock Agents, hosted assistant APIs
```
The rent rises as you go down: libraries cost an import, orchestrators cost your architecture, platforms cost your deployment story and observability data. Inversion of control is the dividing line — who calls whom.

### Build It
Audit any framework in one sitting: (1) Where does the main loop live — your file or theirs? (2) Where does state persist — your DB or their service? (3) Can you run it offline in a plain test? Score each 0–2 toward "library." Do this for two frameworks from this phase and compare totals.

### Use It
| Question | Library | Orchestrator | Platform |
|---|---|---|---|
| Who owns the loop? | You | It | It |
| Where's the state? | Yours | Configurable | Theirs |
| Exit cost | Low | Medium | High |

### War Story
LangChain's own v0.1 restructuring (January 2024) split the monolith into `langchain-core` and per-integration packages precisely because users wanted library-sized dependencies, not framework-sized ones — a public admission that one package had been straddling all three tiers at once.

### Checkpoint
1. What does "inversion of control" mean, and which tier introduces it?
2. Why does the platform tier have the highest exit cost specifically?
3. Run the three-question audit on any framework you use today — what tier is it?

## 11. Framework Lock-In and Escape Hatches

**MOTTO:** The best time to plan your exit is before you move in.

### The Problem
Frameworks accumulate around your code: their message format in your DB, their trace format in your dashboards, their prompt templates in your git history. When the framework churns — or you outgrow it — migration cost is proportional to how deep those formats sank.

### The Concept
Lock-in isn't binary; it's a set of surfaces, each with an escape hatch:

```
Surface              Escape hatch
──────────────────   ─────────────────────────────────────────
Message format       Store a neutral transcript (role/content/tool_call) you own
Model client         OpenAI-compatible APIs / litellm as lingua franca
Prompts              Keep prompts as versioned text files, not framework objects
Traces               Emit OpenTelemetry, not vendor-only formats
Tools                Plain functions + JSON schema; adapt at the edge
```
The pattern is hexagonal architecture: your domain (prompts, tools, transcripts) in the middle; the framework as a replaceable adapter at the boundary.

### Build It
Write `to_neutral(framework_msgs) -> list[dict]` and `from_neutral(...)` for one framework you use. Persist only neutral transcripts. Now swap the framework in a test and replay a stored conversation through the new one. If that works, you're renting; if not, you're owned.

### Use It
Practical anchors: OpenAI-compatible endpoints (served by vLLM, Ollama, most providers) as the portability layer for model calls; MCP for portable tool servers; OpenTelemetry GenAI conventions for traces.

### War Story
OpenAI announced in March 2025 that the Assistants API would be deprecated in favor of the new Responses API, with a migration window into 2026. Teams that had persisted OpenAI-hosted threads and assistant objects as their source of truth got a live-fire migration drill; teams that kept neutral transcripts changed an adapter.

### Checkpoint
1. Name the five lock-in surfaces and one escape hatch for each.
2. Why is the *stored message format* the highest-stakes surface?
3. What does the replay test prove about your architecture?

## 12. When to Use No Framework at All

**MOTTO:** The framework you don't adopt never breaks in production.

### The Problem
After eleven lessons of frameworks, the honest question: your agent is a loop, three tools, and a system prompt. Is a dependency with weekly releases and eight abstraction layers actually buying anything?

### The Concept
A decision procedure, not a vibe:

```
Need durable state / human gates / complex branching? ──> orchestrator (or DIY + a DB table)
Need many vendor integrations fast?                   ──> integration-heavy framework
Need typed outputs in a typed codebase?               ──> thin library (or 30 lines of retry logic)
Need "operate a computer" out of the box?             ──> a harness
None of the above?                                    ──> raw SDK. Stop. You're done.
```
The null hypothesis is Lesson 01's loop. A framework must reject the null with evidence: features you'd otherwise build *and maintain*, minus the cost of churn, debugging depth, and lock-in from Lesson 11.

### Build It
Take one agent you built this phase with a framework and port it to a raw SDK. Count: lines added, dependencies removed, and — the honest metric — which version you can fully explain to a colleague in five minutes.

### Use It
Rules of thumb: prototypes and single-agent tools rarely justify a framework; long-running, resumable, multi-actor systems often do; and everything in between deserves the audit from Lesson 10 plus the escape hatches from Lesson 11 *before* adoption, not after.

### War Story
The strongest no-framework argument came from framework vendors themselves: Anthropic's December 2024 "Building Effective Agents" post found the most successful implementations used simple composable patterns over frameworks, and OpenAI's Swarm shipped as a deliberately tiny teaching artifact before graduating to an SDK. The people with the most agent traffic keep rediscovering the while loop.

### Checkpoint
1. What is the "null hypothesis" a framework must beat, and with what evidence?
2. Which two workload properties most strongly justify an orchestrator?
3. For your current project: which branch of the decision tree applies, and why?
