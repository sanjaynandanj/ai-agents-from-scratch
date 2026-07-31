# Phase 10 — 🦙 Open Models & Local Agents

> Your agent, your weights, your GPU, your rules.

Everything so far worked against hosted APIs; this phase moves the model onto hardware you control. Open-weight models change the economics (no per-token bill), the privacy story (data never leaves the building), and the engineering (you now own serving, quantization, and tool-calling formats that hosted providers hid from you). The models are smaller and rougher than frontier APIs — that's the honest trade, and this phase teaches you when it's worth making. By the end you'll run a complete agent loop against a model whose weights sit on your own disk.

## 01. The Open-Model Landscape: Llama, Qwen, Mistral, Hermes

**MOTTO:** "Open" is a spectrum, and the license is part of the spec.

### The Problem
"Just use an open model" hides real choices: model families differ in license terms, tool-calling ability, language coverage, and how much community tooling exists. Picking by leaderboard rank alone ships you a model you can't legally or practically deploy.

### The Concept
Think of model families as Linux distributions: a few big upstream lineages, each with its own release culture, plus downstream fine-tunes (like Hermes) that repackage base models with different behavior. "Open weights" usually means you get the parameters, not the training data or pipeline — so it's more like getting the compiled binary plus a permissive-ish EULA than true open source.

### Build It
Make a shortlist spreadsheet: for three candidate models record license, parameter count, context length, native tool-calling support, and GGUF availability. Then run the same three-tool agent prompt from Phase 2 against each via a hosted playground and grade the tool calls by hand.

### Use It
| Family | Origin | Notable trait |
|---|---|---|
| Llama | Meta | Huge ecosystem; custom "community license" with conditions |
| Qwen | Alibaba | Strong multilingual + tool use; most releases Apache 2.0 |
| Mistral | Mistral AI | Efficient dense + MoE models; Apache 2.0 on many |
| Hermes | Nous Research | Fine-tunes of Llama/other bases; explicit function-calling training |

### War Story
Meta released the original LLaMA in February 2023 to approved researchers only — and within about a week the weights leaked via a torrent posted to 4chan. Rather than retreat, Meta shipped Llama 2 that July with a commercial-use license, effectively ratifying the open-weights era the leak had started.

### Checkpoint
1. What do you get with "open weights" that you still don't get versus true open source?
2. Why does license type belong in your model selection spreadsheet?
3. What distinguishes a fine-tune family like Hermes from a base family like Llama?

## 02. Hermes and Open Tool-Calling Formats

**MOTTO:** Tool calling isn't magic — it's a chat template and a parsing convention.

### The Problem
Hosted APIs hand you a clean `tool_calls` array. An open model just emits tokens. If you don't know the exact format the model was trained to emit tool calls in — and render your prompt with the matching chat template — you get prose about tools instead of calls.

### The Concept
Open tool calling has three layers: (1) the *chat template* (a Jinja template shipped with the model) that turns your message list into the token stream the model expects; (2) the *tool definition convention* — JSON schemas injected into the system prompt; (3) the *call syntax* the model emits. Nous Research's Hermes models popularized a widely copied convention: JSON inside XML-style tags.

```
System prompt:  ...here are your tools: [{"name": "get_weather", ...}]
                Wrap calls in <tool_call> tags.
Model output:   <tool_call>{"name": "get_weather",
                            "arguments": {"city": "Pune"}}</tool_call>
Your runtime:   parse tags -> run tool -> reply in <tool_response> tags
```

### Build It
Write a parser: regex out `<tool_call>...</tool_call>` blocks, `json.loads` the payload, dispatch, then append the result wrapped in the response convention. Handle the failure case where the model half-emits a tag — that's the case that separates demos from agents.

### Use It
In practice you rarely hand-roll this: `transformers` applies chat templates via `apply_chat_template(tools=...)`, and servers like vLLM and Ollama ship per-family tool-call parsers behind an OpenAI-compatible API. But debugging a local agent means reading raw output, so learn the tags.

### War Story
Nous Research's Hermes 2 Pro (2024) shipped with a dedicated function-calling format — schemas in the system prompt, calls in `<tool_call>` XML tags — plus a public GitHub repo documenting it, and the convention was adopted well beyond Hermes, including as a named parser in vLLM. Hermes 3 followed in August 2024, scaling the recipe up to a 405B Llama 3.1 fine-tune.

