# Phase 17 — 🧪 Advanced Topics

> Where research papers become next year's baseline.

Everything so far has been engineering with a fixed model: prompt it, tool it, orchestrate it. This phase changes the model itself, the agent's relationship with time, and even the economy it operates in. Some of this is production-ready today; some is six months from it; all of it is worth understanding now, because "advanced" in this field has a half-life of about a year.

---

## 01. Fine-Tuning Agents: SFT on Trajectories

**MOTTO:** Stop prompting the behavior in. Train it in.

### The Problem
Your system prompt is 4,000 tokens of "always check before writing", "use the search tool first", "format like this" — and the model still forgets under pressure. You're paying for those tokens on every call, and the behavior is still probabilistic.

### The Concept
Supervised fine-tuning (SFT) on **trajectories**: instead of (question, answer) pairs, train on full agent runs — system state, tool calls, tool results, reasoning, final action — so the model *learns the loop*, not just the answers. Like moving from giving a new hire a laminated instruction card to actually training them on recorded expert sessions. Your traces from Phase 16 are the raw material: filter to successful runs, clean them, and they're a dataset.

### Build It
- Export successful traces (high feedback scores, task completed, no retries) into the provider's chat format with tool-call turns intact.
- Curate hard: dedupe near-identical trajectories, remove lucky successes (right answer, wrong process), balance across task types. 500 excellent beats 50,000 mediocre.
- Fine-tune a small model (7–8B class) with LoRA; evaluate on your Phase 9 harness against the prompted baseline — same tasks, measure success rate, token cost, and how much system prompt you can now delete.

### Use It
| Tool | Role |
|---|---|
| Unsloth / Axolotl / LLaMA-Factory | Open-model SFT + LoRA |
| Hugging Face TRL | `SFTTrainer`, chat/tool templates |
| OpenAI fine-tuning API | Hosted SFT incl. function-calling formats |
| Together / Fireworks | Hosted tuning of open models |

### War Story
Alongside DeepSeek-R1 (January 2025), DeepSeek released distilled models: they generated ~800k reasoning-heavy training samples with R1 and ran plain SFT — no RL at all — on Qwen and Llama bases from 1.5B to 70B. The distilled 14B model outperformed much larger open baselines on reasoning benchmarks. The headline was the RL; the sleeper result was how far pure SFT on good trajectories goes when the trajectories are good enough.

### Checkpoint
1. Why train on full trajectories rather than (input, final answer) pairs for an agent?
2. What makes a "lucky success" trace poisonous in a training set?
3. What did you have to build in Phases 9 and 16 before fine-tuning was even possible?

---

## 02. RL for Agents: From RLHF to GRPO

**MOTTO:** SFT copies the demonstrator. RL surpasses it.

### The Problem
SFT caps you at the quality of your demonstrations. If no trace in your dataset solves the hard case, the fine-tuned model won't either. You want the model to *discover* better strategies — which means rewarding outcomes, not imitating steps.

### The Concept
RLHF's classic pipeline (SFT → reward model → PPO) is heavy: PPO needs a separate value network and careful tuning. **GRPO** (Group Relative Policy Optimization, from DeepSeekMath) simplifies it: sample a *group* of responses per prompt, score them, and use each response's advantage relative to the group mean as the training signal — no value model at all. For agents, the key enabler is **verifiable reward**: code passes tests, math checks out, task provably completed. Where a checker exists, you don't need a learned reward model — and reward hacking gets much harder.

```
prompt ─▶ sample G responses ─▶ score each ─▶ advantage = (score − group mean)
                                                 └─▶ push up above-avg, push down below-avg
```

