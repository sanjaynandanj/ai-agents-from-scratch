# Phase 07 — 🧩 Structured Outputs & Control

> Free text is for poems. Systems need schemas.

An agent's output isn't read by a human — it's parsed by code, routed by dispatchers, and written to databases. One stray "Sure! Here's your JSON:" and the pipeline dies at 3 a.m. This phase covers making stochastic text generators behave like reliable software components: schemas, grammars, validators, judges, guardrails, routers, and the deterministic scaffolding that holds it all together.

## 01. JSON Schema Enforcement and Constrained Decoding

**MOTTO:** Don't ask for JSON. Make anything else impossible.

### The Problem
"Respond in JSON" is a request, and models decline requests: markdown fences, trailing commas, apologetic preambles, invented fields. If downstream code does `json.loads()` on model output, prompt-level politeness is a production incident on a timer.

### The Concept
Two enforcement levels:
1. **API-level structured outputs**: you pass a JSON Schema; the provider guarantees conformant output.
2. **Constrained decoding** (how it works under the hood): at every generation step, mask the logits of any token that would violate the schema's grammar. The model literally cannot emit an invalid character.

```
next-token logits: { "a": 2.1, "{": 1.8, "Sure": 3.0, ... }
schema says next char must be '{'
masked logits:     { "{": 1.8 }   ← everything else → -inf
```

It's a bowling lane with the bumpers up: the ball can wobble, but it cannot leave the lane.

### Build It
- Define the schema from your code's types (Pydantic model → `model_json_schema()`), never by hand-writing JSON Schema twice.
- Pass it via the provider's structured-output/tool-schema parameter.
- Keep schemas tight: `required` everything, `additionalProperties: false`, enums over free strings.

### Use It
| Tool | Mechanism |
|---|---|
| OpenAI Structured Outputs | `response_format` with strict JSON Schema |
| Anthropic tool use | Tool `input_schema` constrains arguments |
| Outlines / XGrammar / llama.cpp | Local logit masking for open models |

### War Story
OpenAI shipped JSON mode at DevDay in November 2023 (valid JSON, but any shape), then Structured Outputs in August 2024, reporting 100% schema adherence on their evals versus under 40% for prompting alone on gpt-4-0613. The gap between "please" and "must" was measured, and it was enormous.

### Checkpoint
1. What's the difference between JSON mode and structured outputs?
2. How does logit masking guarantee validity without retraining the model?
3. Why does `additionalProperties: false` matter for downstream code?

## 02. Validation and Repair Loops

**MOTTO:** Trust, but `try/except`.

### The Problem
Constrained decoding guarantees *syntax*, not *sense*: a schema-valid response can still contain a date of "yesterday-ish", a negative quantity, or an email without an @. And not every model or provider supports constrained decoding at all. You need a net under the net.

### The Concept
Validate → if invalid, repair → revalidate, with a bounded loop:

```
LLM output ─▶ parse ─▶ schema check ─▶ semantic check ─▶ ✅ accept
                │            │               │
                └────────────┴───────────────┘
                             ▼
             repair prompt: original + output + EXACT errors
                             ▼
                   retry (max K, then fail loudly)
```

The repair prompt is surgical: "Your output failed validation: `quantity: -3 is not >= 0`. Return corrected JSON only." Specific errors fix in one round; "that was wrong, try again" loops forever.

### Build It
- Layer checks: `json.loads` → Pydantic schema → custom validators (business rules).
- On failure, send back the exact validator messages, not a paraphrase.
- Cap at 2–3 retries; after that, raise. A silent infinite repair loop is worse than a crash.

### Use It
The Instructor library (built on Pydantic) made this pattern famous — define a model, get automatic validation-and-retry against any LLM. LangChain's `OutputFixingParser` and Guardrails AI do the same dance.

### War Story
This pattern is why function calling exists at all: before OpenAI shipped it in June 2023, developers were regex-scraping JSON out of chatty completions and building homegrown repair loops — a cottage industry of `extract_json_from_markdown()` utilities that the ecosystem is still deleting. The repair loop remains the portable fallback when strict decoding isn't available.

### Checkpoint
1. Why can schema-valid output still be wrong, with two examples?
2. What makes a repair prompt effective versus useless?
3. Why must the repair loop be bounded?

## 03. State Machines for Agent Control Flow

**MOTTO:** The LLM proposes. The state machine disposes.