### Checkpoint
1. What are the three layers between your message list and a parsed tool call?
2. Why does using the wrong chat template silently degrade tool calling?
3. What should your parser do with a malformed or unterminated `<tool_call>` block?

## 03. Serving: Ollama, vLLM, llama.cpp

**MOTTO:** The weights are the engine; the server is the transmission.

### The Problem
A model file does nothing by itself. You need an inference server that loads weights, batches requests, manages KV cache, and speaks an API your agent loop understands — and the right choice differs wildly between "my laptop" and "forty concurrent users."

### The Concept
Three tiers, one metaphor — kitchens: llama.cpp is a camp stove (runs anywhere, C/C++, CPU-friendly); Ollama is a home kitchen (wraps llama.cpp with model management, one-line pulls, an API); vLLM is a restaurant line (GPU-first, continuous batching, PagedAttention to stop wasting KV-cache memory). All three can expose OpenAI-compatible endpoints, which is what keeps your agent code portable.

### Build It
```bash
ollama pull qwen2.5:7b
curl http://localhost:11434/v1/chat/completions \
  -d '{"model": "qwen2.5:7b", "messages": [{"role": "user", "content": "hi"}]}'
```
Then point your Phase 9 Lesson 01 raw loop at `base_url="http://localhost:11434/v1"`. Nothing else changes. That's the payoff of the compatible API.

### Use It
| Server | Sweet spot | Weak spot |
|---|---|---|
| llama.cpp | CPU/edge, minimal deps, GGUF native | DIY ergonomics |
| Ollama | Local dev, model management | Not built for high concurrency |
| vLLM | Multi-user GPU serving, throughput | Heavier setup, GPU required |

### War Story
Georgi Gerganov wrote llama.cpp in March 2023, and within days the community had Llama running on MacBooks and even a Raspberry Pi 4 — at seconds per token, but running. vLLM came from the other direction: its PagedAttention paper (Kwon et al., SOSP 2023) showed KV-cache paging could deliver order-of-magnitude throughput gains over naive serving, and it became the default for serious GPU deployments.

### Checkpoint
1. Which server would you pick for a CPU-only laptop demo, and why?
2. What problem does PagedAttention solve, in one sentence?
3. Why do OpenAI-compatible endpoints matter for your agent code specifically?

## 04. Quantization: Fitting Brains in Small Boxes

**MOTTO:** Trade decimal places for gigabytes; just measure what you traded.

### The Problem
A 70B model at 16-bit needs ~140 GB just for weights — no consumer GPU holds that. Without quantization, "local agent" means "7B or nothing" for most people.

### The Concept
Quantization stores weights at lower precision — 8, 5, or 4 bits instead of 16 — like compressing a photo: file shrinks, and artifacts appear gradually, then suddenly. GGUF is the container format (llama.cpp lineage) with quant levels like `Q8_0`, `Q5_K_M`, `Q4_K_M`; the K-quants spend their bit budget unevenly, protecting sensitive layers.

```
FP16     ~14 GB (7B model)   reference quality
Q8_0      ~7 GB              nearly indistinguishable
Q4_K_M    ~4 GB              the popular sweet spot
Q2_K      ~3 GB              noticeably lobotomized
```

### Build It
Pull the same model at `Q8_0` and `Q4_K_M`, then run your *agent* eval — tool-call correctness over 20 prompts — not just a chat vibe check. Quantization damage shows up first in precise formats (JSON, arguments), exactly where agents live.

### Use It
GGUF quants on Hugging Face (community quantizers publish full ladders per model); GPTQ/AWQ for GPU-native quantization under vLLM. Rule of thumb: a bigger model at 4-bit usually beats a smaller model at 16-bit at equal memory — but verify on *your* tasks.

### War Story
The QLoRA paper (Dettmers et al., May 2023) showed you could fine-tune a 65B model on a single 48 GB GPU by quantizing the base to 4-bit NF4 and training LoRA adapters on top — collapsing what had been a multi-node job into one card and kicking off the consumer fine-tuning wave.