### Build It
- Pick a task with a programmatic checker (e.g., your agent's SQL tasks: does the query run and return the fixture answer?).
- Wire GRPO with TRL's `GRPOTrainer` or the `verifiers` ecosystem on a small model: reward = task check + format check (penalize malformed tool calls).
- Watch for reward hacking — inspect trajectories, not just curves. If reward climbs while transcripts get weird, your checker has a loophole.

### Use It
TRL (`GRPOTrainer`), veRL, OpenRLHF, `verifiers`/prime-rl for RL environments over tool-using tasks.

### War Story
DeepSeek-R1 (January 2025) showed pure RL with GRPO and verifiable rewards — no SFT stage at all for R1-Zero — teaching a base model to reason: response lengths grew as it learned to think longer, and mid-training the model exhibited what the paper called an "aha moment," spontaneously re-examining its own work. R1-Zero's transcripts were messy (language mixing, poor readability), so the released R1 added a small SFT "cold start" before RL. The one-two punch — a little SFT for form, RL against verifiable rewards for capability — is now the standard recipe.

### Checkpoint
1. What does GRPO remove from the PPO pipeline, and what makes that removal work?
2. Why do verifiable rewards suit agent tasks better than learned reward models?
3. Reward is climbing but spot-checked trajectories look degenerate. What happened and what do you fix?

---

## 03. Self-Improvement: Agents That Write Their Own Tools

**MOTTO:** The best tool for the job is the one the agent wrote last Tuesday.

### The Problem
You hand-author every tool. Each new task type means a developer writing a function, a schema, tests. The agent's capabilities are capped by your backlog.

### The Concept
Let the agent close the loop: encounter a task → write code to solve it → verify it works → **store the verified code as a named, reusable skill** → retrieve it next time. The skill library becomes compound interest: complex skills compose simpler ones, and capability curves bend upward. Like a craftsman's jig wall — every tricky job leaves behind a jig that makes the next one faster. The critical ingredient is verification: only code that provably worked gets promoted, or the library fills with confident garbage.

### Build It
- Add three meta-tools to your agent: `write_skill(name, code)`, `test_skill(name)` (runs in a sandbox against the current task), `search_skills(query)` (embedding retrieval over skill descriptions).
- Promotion rule: a skill enters the library only after passing execution in the sandbox; store code + docstring + example call.
- Run it on a task family (e.g., CSV wrangling challenges) and chart tasks-solved-per-hour over time. Flat means your retrieval or verification is broken; rising means the flywheel is turning.

### Use It
Sandboxed execution (Docker, E2B, Modal) is non-negotiable; embedding store for skill retrieval; your Phase 9 evals to measure whether the library actually helps.

### War Story
Voyager (Wang et al., May 2023) put a GPT-4 agent in Minecraft with exactly this loop: an automatic curriculum proposed goals, the agent wrote JavaScript skills against the Mineflayer API, verified them in-game, and banked them in a skill library. Results vs. prior methods: 3.3× more unique items discovered, 2.3× longer travel distances, and key tech-tree milestones unlocked up to 15.3× faster — it was the only method to reach diamond tools. The skill library even transferred to a fresh world. It remains the cleanest demonstration that verified self-written tools compound.

### Checkpoint
1. Why is verification-before-promotion the load-bearing step in a skill library?
2. How does skill composition change the shape of the capability curve?
3. What are the security implications of executing agent-written code, and how does your sandbox address them?

---

## 04. Memory Consolidation and Sleep-Time Compute

**MOTTO:** Thinking is too important to do only while the user waits.

### The Problem
Your agent's memory (Phase on memory) is an append-only junk drawer: raw conversation chunks, redundant facts, stale preferences. Retrieval gets noisier as it grows. And every second of "thinking" happens on the user's clock.

### The Concept
Biological memory doesn't just record — it consolidates offline. Do the same: schedule **sleep-time compute**, background jobs where the agent processes its own memory with no user waiting: deduplicate and merge facts, resolve contradictions (keep the newer preference), promote episodic details into semantic summaries ("user prefers concise answers" from 30 examples), pre-compute likely-useful context for tomorrow. The user-facing agent then starts each session with a curated brief instead of a haystack.

```
awake:  user ⇄ agent ──writes──▶ raw memory
asleep: consolidator agent: dedupe → resolve → summarize → index → brief
```

### Build It
- Nightly job: load a user's raw memory entries; an LLM pass clusters, merges duplicates, flags contradictions, and emits a structured profile + episodic summaries. Keep raw entries archived (never destroy the source of truth).
- Add provenance: every consolidated fact links back to the raw entries that support it, so bad consolidations are debuggable.
- Measure it: retrieval precision on a probe set, and time-to-first-useful-token in fresh sessions, before vs. after consolidation.

### Use It
Letta (nee MemGPT — sleep-time agents are a first-class feature), Mem0, Zep (temporal knowledge graph memory), or a cron job + your own memory store.

### War Story
The "Sleep-time Compute" paper (Lin et al., April 2025, from the Letta/UC Berkeley group) formalized the idea: let a model process context offline, before queries arrive, producing a distilled representation. On their reasoning benchmarks, sleep-time compute reduced the test-time compute needed to reach a given accuracy by roughly 5×, and amortized well when multiple questions hit the same context. The economics are the point: offline tokens are batchable, cacheable, and off the latency path.

### Checkpoint
1. Why keep raw memory archived after consolidation instead of replacing it?
2. Which memory operations belong offline vs. must happen in-session?
3. How would you detect that a consolidation run made things worse?

---

## 05. World Models and Simulation-Based Planning

**MOTTO:** Rehearse where mistakes are free; act where they aren't.

### The Problem
Your agent learns by acting in the real environment — where actions are slow, cost money, and can't be undone. Ten thousand practice runs against a production CRM is not a plan.

### The Concept
A **world model** predicts what the environment will do next given a state and an action. With one, an agent can plan by *simulation*: imagine candidate action sequences, score predicted outcomes, act out only the winner. This is model-based planning (the family behind MuZero's learned-model search). For software agents you rarely need a neural world model — a **staged replica** (seeded database, mocked APIs, recorded website) is a perfectly good world model with 100% fidelity on the parts you copied. The frontier is *learned* world models for environments too rich to replicate.

```
real env:   act ──────────────▶ consequence (slow, costly, irreversible)
world model: propose → simulate → score → pick best ──▶ act once, for real
```

### Build It
- Build a simulator for one of your agent's environments: e.g., a fixture e-commerce API with deterministic inventory and orders. Cover the effectful operations especially.
- Add a `simulate: bool` flag to your tool layer; a planning wrapper runs K candidate plans in simulation, scores terminal states, executes the best plan live.
- Track sim-to-real gap: log every case where the live outcome diverged from the simulated prediction; that list is your simulator's backlog.

### Use It
WebArena / BrowserGym (simulated web environments for browser agents), gym-style custom environments, Docker-composed staging stacks, and record-replay proxies (VCR-style) for third-party APIs.

### War Story
DeepMind's Genie 2 (December 2024) is a foundation world model that generates playable, action-controllable 3D environments from a single prompt image — and DeepMind explicitly positioned it as a way to create unlimited training and evaluation environments for embodied agents, demonstrating their SIMA agent following instructions inside worlds Genie 2 dreamed up. The provocative idea: when environments are the bottleneck for agent training, generate the environments too.

### Checkpoint
1. Why is a staged replica "a world model" in the useful sense, and where does it stop being one?
2. What is the sim-to-real gap and why must you measure it rather than assume it?
3. When does simulation-based planning justify its extra inference cost?

---

## 06. Voice Agents: Latency, Barge-In, and Duplex

**MOTTO:** In voice, 500 milliseconds is an awkward silence.

### The Problem
Text users tolerate a two-second pause; a phone caller hears two seconds of silence and says "hello?…" Voice also breaks turn-taking: humans interrupt, backchannel ("mm-hm"), and talk over each other. A half-duplex request/response agent sounds like a phone tree.

### The Concept
Voice agents live or die on three things. **Latency budget**: the pipeline (ASR → LLM → TTS) must land under ~800 ms voice-to-voice, so you stream every stage and start TTS on the first sentence, not the full reply. **Barge-in**: detect user speech during agent playback, stop the audio instantly, and — harder — cancel the in-flight generation and reconcile state ("I said half of that sentence"). **Duplex**: full-duplex systems listen while speaking; speech-to-speech models collapse the pipeline entirely, cutting latency and keeping prosody, at the cost of less control and harder tool integration.

```
pipeline:  mic → VAD → ASR ──stream──▶ LLM ──first sentence──▶ TTS → speaker
                 └── barge-in: user speaks → kill playback + cancel LLM
```

### Build It
- Assemble a pipeline agent: streaming ASR (Deepgram or Whisper-streaming) → your agent loop → streaming TTS (Cartesia/ElevenLabs). Measure voice-to-voice p95 latency; itemize where the milliseconds go.
- Implement barge-in: VAD monitors during playback; on speech, stop TTS, abort the LLM stream, and truncate the assistant turn in history to what was actually spoken.
- Handle tool calls that take seconds: generate a spoken filler ("let me check that…") while the tool runs — dead air is a bug.

### Use It
| Tool | Role |
|---|---|
| OpenAI Realtime API | Hosted speech-to-speech with tool calls |
| Pipecat / LiveKit Agents | OSS voice-agent orchestration frameworks |
| Deepgram / Whisper | Streaming ASR |
| Cartesia / ElevenLabs | Low-latency streaming TTS |
| Vapi / Retell | Managed voice-agent platforms + telephony |

### War Story
OpenAI's numbers for ChatGPT voice tell the whole story: the pre-2024 pipeline averaged 2.8 s (GPT-3.5) to 5.4 s (GPT-4) per response because audio→text→LLM→text→audio crossed three models, losing tone and interruptibility along the way. GPT-4o's single natively-audio model brought average response time to ~320 ms, and the subsequent Realtime API (late 2024) exposed the same trick to developers — server-side VAD, barge-in support, and function calling over a WebSocket. The capability that made voice agents viable wasn't smarter; it was faster.

### Checkpoint
1. Where does each chunk of latency come from in a pipeline voice agent, and which stage benefits most from streaming?
2. What state reconciliation does barge-in require beyond stopping audio?
3. What do you give up when moving from a pipeline to a speech-to-speech model?

---

## 07. Embodied Agents and Robotics-Lite

**MOTTO:** The physical world doesn't have a retry button.

### The Problem
Everything in this course acts through APIs, where actions are cheap, fast, and mostly reversible. A robot arm is none of those. What survives the jump from tokens to torque — and what breaks?

### The Concept
The modern bridge is the **vision-language-action (VLA)** model: take a vision-language model pretrained on the internet, then fine-tune it to output robot actions as tokens — perception, language understanding, and control in one policy. Around it sits a familiar shape: a slow deliberate planner (the LLM/VLA, ~1 Hz thinking) and a fast reactive controller (~100 Hz reflexes) — exactly your agent loop, except tool calls take seconds, feedback is noisy sensors, and "undo" doesn't exist. Safety moves from prompt-injection defense to workspace limits, force caps, and e-stops.

### Build It
No robot required for the concepts:
- In MuJoCo (or any physics sim), wire an LLM planner that decomposes "put the block in the bowl" into primitive calls (`move_to(x,y,z)`, `grip()`, `release()`) executed by a scripted controller. Note the failure classes: the plan was right but the grasp slipped — a category APIs never gave you.
- Add perception noise (jittered object positions) and watch pure open-loop plans fail; add a re-observe-and-replan step and watch closed-loop recover. That loop *is* embodiment in miniature.
- Optional hardware: Hugging Face's LeRobot + an SO-100 arm kit (~$100-class) runs imitation-learning policies on real hardware.

### Use It
LeRobot (HF's OSS robotics stack), MuJoCo / Isaac Sim (simulation), OpenVLA (open 7B VLA model), ROS 2 for real integration.

### War Story
Google DeepMind's RT-2 (July 2023) demonstrated the VLA thesis: co-fine-tuning a vision-language model on web data plus robot trajectories, emitting actions as text tokens, roughly doubled success on unseen objects and instructions versus the robotics-data-only predecessor RT-1 — including semantic leaps like picking the improvised hammer (a rock) or choosing a drink for a tired person, behaviors present nowhere in the robot data. Internet-scale pretraining transferred to the physical world; the paper marks the moment robotics and LLM agents became one field with two speeds.

### Checkpoint
1. Which parts of your software agent loop survive contact with hardware, and which assumptions break?
2. Why do embodied stacks split into slow planners and fast controllers?
3. How does the safety model differ between an API agent and a physical one?

---

## 08. Test-Time Learning and In-Context Adaptation

**MOTTO:** The weights are frozen. The behavior doesn't have to be.

### The Problem
Your agent faces a task family it wasn't trained on — a proprietary DSL, a quirky internal API. Fine-tuning takes days and a dataset you don't have. You need the model to get better *during* the task.

### The Concept
Three escalating mechanisms, all without touching weights. **Many-shot in-context learning**: with long contexts, hundreds of examples in the prompt approach fine-tuning quality. **Test-time compute scaling**: spend more inference on hard problems — longer reasoning, N samples with a verifier picking the winner, budget-forcing ("wait, let me reconsider"). **In-context adaptation loops**: the agent tries, observes the error, writes the lesson into its own working context, and retries — Reflexion's insight, "learning" as accumulation of verbal experience in context. The weights are the instincts; the context is the notebook.

### Build It
- Take a task your agent fails ~50% of (e.g., queries in a made-up DSL you define). Measure baseline, then: (a) 3-shot vs. 50-shot vs. 300-shot examples in context; (b) best-of-8 sampling with a programmatic verifier; (c) a retry loop where error messages and the agent's own post-mortem notes persist across attempts.
- Chart accuracy vs. tokens spent for all three. You're drawing the test-time scaling curve for your own task — and finding where it flattens.

### Use It
Long-context models + prompt caching (many-shot is only affordable cached), verifier functions from your eval harness, reasoning-effort controls on o-series/Claude extended thinking.

### War Story
In December 2024, OpenAI's o3 scored 75.7% on ARC-AGI's semi-private eval in its standard configuration and 87.5% with high test-time compute — on a benchmark designed to resist memorization, where GPT-4o managed single digits. Same weights across both o3 scores; the difference was purely how much inference-time search the model was allowed. ARC Prize's own analysis of the cost spread (lesson 16-02 covered the dollars) framed the new reality: capability is now partly a *purchasing decision made at inference time*.

### Checkpoint
1. When does many-shot ICL beat fine-tuning as an engineering choice, and what makes it affordable?
2. Why does best-of-N need a verifier, and what happens without one?
3. What is the difference between Reflexion-style adaptation and simply retrying?

---

## 09. Agent Economies and Machine Payments

**MOTTO:** An agent that can't pay is an agent that always needs you.

### The Problem
Your research agent hits a paywalled API: $0.002 per call. A human would just pay it. Your agent stops dead, because the entire payments stack — cards, checkouts, CAPTCHAs, 3-D Secure — assumes a human with thumbs. And giving an autonomous loop your raw Visa number is a lesson-16 war story waiting to happen.

### The Concept
Two real building blocks exist today. **Pay-per-request protocols**: x402 (Coinbase, 2025) revives HTTP status 402 "Payment Required" — a server answers a request with a price, the client (an agent) pays in stablecoins, retries with payment proof, and gets the resource; no accounts, no sessions, machine-speed micropayments. **Scoped credentials**: virtual cards and mandates issued per-agent with hard limits — single merchant, spend cap, expiry — from Stripe's agent tooling and the card networks' 2025 programs (Visa Intelligent Commerce, Mastercard Agent Pay), so an agent's purchasing power is a capability token, not a wallet. The design rules are your Phase 16 lessons wearing a money hat: hard budgets, idempotency keys on every charge, and a human-approval gate above a threshold. Beyond this, agent-to-agent commerce at scale is early and unproven — treat vision decks accordingly.

```
agent ──GET /api/data──▶ server
      ◀── 402 + price ──
      ──payment payload─▶  (stablecoin via facilitator)
      ◀── 200 + data ────
```

### Build It
- Build a toy x402 flow: a Flask API returns 402 with `{price, pay_to}`; your agent checks the price against its budget policy, "pays" against a mock ledger, retries with the receipt header. Enforce a per-session spend cap and a per-call price ceiling.
- Add the human gate: purchases over $X pause the run and request approval (your async patterns from 16-07).
- Log every payment as a span with idempotency key — a double-charged retry is the same bug as lesson 16-04, now with real money.

### Use It
x402 (protocol + SDKs), Coinbase AgentKit, Stripe's agent toolkit and issuing (single-use virtual cards), Skyfire, Visa Intelligent Commerce / Mastercard Agent Pay (network-level agent credentials), Google's AP2 agent-payments protocol.

### War Story
When Coinbase launched x402 in May 2025, the pitch was precisely the dormant corner of HTTP/1.1: status code 402, reserved since the 1990s for a payment future that never arrived because card fees made micropayments absurd. Stablecoin rails made per-request payments of fractions of a cent viable, and the launch drew collaborators including AWS, Cloudflare, and Circle; Cloudflare's related 2025 "pay per crawl" experiments applied the same 402 pattern to charging AI crawlers for content. It is genuinely early — but it's the first payments primitive designed for software as the customer.

### Checkpoint
1. Why do traditional card checkouts fail agents both technically and on a risk basis?
2. How do scoped credentials change the blast radius of a compromised or buggy agent?
3. Which Phase 16 disciplines apply directly to agent payments, and how?

---

## 10. The Research Frontier: What to Read Next

**MOTTO:** The gap between arXiv and production is your career opportunity.

### The Problem
This course ends; the field doesn't. You need the short list of papers that built the ideas you've been using — read in order, they're the origin story of everything in Phases 1–17 — plus the reflexes to keep up without drowning.

### The Concept
Read primary sources. Blog summaries decay; the papers tell you what was actually measured, on what, with what caveats — and the caveats are where the next project lives.

### The Reading List
**ReAct** (Yao et al., 2022) — The paper behind your Phase 2 agent loop. Interleaves reasoning traces with actions so each informs the other, beating act-only and reason-only baselines on knowledge and interaction tasks. Notable for how little machinery it needs: it's prompting, and it started everything.

**Reflexion** (Shinn et al., 2023) — Agents that learn from failure without weight updates: after an unsuccessful attempt, the agent writes a verbal self-critique into memory and retries with that lesson in context. Substantial gains on coding and decision tasks; the foundation of every self-correction loop you've built.

**Tree of Thoughts** (Yao et al., 2023) — Generalizes chain-of-thought into search: maintain multiple candidate reasoning branches, self-evaluate, backtrack. Its headline result (Game of 24: 4% → 74% over CoT with GPT-4) made deliberate search-over-thoughts a standard tool, prefiguring test-time compute scaling.

**Voyager** (Wang et al., 2023) — Lesson 03's hero: lifelong learning in Minecraft via an automatic curriculum, self-written and verified code skills, and a compounding skill library. Read it for the promotion-gate design; the numbers (3.3× items, 15.3× faster milestones) follow from it.

**Generative Agents** (Park et al., 2023) — The "Smallville" paper: 25 LLM agents in a simulated town with observation, reflection, and retrieval-based memory produce emergent social behavior — famously, agents spreading word of a Valentine's party and showing up. The memory-stream architecture (recency × importance × relevance) shaped every agent-memory system since, including your Phase memory work.

**SWE-bench** (Jimenez et al., 2023) — The benchmark that made coding agents measurable: 2,294 real GitHub issues from 12 Python repos, scored by whether the agent's patch passes the repo's own tests. Early models resolved under 2%; the subsequent climb (and the Verified subset's creation after quality audits) is the cleanest capability curve in the field. Read it to understand what your Phase 9 evals aspire to.

**MemGPT** (Packer et al., 2023) — Memory management as an operating system: the context window is RAM, external storage is disk, and the LLM itself pages data between tiers via function calls. The conceptual ancestor of production memory systems (and of lesson 04's sleep-time compute, from the same lineage).

**DeepSeek-R1** (DeepSeek, 2025) — Reasoning via pure RL with GRPO and verifiable rewards (R1-Zero), then the practical recipe: SFT cold-start + RL + distillation into small models. Read it for what emerged without supervision (longer thinking, self-checking) and for the training economics that startled the industry in January 2025.

### Build It
Pick one paper, reproduce its core result at toy scale on your own harness, and write up where your numbers diverged from the paper's. That workflow — read, reproduce, note the gap — is how you stay current for the next decade.

### War Story
AutoGPT (March 2023) became one of the fastest repositories in GitHub history to pass 100k stars — an autonomous GPT-4 loop that captured the imagination and then, in practice, wandered, looped, and burned API budgets on most real tasks. Meanwhile the quieter papers above supplied the actual load-bearing ideas. The field's hype and its substance are usually published the same month; the reading list is how you tell them apart.

### Checkpoint
1. Which three papers on this list most directly explain your own Phase 2–5 architecture, and how?
2. Why did SWE-bench change coding-agent research more than any model release?
3. What's your personal system for tracking this field a year from now? (Wrong answer: "Twitter.")