### The Problem
"While loop + LLM decides everything" agents wander: they skip approval steps, call tools out of order, and re-enter states they should have left. Some transitions — *refund requires approval first* — must be guaranteed, and a prompt cannot guarantee anything.

### The Concept
Model the agent as a finite state machine. States define what the LLM may do *right now*; edges define legal transitions; your code — not the model — enforces both.

```
 ┌─────────┐  intent   ┌──────────┐  needs_ok  ┌──────────┐
 │ TRIAGE  │──────────▶│ RESOLVE  │───────────▶│ APPROVAL │
 └─────────┘           └────┬─────┘            └────┬─────┘
      │ chitchat            │ solved                │ approved
      ▼                     ▼                       ▼
 ┌─────────┐           ┌──────────┐            ┌──────────┐
 │  REPLY  │           │  CLOSE   │◀───────────│ EXECUTE  │
 └─────────┘           └──────────┘            └──────────┘
```

The LLM picks *among allowed edges* (a constrained choice — lesson 01!); it never invents an edge.

### Build It
- Represent as a dict: `{state: {trigger: next_state}}`.
- Per state, restrict the toolset and the output schema to that state's legal actions.
- Illegal transition attempted? Log it, stay put, re-prompt with allowed options.

### Use It
| Tool | State model |
|---|---|
| LangGraph | Explicit graph: nodes, edges, conditional routing |
| AWS Step Functions | State machine orchestrating LLM steps |
| Hand-rolled | A dict and a while loop — often all you need |

### War Story
LangChain launched LangGraph in January 2024 precisely because its original free-form agent executors were too hard to control in production — the pitch was explicit graphs, cycles, and persistence instead of an opaque loop. The market voted for state machines by migrating.

### Checkpoint
1. What does the state machine guarantee that a system prompt cannot?
2. How do states interact with per-state tool restriction?
3. When is a full graph framework overkill versus a dict of transitions?

## 04. Grammars and Regex-Constrained Generation

**MOTTO:** JSON is one grammar. Your DSL deserves the same rigor.

### The Problem
Not everything is JSON. You need the model to emit valid SQL, a semver string, a chess move, a YAML config, or your product's mini-DSL. Schema enforcement doesn't cover arbitrary syntax — but the logit-masking trick generalizes.

### The Concept
Any formal language with a machine-checkable definition can constrain decoding:
- **Regex**: the generated string must match, char by char — perfect for IDs, dates, phone formats.
- **Context-free grammars** (EBNF/GBNF): full recursive syntax — expressions, nested structures, programming languages.

```
grammar:  answer ::= "yes" | "no" | "unsure"
model wants: "Well, probably..."  → masked
model emits: "unsure"             → only legal continuation
```

Same bumpers as lesson 01, arbitrary lane shape. The constraint engine compiles your grammar into an automaton and walks it in lockstep with generation.

### Build It
- With Outlines: `outlines.generate.regex(model, r"\d{4}-\d{2}-\d{2}")` — done.
- With llama.cpp: write a GBNF grammar file, pass `--grammar-file`.
- Design tip: constrain *structure*, not *content* — a grammar forcing `SELECT ... FROM allowed_table` beats one allowing arbitrary SQL.

### Use It
| Tool | Grammar support |
|---|---|
| llama.cpp | GBNF grammars |
| Outlines (.txt/dottxt) | Regex, JSON Schema, CFG |
| Guidance / SGLang / XGrammar | Templates and compiled grammars |

### War Story
Willard & Louf's 2023 paper "Efficient Guided Generation for Large Language Models" (the Outlines paper) reframed constrained decoding as walking a finite-state machine, making regex-constrained generation effectively free per token. llama.cpp had already made GBNF grammars a beloved feature for local models the same year — hobbyists had guaranteed-valid output before most API users did.

### Checkpoint
1. When do you need a CFG instead of a regex?
2. Why is constraining structure-not-content the right security posture for SQL generation?
3. What performance concern did FSM-based guided generation solve?

## 05. LLM-as-Judge: Grading With Models

**MOTTO:** Verification is easier than generation. Exploit the asymmetry.

### The Problem
Schemas can't grade quality. "Is this summary faithful? Is this reply on-brand? Did the agent actually answer?" have no regex. Human review doesn't scale to 10,000 outputs a day — but judging is genuinely easier than generating, and models can do it.

### The Concept
A second LLM call, engineered as an instrument:
- **Rubric-based**: score named criteria (faithfulness, completeness) with definitions per level.
- **Pairwise**: "which of A/B is better?" — easier and more reliable than absolute scores.
- **Reference-based**: compare output against a gold answer.