### Checkpoint
1. Why does quantization damage appear in tool calls before casual chat?
2. What does the K in `Q4_K_M` buy over naive uniform quantization?
3. Given 16 GB of VRAM, how would you decide between a 7B-Q8 and a 14B-Q4?

## 05. Local Agent Stacks End to End

**MOTTO:** A local agent is five layers, and you now own all five.

### The Problem
Individually you understand models, servers, and loops. Assembled, they fail in cross-layer ways: the server's template doesn't match the model's tool format, the quant breaks JSON, the context window fills silently. Someone has to own the whole stack — locally, that someone is you.

### The Concept
```
┌─────────────────────────────┐
│ Agent loop (your code)      │  retries, tool dispatch, memory
├─────────────────────────────┤
│ Structured-output layer     │  grammars/validation (Lesson 08)
├─────────────────────────────┤
│ API surface                 │  OpenAI-compatible endpoint
├─────────────────────────────┤
│ Inference server            │  Ollama / vLLM / llama.cpp
├─────────────────────────────┤
│ Model + quant + template    │  the actual weights
└─────────────────────────────┘
```
Debugging rule: failures propagate *up*, so diagnose *down* — bad agent behavior is usually a template or quant problem wearing a costume.

### Build It
Compose a stack spec file (model, quant, server, template, context limit, tool format) for one working configuration, and a smoke test that exercises every layer: raw completion, chat template, one tool call, one multi-turn run. Run it whenever any layer changes.

### Use It
Common working combos: Ollama + Qwen or Llama instruct models for dev boxes; vLLM + AWQ-quantized models with its tool-call parsers for shared GPU servers; llama.cpp + GGUF + GBNF grammar for embedded/edge. Pin versions — server updates change template handling more often than you'd hope.

### War Story
Ollama added an OpenAI-compatible API in February 2024, and it quietly became the biggest enabler of local agent stacks: overnight, every tutorial, SDK, and framework written against OpenAI's API shape could target local weights by changing one base URL. Compatibility, not capability, was the unlock.

### Checkpoint
1. Name the five layers and one characteristic failure per layer.
2. Why "diagnose down" when the symptom appears at the top?
3. What belongs in a stack spec file, and why pin server versions?

## 06. Fine-Tuning for Tool Use

**MOTTO:** If the model won't call tools reliably, teach it — with traces, not scolding.

### The Problem
Base and casually instruction-tuned models emit tool calls inconsistently: wrong format, hallucinated arguments, calling tools when they shouldn't. Prompt engineering plateaus; below a certain model size, formats must be *trained in*.

### The Concept
Supervised fine-tuning (SFT) on tool-call transcripts: each example is a full conversation — system prompt with schemas, user request, correctly formatted `<tool_call>`, tool response, final answer. LoRA/QLoRA makes this cheap by training small adapter matrices instead of all weights. The analogy is drilling a new employee on the ticketing system: you don't retrain their whole education, just the workflows — including *negative* examples (requests that need no tool) so they don't file tickets for everything.

### Build It
Assemble ~1k traces: harvest successful runs from a stronger model, convert to your target's chat template, and include failure-mode counterexamples (no-tool-needed, missing-parameter-so-ask). Train with a standard SFT stack (`trl`/`axolotl`/`unsloth`, QLoRA config), then eval against the tool-correctness suite from Lesson 04 — never against loss alone.

