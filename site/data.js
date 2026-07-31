// AI Agents From Scratch — canonical curriculum data
// 20 phases · 212 lessons
const CURRICULUM = [
  {
    id: 0, slug: "00-setup-and-mental-models", emoji: "🧠", name: "Setup & Mental Models",
    tagline: "An agent is a loop with a brain. Learn the loop before the brain.",
    lessons: [
      "What is an agent (and what is just a chatbot with vibes)",
      "Agent vs workflow vs pipeline: the autonomy spectrum",
      "The agent loop: observe, think, act, repeat",
      "Environments, tools, memory: the agent's world",
      "Why agents fail: a taxonomy of face-plants",
      "The evaluation mindset: never trust a demo",
      "Reading agent traces like a debugger",
      "Your lab setup: Python, a mock LLM, and zero API keys"
    ]
  },
  {
    id: 1, slug: "01-llm-foundations", emoji: "🗣️", name: "LLM Foundations for Agents",
    tagline: "Know your engine before you build the car.",
    lessons: [
      "Tokens, context windows, and why size matters",
      "Sampling: temperature, top-p, and determinism",
      "System prompts: the agent's constitution",
      "Prompt engineering that actually transfers",
      "Few-shot examples: teaching by showing",
      "Chain-of-thought: making the model show its work",
      "Structured output and JSON mode",
      "Function calling: the API that changed everything",
      "Context engineering: what goes in the window",
      "Prompt caching: the 10x cost lever",
      "Model selection: frontier vs small vs open",
      "Cost and latency budgets for agents"
    ]
  },
  {
    id: 2, slug: "02-the-agent-loop", emoji: "🔄", name: "The Agent Loop",
    tagline: "Every agent framework is 100 lines of while-loop wearing a trench coat.",
    lessons: [
      "ReAct: reason, act, observe",
      "The scratchpad: an agent's working memory",
      "Stop conditions: knowing when to quit",
      "Error handling inside the loop",
      "Reflection: the agent that critiques itself",
      "Self-consistency: ask three times, take the vote",
      "Turn budgets and runaway loops",
      "Streaming and interruptibility",
      "Human-in-the-loop gates",
      "Build a complete agent loop in 100 lines"
    ]
  },
  {
    id: 3, slug: "03-tools-and-function-calling", emoji: "🔧", name: "Tools & Function Calling",
    tagline: "A model that can only talk is a consultant. Give it hands.",
    lessons: [
      "Tool schemas: describing functions to a model",
      "Tool choice: auto, required, forced, none",
      "Parallel tool calls",
      "Tool errors: retry, explain, or give up",
      "Sandboxing code execution",
      "Search tools: web, docs, and grep",
      "File tools: read, write, edit safely",
      "Browser and HTTP tools",
      "The tool router: dispatch without spaghetti",
      "Dynamic tool loading and tool search",
      "Designing tools agents actually use well",
      "Build a tool-using agent from scratch"
    ]
  },
  {
    id: 4, slug: "04-memory", emoji: "📚", name: "Memory",
    tagline: "Goldfish agents ask the same question twice. Give yours a hippocampus.",
    lessons: [
      "Short-term vs long-term memory",
      "Conversation buffers and windowing",
      "Summarization memory: compress or die",
      "Vector memory: remember by similarity",
      "Episodic vs semantic memory",
      "Entity memory: tracking people, places, things",
      "The write policy: what's worth remembering",
      "Memory retrieval: when to recall what",
      "Forgetting: decay, eviction, and contradictions",
      "Build a memory system from scratch"
    ]
  },
  {
    id: 5, slug: "05-rag-for-agents", emoji: "🔍", name: "RAG for Agents",
    tagline: "The model knows nothing about your data. Fix that at query time.",
    lessons: [
      "Why RAG: grounding beats fine-tuning for facts",
      "Chunking strategies: size, overlap, structure",
      "Embeddings: meaning as geometry",
      "Vector databases and ANN search",
      "Hybrid search: dense + sparse (BM25)",
      "Reranking: the second-stage filter",
      "Query rewriting and decomposition",
      "Agentic RAG: retrieval as a tool decision",
      "GraphRAG and structured knowledge",
      "Citations and faithfulness",
      "RAG evaluation: retrieval and generation metrics",
      "Build a RAG pipeline from scratch"
    ]
  },
  {
    id: 6, slug: "06-planning-and-reasoning", emoji: "🗂️", name: "Planning & Reasoning",
    tagline: "Amateurs improvise. Agents that ship make plans — then revise them.",
    lessons: [
      "Task decomposition: big goals into small steps",
      "Plan-and-execute vs ReAct: when to plan ahead",
      "Tree of Thoughts: exploring alternatives",
      "Search over reasoning: beams and MCTS-lite",
      "Replanning: when step 3 destroys the plan",
      "Hierarchical planning: managers and workers",
      "Verification loops: check before you claim",
      "Reasoning models: o-series, R1, and extended thinking",
      "Inference-time compute: pay more, think harder",
      "Task lists and progress tracking",
      "Long-horizon coherence: not losing the plot",
      "Build a planning agent from scratch"
    ]
  },
  {
    id: 7, slug: "07-structured-control", emoji: "🧩", name: "Structured Outputs & Control",
    tagline: "Free text is for poems. Systems need schemas.",
    lessons: [
      "JSON Schema enforcement and constrained decoding",
      "Validation and repair loops",
      "State machines for agent control flow",
      "Grammars and regex-constrained generation",
      "LLM-as-judge: grading with models",
      "Guardrail layers: pre, mid, and post",
      "Routing: classify then dispatch",
      "Confidence and abstention: teaching 'I don't know'",
      "Deterministic scaffolds around stochastic cores",
      "Build a structured-output engine from scratch"
    ]
  },
  {
    id: 8, slug: "08-protocols", emoji: "🌐", name: "Protocols: MCP & Friends",
    tagline: "Tools were bespoke. Then MCP made them USB.",
    lessons: [
      "Why protocols: the N×M integration problem",
      "MCP architecture: hosts, clients, servers",
      "MCP tools, resources, and prompts",
      "Building an MCP server",
      "MCP transports: stdio, HTTP, SSE",
      "MCP security: the confused deputy and beyond",
      "A2A: agent-to-agent communication",
      "Function-calling dialects: OpenAI vs Anthropic vs Gemini",
      "OpenAPI as a tool source",
      "Computer use: screenshots and clicks as a protocol",
      "Skills and slash commands: packaged capabilities",
      "Build an MCP server from scratch"
    ]
  },
  {
    id: 9, slug: "09-frameworks", emoji: "🤖", name: "The Frameworks Tour",
    tagline: "Learn what they abstract, then decide if you need the abstraction.",
    lessons: [
      "Raw SDK first: agents without frameworks",
      "LangChain: the kitchen sink, examined",
      "LangGraph: agents as state graphs",
      "CrewAI: role-playing crews",
      "AutoGen: conversational multi-agent",
      "OpenAI Agents SDK and handoffs",
      "Claude Agent SDK: the harness approach",
      "smolagents and code-acting agents",
      "Pydantic AI: types as guardrails",
      "Orchestration vs library vs platform",
      "Framework lock-in and escape hatches",
      "When to use no framework at all"
    ]
  },
  {
    id: 10, slug: "10-open-models", emoji: "🦙", name: "Open Models & Local Agents",
    tagline: "Your agent, your weights, your GPU, your rules.",
    lessons: [
      "The open-model landscape: Llama, Qwen, Mistral, Hermes",
      "Hermes and open tool-calling formats",
      "Serving: Ollama, vLLM, llama.cpp",
      "Quantization: fitting brains in small boxes",
      "Local agent stacks end to end",
      "Fine-tuning for tool use",
      "Distillation: teaching small models agent tricks",
      "Structured output on open models",
      "Privacy and on-prem agent deployments",
      "Build a local agent with an open model"
    ]
  },
  {
    id: 11, slug: "11-multi-agent-fundamentals", emoji: "👥", name: "Multi-Agent Fundamentals",
    tagline: "One agent is a worker. Many agents are an organization — with org problems.",
    lessons: [
      "Why multi-agent: parallelism, specialization, context isolation",
      "When multi-agent is worse: the coordination tax",
      "Orchestrator-worker: the boss pattern",
      "Handoffs: passing the conversation",
      "Routing: the right agent for the job",
      "Shared state and blackboards",
      "Message passing between agents",
      "Sub-agent context: what to tell the intern",
      "Result synthesis: merging parallel work",
      "Debate and critique: adversarial collaboration",
      "Delegation depth: agents spawning agents",
      "Build an orchestrator-worker system from scratch"
    ]
  },
  {
    id: 12, slug: "12-swarms-and-patterns", emoji: "🐝", name: "Swarms & Advanced Patterns",
    tagline: "No one ant knows the plan. The colony still builds the bridge.",
    lessons: [
      "Swarm intelligence: emergence from simple rules",
      "Hierarchies: teams of teams",
      "Market mechanisms: auctions for task allocation",
      "Consensus among agents: voting and quorums",
      "Specialist pools and dynamic team formation",
      "Long-running agent societies and simulations",
      "Generative agents: the Smallville experiment",
      "Stigmergy: coordination through the environment",
      "Failure containment in agent groups",
      "Build a swarm simulation from scratch"
    ]
  },
  {
    id: 13, slug: "13-autonomous-agents", emoji: "🖥️", name: "Autonomous & Computer-Use Agents",
    tagline: "The agent has your keyboard now. Choose what it's allowed to press.",
    lessons: [
      "Coding agents: from Copilot to SWE-agent",
      "The edit-test-fix loop",
      "Browser agents: DOM, screenshots, actions",
      "Computer use: pixels in, clicks out",
      "Long-horizon autonomy: hours, not turns",
      "Checkpointing and resumability",
      "Permission models: what needs a human",
      "Environment design: making the world agent-friendly",
      "Background agents and fleets",
      "Build a mini coding agent from scratch"
    ]
  },
  {
    id: 14, slug: "14-evaluation", emoji: "📊", name: "Evaluation & Benchmarks",
    tagline: "If you can't measure your agent, you're shipping a mood.",
    lessons: [
      "Evals from scratch: task, rubric, grader",
      "Trajectory evaluation: grading the journey",
      "LLM-as-judge: powers and pitfalls",
      "Benchmarks: SWE-bench, GAIA, WebArena, tau-bench",
      "Building a regression suite for agents",
      "Non-determinism: pass@k and variance",
      "Online evals: A/B tests and user signals",
      "Error analysis: reading failed trajectories",
      "Capability vs reliability: the nines problem",
      "Build an eval harness from scratch"
    ]
  },
  {
    id: 15, slug: "15-safety-and-security", emoji: "🛡️", name: "Safety & Security",
    tagline: "Every tool you give an agent, you also give the attacker in its context.",
    lessons: [
      "The agent threat model",
      "Prompt injection: direct and indirect",
      "Defending against injection: layers, not silver bullets",
      "The lethal trifecta: private data, untrusted input, exfiltration",
      "Tool permissioning and least privilege",
      "Sandboxing: containers, VMs, and blast radius",
      "Jailbreaks and refusal robustness",
      "Data exfiltration channels",
      "Alignment basics for agent builders",
      "Auditing and kill switches"
    ]
  },
  {
    id: 16, slug: "16-production", emoji: "🏭", name: "Production Agents",
    tagline: "The demo took a day. The last 20% takes the quarter.",
    lessons: [
      "Agent observability: traces, spans, replays",
      "Cost controls: budgets, caps, and alerts",
      "Latency engineering: streaming, parallelism, caching",
      "Retries and idempotent tool design",
      "State persistence and session management",
      "Prompt versioning and regression gates",
      "Deployment patterns: sync, async, background",
      "Rate limits and provider failover",
      "The agent ops runbook",
      "Multi-tenancy and isolation",
      "Feedback loops: learning from production",
      "The production readiness checklist"
    ]
  },
  {
    id: 17, slug: "17-advanced-topics", emoji: "🧪", name: "Advanced Topics",
    tagline: "Where research papers become next year's baseline.",
    lessons: [
      "Fine-tuning agents: SFT on trajectories",
      "RL for agents: from RLHF to GRPO",
      "Self-improvement: agents that write their own tools",
      "Memory consolidation and sleep-time compute",
      "World models and simulation-based planning",
      "Voice agents: latency, barge-in, and duplex",
      "Embodied agents and robotics-lite",
      "Test-time learning and in-context adaptation",
      "Agent economies and machine payments",
      "The research frontier: what to read next"
    ]
  },
  {
    id: 18, slug: "18-case-studies", emoji: "🏗️", name: "Case Studies — Design Real Agents",
    tagline: "Whiteboard the agents people actually pay for.",
    lessons: [
      "Design a coding agent (Claude Code-lite)",
      "Design a deep-research agent",
      "Design a customer-support agent",
      "Design a data-analyst agent",
      "Design a browser QA agent",
      "Design a personal assistant with memory",
      "Design an email triage agent",
      "Design a document-processing pipeline agent",
      "Design a sales/CRM agent",
      "Design a multi-agent content studio"
    ]
  },
  {
    id: 19, slug: "19-capstones", emoji: "🏆", name: "Capstone Projects",
    tagline: "Stop reading about agents. Ship one. Then ship a team of them.",
    lessons: [
      "Capstone: your own agent framework in 500 lines",
      "Capstone: a coding agent that passes its own tests",
      "Capstone: a deep-research agent with citations",
      "Capstone: an MCP server suite",
      "Capstone: a local agent on an open model",
      "Capstone: a multi-agent research team",
      "Capstone: an eval harness with a leaderboard",
      "Capstone: the grand agent (your design, defended)"
    ]
  }
];

const STATS = {
  lessons: CURRICULUM.reduce((n, p) => n + p.lessons.length, 0),
  phases: CURRICULUM.length,
  codeExamples: 12,
  projects: 6,
  hours: 200
};