Known biases to engineer around: position bias (favors first answer — so swap order and average), verbosity bias (favors longer), self-preference (favors its own family's style).

### Build It
- Judge prompt = rubric + few graded examples + forced structured verdict: `{"score": 1-5, "reasoning": "..."}` (lesson 01 again).
- Fresh context — the judge never sees the generator's conversation.
- Calibrate: hand-label 50 outputs, measure judge-human agreement *before* trusting it in a gate.

### Use It
| Use case | Pattern |
|---|---|
| Offline evals | Judge scores a test set per release |
| Online gate | Judge checks response before sending (adds latency) |
| Training signal | Judge verdicts as reward / filter for fine-tuning data |

Tooling: OpenAI Evals, LangSmith, Ragas, promptfoo — all ship judge templates.

### War Story
The MT-Bench / Chatbot Arena paper (Zheng et al., 2023) measured GPT-4-as-judge agreeing with human preferences over 80% of the time — comparable to human-human agreement — while also documenting position and verbosity bias in the same study. The instrument works, and its error bars were published on day one.

### Checkpoint
1. Why is pairwise comparison more reliable than absolute scoring?
2. Name two judge biases and the mitigation for each.
3. What must you do before using a judge as a deployment gate?

## 06. Guardrail Layers: Pre, Mid, and Post

**MOTTO:** Defense in depth — because any single layer has a bad day.

### The Problem
Agents face hostile input (prompt injection), risky middles (dangerous tool calls), and embarrassing output (leaked PII, invented policies, off-topic rants). No single check catches all three, and the model itself is the least reliable enforcer of its own limits.

### The Concept
Three checkpoints around the stochastic core:

```
 user input ─▶ [PRE]  injection scan, topic filter, PII strip
                 │
                 ▼
              [MID]   tool-call allowlists, arg validation,
                 │    spend caps, human approval for irreversible ops
                 ▼
 response  ◀─ [POST]  PII/output filter, claim check vs policy docs,
                      tone/format lint
```

Pre-guards are cheap rules and classifiers; mid-guards are *code* (the only layer the model can't talk its way past); post-guards catch what generation invented.

### Build It
- Pre: regex + small-model classifier for injection/topic; strip or refuse.
- Mid: validate every tool call against an allowlist and arg schema *outside* the LLM; require human sign-off for the irreversible list.
- Post: PII scanner, and a judge (lesson 05) checking claims against your actual policy corpus.

### Use It
| Tool | Layer focus |
|---|---|
| NVIDIA NeMo Guardrails | Programmable rails, all three layers |
| Guardrails AI | Validator library, mostly post |
| Llama Guard / provider moderation APIs | Input/output classification |

### War Story
In February 2024, a Canadian tribunal ordered Air Canada to honor a bereavement-fare policy its website chatbot had invented — rejecting the airline's argument that the chatbot was "a separate legal entity responsible for its own actions." A post-guard checking claims against real policy documents is cheaper than the ruling, and much cheaper than the headlines.

### Checkpoint
1. Why is the mid layer the only one the model can't talk its way past?
2. Which layer would have saved Air Canada, and what would it check against?
3. Why do guardrails belong outside the LLM rather than in the system prompt?

## 07. Routing: Classify Then Dispatch

**MOTTO:** Not every question deserves your most expensive model.

### The Problem
One mega-prompt handling refunds, tech support, sales, and chitchat does all of them mediocrely — and burns frontier-model tokens on "what are your hours?". Meanwhile specialized handlers exist but nothing steers traffic to them.

### The Concept
A cheap classifier in front, specialists behind:

```
                    ┌▶ billing_agent    (tools: stripe, crm)
 input ─▶ [ROUTER] ─┼▶ support_agent    (tools: docs, tickets)
  cheap, fast       ├▶ smalltalk        (tiny model, no tools)
  structured out    └▶ human_handoff    (low confidence / high stakes)
```

The router's output is a *constrained enum* (lesson 01): `{"route": "billing", "confidence": 0.87}`. Route on intent, on difficulty (cheap model first, escalate on failure), or on risk (anything irreversible → human lane).

### Build It
- Router = small fast model + enum-constrained schema + few-shot examples per route.
- Always include a fallback route; a router without "unsure" is a misrouting machine.
- Log every routing decision — the misroutes become your next few-shot examples.

### Use It
| System | Routing flavor |
|---|---|
| LangGraph conditional edges | Route nodes on state |
| OpenRouter / LiteLLM | Cross-model routing and fallback |
| Claude Code | Model choice per task; subagent dispatch |

### War Story
OpenAI's GPT-5 launch in August 2025 put a real-time router in front of ChatGPT, automatically deciding between fast and reasoning variants per query. On launch day the router misbehaved — Sam Altman publicly acknowledged the autoswitcher broke, making the model "seem way dumber" — and user backlash forced OpenAI to restore manual model selection. Routing is powerful, and it is absolutely part of your product surface.

### Checkpoint
1. Why should the router's output be enum-constrained?
2. What are three different keys you can route on besides intent?
3. What did the GPT-5 launch teach about silent routing?

## 08. Confidence and Abstention: Teaching "I Don't Know"

**MOTTO:** A wrong answer costs 10×. "I don't know" costs an apology.

### The Problem
LLMs are trained to always answer, and they answer wrong with the same fluent confidence as right. In an agent pipeline, unearned confidence compounds: a hallucinated field flows into a database, a guessed route triggers a real tool call.

### The Concept
Give every output an escape hatch and a confidence signal:
- **Schema-level abstention**: make `"unknown"` a first-class enum value, so refusing is *structurally as easy* as answering.
- **Confidence elicitation**: self-reported scores (crude, overconfident), sampling agreement (ask 5× at temperature — do answers agree?), or token logprobs where available.
- **Calibration**: does stated 80% mean right 80% of the time? Measure on labeled data; expect overconfidence; remap.

```
confidence ≥ τ_high  ─▶ act autonomously
τ_low ≤ c < τ_high   ─▶ act + flag for review
confidence < τ_low   ─▶ abstain / escalate to human
```

### Build It
- Add `"answer": string | null` + `"confidence": number` + `"basis": string` to output schemas.
- Prompt the asymmetry explicitly: "If the evidence is insufficient, return null. A null is correct; a guess is a failure."
- Tune thresholds τ from measured calibration, not vibes.

### Use It
Sampling-agreement confidence gates production extraction pipelines (disagreement → human queue); abstention rates are a first-class metric on benchmarks like SimpleQA, which scores correct, incorrect, and *not attempted* separately.

### War Story
OpenAI's September 2025 paper "Why Language Models Hallucinate" argued the field did this to itself: benchmarks that grade binary right/wrong reward guessing over abstaining, so models learn to bluff like students on a multiple-choice exam with no negative marking. The fix they proposed is exactly this lesson — score "I don't know" better than a confident miss.

### Checkpoint
1. Why does making "unknown" a schema enum increase abstention quality?
2. Compare self-reported confidence with sampling agreement — tradeoffs?
3. What does it mean for a confidence signal to be calibrated?

## 09. Deterministic Scaffolds Around Stochastic Cores

**MOTTO:** Put the dice in a cup. The cup doesn't roll.

### The Problem
Teams sprinkle LLM calls through their codebase and then wonder why nothing is testable, debuggable, or predictable. The failure isn't the model being stochastic — it's letting stochasticity leak into control flow, error handling, and state.

### The Concept
Architectural rule: **deterministic code decides; the LLM fills in blanks.** Loops, retries, transitions, budgets, and side effects live in ordinary code you can unit-test. The LLM sits inside narrow, schema-bounded sockets.

```
┌────────────────── deterministic scaffold ──────────────────┐
│ state machine · retry caps · validators · budget · logging │
│                                                            │
│      ┌─────────┐        ┌─────────┐        ┌─────────┐     │
│      │ LLM 🎲  │        │ LLM 🎲  │        │ LLM 🎲  │     │
│      │ socket  │        │ socket  │        │ socket  │     │
│      └─────────┘        └─────────┘        └─────────┘     │
│  every socket: typed input → schema-constrained output     │
└────────────────────────────────────────────────────────────┘
```

This is the unifying theory of Phase 7: schemas (01), repair (02), state machines (03), grammars (04), judges (05), guardrails (06), routers (07), abstention (08) are all scaffold components around dice.

### Build It
- Wrap every LLM call in a typed function: `def extract_invoice(text: str) -> Invoice:` — callers never see prompts or raw strings.
- Test the scaffold with a mock LLM (deterministic, instant, free); test the sockets with recorded fixtures and evals.
- Make every socket swappable: model upgrades become config changes, not rewrites.

### Use It
This is the shape of every serious production agent: Temporal or Step Functions for durable deterministic orchestration with LLM activities inside; LangGraph graphs where nodes are typed functions; plain Python services where the LLM is just another fallible dependency behind an interface.

### War Story
Anthropic's December 2024 engineering post "Building Effective Agents" — written from watching dozens of production teams — landed on the same conclusion: the most successful implementations used "simple, composable patterns" rather than complex frameworks, and recommended adding autonomy only where measurably needed. The boring architecture won the field study.

### Checkpoint
1. What belongs in the scaffold and what belongs in a socket? Give two examples of each.
2. How does the typed-function wrapper enable testing without an API key?
3. Why does this architecture make model upgrades low-risk?

## 10. Build a Structured-Output Engine From Scratch

**MOTTO:** Instructor is ~this~ many lines of ideas. Build the ideas.

### The Problem
You've used validation-and-repair via libraries. Time to own it: a generic engine that takes any schema, any prompt, any (mock) LLM — and returns validated data or a loud, honest failure.

### The Concept
Lesson 02's loop, generalized: validate against a schema, feed exact errors back, bound the retries. Plus lesson 08's abstention and lesson 09's typed socket, in ~70 lines.

### Build It
```python
import json, re

def validate(data, schema):
    """Tiny validator: types, required, enums. Returns list of errors."""
    errors = []
    for field, spec in schema["fields"].items():
        if field not in data:
            errors.append(f"missing required field '{field}'"); continue
        val = data[field]
        if spec["type"] == "number" and not isinstance(val, (int, float)):
            errors.append(f"'{field}': expected number, got {type(val).__name__}")
        if spec["type"] == "string" and not isinstance(val, str):
            errors.append(f"'{field}': expected string, got {type(val).__name__}")
        if "enum" in spec and val not in spec["enum"]:
            errors.append(f"'{field}': {val!r} not in {spec['enum']}")
        if "min" in spec and isinstance(val, (int, float)) and val < spec["min"]:
            errors.append(f"'{field}': {val} below minimum {spec['min']}")
    for field in data:
        if field not in schema["fields"]:
            errors.append(f"unexpected field '{field}'")
    return errors

def extract_json(text):
    """Models wrap JSON in prose/fences. Dig it out."""
    m = re.search(r"\{.*\}", text, re.DOTALL)
    return json.loads(m.group()) if m else None

def structured_call(llm, prompt, schema, max_retries=2):
    msg = f"{prompt}\nReturn ONLY JSON with fields: {json.dumps(schema['fields'])}"
    for attempt in range(max_retries + 1):
        raw = llm(msg)
        data = extract_json(raw)
        errors = ["output was not JSON"] if data is None else validate(data, schema)
        if not errors:
            return {"ok": True, "data": data, "attempts": attempt + 1}
        msg = (f"{prompt}\nYour previous output failed validation:\n- "
               + "\n- ".join(errors) + "\nReturn ONLY corrected JSON.")
    return {"ok": False, "errors": errors, "attempts": max_retries + 1}

# Mock LLM: wrong on first call, corrected on repair.
calls = {"n": 0}
def mock_llm(prompt):
    calls["n"] += 1
    if calls["n"] == 1:
        return 'Sure! Here you go: {"amount": "forty", "status": "OK"}'
    return '{"amount": 40, "status": "approved"}'

schema = {"fields": {
    "amount": {"type": "number", "min": 0},
    "status": {"type": "string", "enum": ["approved", "rejected", "unknown"]},
}}
print(structured_call(mock_llm, "Extract the payment decision.", schema))
# → {'ok': True, 'data': {'amount': 40, 'status': 'approved'}, 'attempts': 2}
```

Exercises: (a) add `"unknown"`-style abstention and a confidence field; (b) make the mock fail all retries and confirm the loud failure; (c) add nested-object support to `validate`; (d) swap in a real LLM and measure attempts-per-success across 20 runs.

### Use It
This is the core of Instructor, Guardrails AI, and LangChain's fixing parsers — schema in, validated data or honest failure out. When you adopt those libraries now, you're choosing ergonomics, not magic.

### War Story
The industry measured how much this matters: the Berkeley Function-Calling Leaderboard (launched 2024 by the Gorilla team) evaluates models on whether their structured tool calls are *actually executable*, via AST matching — and even frontier models miss a meaningful fraction. The repair loop isn't training wheels; it's the difference between a demo and a system.

### Checkpoint
1. Why does the repair prompt include the exact validator errors?
2. Where would constrained decoding slot into this engine, and what would it eliminate?
3. What does `attempts` in the return value let you monitor in production?