### Use It
Public function-calling datasets (e.g., Glaive's, credited in Hermes model cards) bootstrap the format; your own domain traces provide the last mile. Benchmark on the Berkeley Function-Calling Leaderboard style of eval: schema-exact matching, not vibes.

### War Story
Berkeley's Gorilla project (Patil et al., 2023) fine-tuned a 7B LLaMA on API-call data and reported it beating GPT-4 on their APIBench API-invocation benchmark — an early, concrete demonstration that a small specialist can out-call a giant generalist on the narrow skill agents actually need.

### Checkpoint
1. Why do negative (no-tool) examples belong in the training set?
2. What does LoRA change about the cost and artifact of fine-tuning?
3. Why is eval-by-loss insufficient for a tool-use fine-tune?

## 07. Distillation: Teaching Small Models Agent Tricks

**MOTTO:** Big model writes the textbook; small model studies it.

### The Problem
Frontier models plan and recover well but are too big to run locally; small open models fit on your GPU but reason clumsily. You want the big model's *behavior* at the small model's *price*.

### The Concept
Distillation trains a student model on a teacher's outputs. For agents, that means generating thousands of teacher trajectories — plans, tool calls, error recoveries — filtering for successful ones, and fine-tuning the student on them. It's an apprenticeship: the student copies worked examples, including the *reasoning traces*, not just final answers. Limits are real: students inherit style more easily than judgment, and generalization beyond the trace distribution is the first thing to break.

```
teacher (API) ──> 10k task trajectories ──> filter successes ──> SFT student (7B)
```

### Build It
Distill one skill, narrowly: generate 500 teacher runs of your Phase 2 agent's task family, keep the runs that pass your eval, convert to student chat format, QLoRA-train, then compare student-vs-teacher pass rates on held-out tasks. Expect a gap; measure it honestly.

### Use It
Note the legal wrinkle before you build a product on this: most hosted providers' terms restrict using their outputs to train competing models. Distilling from your *own* larger open model (Llama 405B → 8B) sidesteps that cleanly.

### War Story
Stanford's Alpaca (March 2023) fine-tuned LLaMA 7B on 52k instruction examples generated by OpenAI's text-davinci-003, for a reported training cost under $600 — then took its public demo down within weeks over safety and cost concerns. It proved both halves of the distillation story at once: startlingly cheap capability transfer, and the governance questions that follow it.

### Checkpoint
1. What gets filtered between teacher generation and student training, and why?
2. Why do students inherit style more reliably than judgment?
3. What terms-of-service issue affects distilling from hosted frontier models?

## 08. Structured Output on Open Models

**MOTTO:** Don't ask nicely for JSON — make invalid JSON impossible to emit.

### The Problem
Agents die on almost-JSON: trailing commas, unquoted keys, a chatty preamble before the brace. Retry loops mask the problem and burn latency. On hosted APIs you clicked "JSON mode"; locally, you get to build the mode.

### The Concept
Grammar-constrained decoding filters the model's next-token distribution: at each step, mask every token that would violate the target grammar, then sample from what's left. The model literally *cannot* emit invalid output. It's bowling with bumper rails — the ball still chooses its path, but the gutter is physically closed. This is a decisive home-field advantage of local inference: you control the sampler, so you can compile a JSON Schema to a token-level automaton.

```
logits ──> mask (tokens legal under grammar state) ──> sample ──> advance grammar
```

### Build It
Two routes: llama.cpp's GBNF — write a grammar, pass it at inference; or Outlines — `outlines.generate.json(model, MySchema)` compiles a Pydantic schema to a finite-state machine over tokens. Wire either under your tool-call parser so *arguments* are schema-valid before your code ever sees them.

### Use It
Outlines (dottxt), llama.cpp GBNF, vLLM's guided/structured decoding options, XGrammar. Caveat worth knowing: constraints guarantee *validity*, not *quality* — a model forced into a schema can still fill it with confident nonsense, so validation-by-type and evaluation-by-content remain separate jobs.

### War Story
The technique went mainstream through Outlines, whose underlying paper (Willard & Louf, 2023) showed guided generation could run with negligible per-token overhead by precompiling the constraint into a finite-state machine. When OpenAI shipped Structured Outputs in August 2024 advertising 100% schema conformance, it was the same family of constrained-decoding ideas — arriving at the API tier a year after open-source samplers had it.

### Checkpoint
1. Mechanically, where in the sampling pipeline does the grammar intervene?
2. Why can constrained decoding guarantee validity but not correctness?
3. Why is this technique easier to apply locally than through most hosted APIs?

## 09. Privacy and On-Prem Agent Deployments

**MOTTO:** The cheapest data-processing agreement is the one you never need to sign.

### The Problem
Agents see everything: source code, contracts, patient notes, financials — plus whatever their tools read. Sending that to a third-party API creates residency, retention, and regulatory exposure that some industries (health, defense, finance) simply cannot accept.

### The Concept
Local inference collapses the data-flow diagram: prompt and completion never cross your network boundary, so whole categories of GDPR/HIPAA analysis reduce to "the data stayed on our metal." But — and this is the part vendors skip — the *agent* is more than the model. Tool calls, logs, traces, and memory stores each leak independently. On-prem means auditing the whole stack from Lesson 05, not just pointing at the GPU.

```
Hosted:  your data ──> internet ──> provider (retention? training? subpoena?)
On-prem: your data ──> localhost ──> your disk ──> your retention policy
```

### Build It
Threat-model your Lesson 05 stack: enumerate every place agent data lands (server logs, Ollama history, trace files, tool outputs, vector store), then write the retention and access policy per location. Run the agent on an airgapped or egress-blocked host and confirm with a packet capture that nothing phones home.

### Use It
Deployment tiers: fully local (llama.cpp/Ollama on workstation), private cluster (vLLM behind your VPN), VPC-hosted open weights (cloud GPUs, your tenancy). Compliance artifacts that open weights simplify: data-processing agreements, sub-processor lists, cross-border transfer analysis.

### War Story
In early May 2023, Samsung banned employee use of generative AI tools after engineers pasted internal source code into ChatGPT; weeks earlier, Italy's data-protection authority had temporarily blocked ChatGPT nationwide over GDPR concerns. Both incidents pushed enterprises toward the same conclusion: for sensitive workloads, inference has to happen where the data already lives.

### Checkpoint
1. Which agent components besides the model can leak data, and how?
2. What does egress-blocking plus packet capture actually verify?
3. Which compliance artifacts get simpler when inference is on-prem, and which don't change?

## 10. Build a Local Agent with an Open Model

**MOTTO:** One base URL, one loop, zero API keys.

> ⚙️ **Setup required** — this is the only lesson in this phase that needs software installed: [Ollama](https://ollama.com) running locally with a tool-capable model pulled (e.g. `ollama pull qwen2.5:7b`). Everything else in this phase reads fine dry; this one you run.

### The Problem
You've met every layer separately. Time to prove the whole thesis: a complete tool-calling agent loop, on your machine, against weights you control, with no external dependency but Python and Ollama.

### The Concept
Same loop as Phase 9 Lesson 01 — the only differences are the endpoint (`localhost:11434`) and that *you* are the provider. Ollama's `/api/chat` accepts a `tools` array, applies the model's chat template, parses the model's tool-call convention, and hands you structured `tool_calls` back. The hosted-API experience, reconstructed from parts you now individually understand.

### Build It
```python
import requests, json

def get_weather(city: str) -> str:
    return json.dumps({"city": city, "temp_c": 31})   # mock it; wiring is the lesson

TOOLS = [{"type": "function", "function": {
    "name": "get_weather", "description": "Current weather for a city",
    "parameters": {"type": "object",
                   "properties": {"city": {"type": "string"}},
                   "required": ["city"]}}}]

messages = [{"role": "user", "content": "What's the weather in Pune?"}]
while True:
    r = requests.post("http://localhost:11434/api/chat", json={
        "model": "qwen2.5:7b", "messages": messages,
        "tools": TOOLS, "stream": False}).json()
    msg = r["message"]; messages.append(msg)
    calls = msg.get("tool_calls")
    if not calls:
        print(msg["content"]); break
    for c in calls:
        fn = c["function"]
        out = get_weather(**fn["arguments"])
        messages.append({"role": "tool", "content": out, "tool_name": fn["name"]})
```
Extensions: add a second tool and watch routing; swap models and re-run your eval; kill your Wi-Fi first, for the principle of the thing.

### Use It
From here the upgrades map to earlier lessons: grammar-constrain the arguments (Lesson 08), quantize down until your eval complains (Lesson 04), fine-tune if it complains too early (Lesson 06), then move the whole thing to vLLM when a second user shows up (Lesson 03).

### War Story
This exact stack is the descendant of llama.cpp's March 2023 proof that frontier-adjacent models could run on commodity hardware — the demos of Llama grinding out tokens on a MacBook and a Raspberry Pi. Three years of quantization, serving, and fine-tuning work later, the same class of hardware runs full tool-calling agents; the loop you just wrote is that history, operationalized.

### Checkpoint
1. Which layers from Lesson 05 does Ollama handle in this code, and which remain yours?
2. What would you change to run this loop against vLLM instead?
3. Run it with Wi-Fi off: what does that demonstrate about the trust boundary?
