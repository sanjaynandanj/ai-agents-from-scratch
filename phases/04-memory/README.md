# Phase 04 — 📚 Memory

> Goldfish agents ask the same question twice. Give yours a hippocampus.

An LLM is stateless: every request starts from zero, and the only "memory" it has is whatever you paste into the context window. That works until the conversation outgrows the window, the session ends, or the user says "like I told you last week." This phase builds the memory stack — buffers, summaries, vector recall, entities, write policies, and forgetting — that turns a stateless function into something that appears to know you. The context window is RAM; everything else is a filing system you must design yourself.

## 01. Short-Term vs Long-Term Memory

**MOTTO:** The context window is RAM, not a hard drive — and RAM gets wiped.

### The Problem
Your user tells the agent their name, their stack, and their deadline. Twenty minutes later — new session — the agent cheerfully asks for all three again. Nothing was "forgotten," because nothing was ever stored: the model's weights didn't change, and the conversation lived only in a request payload that no longer exists.

### The Concept
Borrow the computer-architecture split. Short-term memory is whatever is *in the context window right now*: fast, fully attended-to, tiny, volatile. Long-term memory is everything *outside* the window — files, databases, indexes — that must be explicitly written and explicitly retrieved back in:

```
              ┌───────────────────────────┐
   prompt ──► │  CONTEXT WINDOW (RAM)     │ ──► response
              │  system + history + docs  │
              └─────▲───────────────┬─────┘
              retrieve             write
              ┌─────┴───────────────▼─────┐
              │  LONG-TERM STORE (disk)   │
              │  summaries · facts · logs │
              └───────────────────────────┘
```

The model never "remembers" anything across calls. Memory is an illusion your orchestration code constructs by moving the right bytes into the window at the right time.

### Build It
1. Short-term: a Python list of messages, re-sent on every call. That's it — that's the whole trick behind "chat."
2. Long-term: any persistence — start with a JSON file of facts.
3. The bridge: before each call, load relevant long-term items into the system prompt; after each call, decide what to save.

```python
class Agent:
    def __init__(self, store_path="memory.json"):
        self.messages = []                      # short-term: dies with the process
        self.store = load_json(store_path)      # long-term: survives it

    def chat(self, user_msg):
        context = "Known facts: " + "; ".join(self.store["facts"])
        reply = llm([{"role": "system", "content": context}]
                    + self.messages + [{"role": "user", "content": user_msg}])
        self.messages += [{"role": "user", "content": user_msg},
                          {"role": "assistant", "content": reply}]
        return reply
```

Everything else in this phase is refinements of the load/save steps.

### Use It
| Layer | Mechanism | Analogy |
|---|---|---|
| In-window history | Message list | CPU registers / RAM |
| Session persistence | JSONL transcript on disk | Suspend-to-disk |
| Cross-session facts | Memory file / DB | Filing cabinet |
| Learned behavior | Fine-tuning (rare, slow) | Muscle memory |

ChatGPT's Memory feature, Claude's memory tool, and frameworks' "memory modules" are all variations of the bridge step — none of them modify the model.

### War Story
The MemGPT paper (Packer et al., October 2023) made the OS analogy explicit and load-bearing: treat the context window as main memory, external storage as disk, and let the LLM itself issue "syscalls" to page data in and out — a virtual-memory manager for conversations. The framing stuck; the paper's authors went on to build Letta around it.

### Checkpoint
1. Why does a "chat" feel stateful when the model is stateless?
2. What are the two explicit operations your code must perform to simulate long-term memory?
3. In the MemGPT analogy, what corresponds to a page fault?

## 02. Conversation Buffers and Windowing

**MOTTO:** You can't keep everything — decide what falls off the back of the truck.

### The Problem
Message lists only grow. At turn 5 you're fine; at turn 150 you've blown the context limit and the API throws — or, subtler and worse, you're paying for 80k tokens per call, latency triples, and the model starts ignoring the middle of the pile. Unbounded buffers fail loud (overflow) or fail quiet (cost and degraded attention). Both are bugs.

### The Concept
A windowed buffer keeps the most recent N turns (or, better, most recent T *tokens*) and drops the oldest — a conveyor belt, not a warehouse:

```
  turn:   1    2    3    4    5    6    7    8
        ┌────┐
  drop ◄│ s1 │ [ 2    3    4    5    6    7    8 ]  ← window (kept)
        └────┘   ▲
                 └─ oldest survivor; next to fall
  Always pinned: system prompt (never drops)
```

Recency is a decent default heuristic — recent turns are usually most relevant — but windowing is *lossy amnesia*: the user's name from turn 1 is simply gone. That flaw is what lessons 03–08 exist to fix.

### Build It
1. Count tokens, not messages — messages vary wildly in size. A rough proxy (`len(text) // 4`) is fine to start.
2. Evict from the oldest end until under budget. Never evict the system prompt.
3. Keep message-pair integrity: don't orphan a tool result from its tool call, or an assistant reply from its user turn — providers reject dangling tool messages.

```python
def windowed(messages, budget=8000, count=lambda m: len(m["content"]) // 4):
    system, rest = messages[0], messages[1:]
    kept, total = [], count(system)
    for m in reversed(rest):                 # newest first
        if total + count(m) > budget:
            break
        kept.append(m); total += count(m)
    kept = list(reversed(kept))
    while kept and kept[0]["role"] in ("assistant", "tool"):
        kept.pop(0)                          # don't start mid-exchange
    return [system] + kept
```

### Use It
| Strategy | Keeps | Fails when |
|---|---|---|
| Last-N messages | Simple recency | One huge message busts budget |
| Token-budget window | Precise cost control | Early key facts needed later |
| Pinned + window | System prompt, first user goal | Mid-conversation facts |
| Window + summary (next lesson) | Gist of the dropped part | Details, verbatim quotes |

Every chat product you've used does some version of this; the differences are in what they refuse to drop.

### War Story
The "Lost in the Middle" paper (Liu et al., 2023) measured what practitioners suspected: models retrieve information best from the *beginning and end* of long contexts, with a pronounced U-shaped accuracy dip for facts placed in the middle. Windowing plus pinning — keep the start, keep the end, be suspicious of the middle — is that finding turned into an engineering rule.

### Checkpoint
1. Why budget by tokens rather than by message count?
2. What goes wrong if eviction splits a tool call from its tool result?
3. What does the "lost in the middle" result imply about *where* to place must-not-miss facts in the window?

## 03. Summarization Memory: Compress or Die

**MOTTO:** When the window fills, don't drop the past — shrink it.

### The Problem
Pure windowing threw away turn 1, where the user stated the whole point of the conversation. Forty turns of debugging later, the agent no longer knows what bug it's fixing. You need the *gist* of the dropped history without its token cost — because the alternative, keeping everything, is the overflow you just escaped.

### The Concept
Compaction: when the buffer nears its budget, use the LLM itself to compress the oldest chunk into a dense summary, then replace those messages with it:

```
  before:  [sys][m1..m40 — 30k tok][m41..m60 — 10k tok]
                     │ summarize (LLM call)
                     ▼
  after:   [sys][SUMMARY — 800 tok][m41..m60 — 10k tok]
                                     └ recent turns stay verbatim
```

Lossy compression, like JPEG for conversations: the picture survives, fine detail doesn't. The art is in the summarization prompt — a generic "summarize this" loses decisions and open TODOs; a targeted prompt ("preserve: user goals, decisions made, unresolved questions, file names, exact identifiers") keeps what the agent will actually need.

### Build It
1. Trigger at a threshold (e.g., 80% of budget) — not at 100%, or you have no room to summarize.
2. Split: oldest ~half becomes summarization input; recent turns stay verbatim.
3. Summarize with a task-aware prompt; include the *previous* summary so summaries chain instead of stacking.
4. Splice the summary in as a system-adjacent message.

```python
SUMMARIZE = """Compress this conversation for an agent's memory.
MUST preserve: user goals, decisions + reasons, unresolved questions,
exact names/paths/IDs mentioned. Omit pleasantries. Max 300 words.
Previous summary (merge into new one): {prev}"""

def compact(messages, budget, llm):
    if tokens(messages) < 0.8 * budget:
        return messages
    system, old, recent = messages[0], messages[1:-10], messages[-10:]
    prev = extract_prev_summary(system) or "none"
    summary = llm(SUMMARIZE.format(prev=prev) + render(old))
    return [system,
            {"role": "system", "content": f"[Conversation so far]: {summary}"},
            *recent]
```

5. Beware summary drift: each re-summarization compounds loss, like photocopying a photocopy. Chaining from the previous summary (step 3) limits this; pinning critical facts outside the summary (lesson 06/07) fixes it properly.

### Use It
| Approach | Tradeoff |
|---|---|
| Summarize-on-threshold | Occasional latency spike at compaction |
| Rolling summary each turn | Smooth, but an LLM call per turn |
| Hierarchical (summary of summaries) | Scales to very long sessions; more drift |
| Claude Code `/compact`-style | User-visible, on-demand; user controls timing |

### War Story
Compaction went from research idea to daily tooling fast: Claude Code ships auto-compaction that summarizes the conversation as the window fills (with `/compact` for manual control), and Anthropic later exposed the same idea at the API level as context editing. Anyone who has watched a long coding session survive three compactions — and then seen the agent misremember a detail from before the first one — has felt both the necessity and the lossiness firsthand.

### Checkpoint
1. Why trigger compaction *before* the window is actually full?
2. What information should a summarization prompt explicitly order the model to preserve, and why does "just summarize" fail?
3. What is summary drift, and which design choice in Build It mitigates it?

## 04. Vector Memory: Remember by Similarity

**MOTTO:** Store meanings, not strings — so "my dog" can find "the golden retriever."

### The Problem
Your agent stored "User adopted a golden retriever named Biscuit." Weeks later the user asks, "what food should I get for my dog?" A keyword search for "dog" finds nothing — the memory says *retriever*. Exact-match retrieval fails precisely when people do the normal human thing: refer to the same fact in different words.

### The Concept
Embeddings map text to points in high-dimensional space where semantic neighbors land close together. Vector memory stores each memory's embedding alongside its text; recall embeds the query and returns nearest neighbors by cosine similarity:

```
        "golden retriever named Biscuit" ●
                                    ●  "what food for my dog?"      near
                                                                     │
   "user prefers dark mode" ●                                      far
                     ● "quarterly tax deadline"

  recall(query) = top-k memories by cos(embed(query), embed(memory))
```

It's a filing cabinet organized by *aboutness* instead of alphabet. Cosine similarity — the angle between vectors — is the standard distance because it ignores magnitude and captures direction-of-meaning.

### Build It
1. On write: `store.append({text, vector: embed(text), ts})`.
2. On recall: embed the query, score against all stored vectors, take top-k above a floor.
3. Brute force is fine for thousands of memories — NumPy dot products are fast. (ANN indexes are a Phase 5 problem.)

```python
import math

def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)); nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb + 1e-9)

def recall(query, store, embed, k=3, floor=0.3):
    qv = embed(query)
    scored = sorted(((cosine(qv, m["vector"]), m) for m in store), reverse=True)
    return [m for s, m in scored[:k] if s > floor]
```

4. The similarity floor matters: without it, top-k returns the *least irrelevant* garbage when nothing truly matches, and the model treats it as gospel.

### Use It
| Store | Sweet spot |
|---|---|
| In-memory list + NumPy | < ~100k memories; zero deps |
| SQLite + sqlite-vec / Chroma | Local persistence, easy start |
| Qdrant / Weaviate / pgvector | Production, filters + scale |
| Embeddings API (OpenAI, Voyage, etc.) | Quality vectors without hosting a model |

Weaknesses to respect: similarity is not *relevance* ("I love dogs" ≠ useful for a food question), and pure vectors miss exact identifiers — hybrid search (Phase 5) covers that flank.

### War Story
Word2vec (Mikolov et al., 2013) delivered the result that made "meaning as geometry" famous: vector arithmetic like *king − man + woman ≈ queen* falling out of unsupervised training. A decade later the same principle — scaled up through sentence encoders and contrastively trained embedding models — became the retrieval backbone of nearly every agent memory and RAG system in production.

### Checkpoint
1. Why does keyword search fail the "dog/retriever" case while vector search succeeds?
2. What failure mode does a similarity floor prevent in top-k recall?
3. Name a query type where vector memory *underperforms* keyword search.

## 05. Episodic vs Semantic Memory

**MOTTO:** "What happened last Tuesday" and "what is true about the user" are different databases.

### The Problem
You dump everything into one memory pile: raw events ("user asked about refunds at 3pm"), and distilled facts ("user manages a Shopify store"). Retrieval turns to mush — queries about *facts* surface stale event logs; queries about *history* surface facts with no timeline. One store, two access patterns, constant interference.

### The Concept
Cognitive science splits human declarative memory the same way (Tulving, 1972). Episodic memory is autobiographical — specific events, time-stamped, contextual: "On July 3 the deploy failed with a TLS error." Semantic memory is general knowledge, detached from when you learned it: "The staging server uses self-signed certs."

```
  EPISODIC (a diary)                    SEMANTIC (an encyclopedia)
  ─ append-only event log              ─ mutable fact store
  ─ keyed by time + session            ─ keyed by subject
  ─ "what happened when?"              ─ "what is true?"
  ─ grows forever, decays in value     ─ small, dense, high-value
            │        distill (async)        ▲
            └───────────────────────────────┘
```

The arrow is the interesting part: semantic facts are *derived* from episodes, the way you remember that a friend is vegetarian long after forgetting the dinner where you learned it.

### Build It
1. Episodic store: append-only JSONL of `{ts, session, role, text}` — cheap, complete, never edited.
2. Semantic store: keyed facts `{subject, fact, confidence, source_episode, updated}` — small and curated.
3. A distiller job (end of session, or every N turns): prompt the LLM with recent episodes → "extract stable facts worth keeping"; upsert into semantic store, updating rather than duplicating.
4. Retrieval routes by question shape: time-ish queries ("last time", "yesterday", "again") → episodic search; identity/preference/config queries → semantic lookup; when unsure, pull a little of both.

```python
def distill(episodes, semantic, llm):
    facts = llm(f"Extract durable facts about the user/project from:\n{render(episodes)}\n"
                "Return JSON: [{subject, fact}]. Skip transient chit-chat.")
    for f in json.loads(facts):
        semantic.upsert(f["subject"], f["fact"], source=episodes[-1]["ts"])
```

### Use It
| Question | Store queried |
|---|---|
| "What did we decide yesterday?" | Episodic |
| "What's my usual deploy target?" | Semantic |
| "Have we hit this error before?" | Episodic (then distill the fix into semantic!) |
| "Who is Priya?" | Semantic (entity view — next lesson) |

Generative Agents (Park et al., 2023) used exactly this layering: an event stream plus periodically synthesized higher-level "reflections."

### War Story
The Generative Agents paper (Park et al., April 2023) put 25 LLM-driven characters in a simulated town, each with an episodic "memory stream" and a reflection process that distilled events into higher-level conclusions. The agents organized a Valentine's Day party from a single seeded intention — invitations spread, and several agents showed up — behavior that emerged from the memory architecture, not from scripting.

### Checkpoint
1. Which store is append-only and which is mutable, and why does that match their contents?
2. What does the distillation step correspond to in the human-memory analogy?
3. Given the query "did we already try downgrading numpy?", which store(s) do you hit and in what order?

## 06. Entity Memory: Tracking People, Places, Things

**MOTTO:** Memories about *someone* should be filed under that someone.

### The Problem
Across sessions the user mentions "Priya" fifteen times: she's a coworker, she owns the API migration, she's out in August, she prefers Slack over email. Vector recall of "message Priya about the deadline" surfaces two of those fragments — the rest are scattered across unrelated conversations, semantically near other things. You have knowledge *about Priya*; you don't have a *Priya record*.

### The Concept
Entity memory is a structured index keyed by the noun: one card per person, project, or system, accumulating facts and relations over time — a CRM your agent keeps for its own world:

```
  ENTITY: Priya (person)
  ├─ role: coworker; owns API migration
  ├─ prefs: Slack > email
  ├─ status: OOO August (noted 2026-07-12)
  └─ relations: works_with → User; owns → api-migration (project)

  mention detected ──► resolve ("she" → Priya) ──► update card
  entity referenced ──► load whole card into context
```

Two hard sub-problems ride along: *extraction* (spotting entity mentions — LLMs are excellent at this) and *resolution* (deciding "Priya", "she", and "P. Sharma" are one entity — genuinely hard, embrace approximate).

### Build It
1. After each exchange, run an extraction prompt: "List entities mentioned and any new facts about each. JSON: `[{name, type, facts[]}]`."
2. Resolve against existing cards — exact name match first, then alias list, then ask-the-LLM for ambiguous cases.
3. Merge facts into the card; keep `last_updated` per fact (staleness matters — lesson 09).
4. On retrieval: scan the incoming user message for known entity names/aliases; inject matching cards into context wholesale. Cards are small; whole-card injection beats fragment recall.

```python
def inject_entities(user_msg, entities):
    hits = [card for name, card in entities.items()
            if name.lower() in user_msg.lower()
            or any(a.lower() in user_msg.lower() for a in card["aliases"])]
    return "\n".join(render_card(c) for c in hits[:5])
```

### Use It
| Approach | Tradeoff |
|---|---|
| LLM extraction per turn | Accurate, costs a call per exchange |
| Batch extraction per session | Cheaper; facts arrive late |
| LangChain-style entity memory | Convenient; resolution is naive |
| Full knowledge graph (nodes + edges) | Powerful relations; real engineering (see GraphRAG, Phase 5) |

Entity cards compose beautifully with the semantic store from lesson 05 — an entity card is just semantic memory with a primary key.

### War Story
When OpenAI rolled out Memory for ChatGPT (announced February 2024, broadly enabled later that year), the user-visible behavior was essentially entity memory about *you*: distilled, editable statements like your profession, preferences, and ongoing projects — not conversation transcripts. The design validated a core lesson: users want memory they can read, correct, and delete, which structured entity records make possible and raw vector stores make hard.

### Checkpoint
1. Why does whole-card injection often beat top-k fragment recall for entity questions?
2. What is entity resolution, and why is it harder than entity extraction?
3. How do entity cards make memory *auditable* in a way embedded fragments aren't?

## 07. The Write Policy: What's Worth Remembering

**MOTTO:** A memory that stores everything is a landfill with a search bar.

### The Problem
Naive systems write every exchange to long-term memory. Within weeks: "user said thanks", "user asked to rephrase", and "user's API key is sk-..." sit alongside the three facts that matter. Retrieval quality drowns in noise, storage of secrets becomes a liability, and one sarcastic "sure, I *love* debugging YAML" becomes a permanent personality profile. Deciding what to write is as important as deciding what to read.

### The Concept
A write policy is a gate between the conversation and the store, scoring each candidate memory on a few axes:

```
  candidate fact ──► [ WRITE POLICY ]──► store / skip / redact
                        │
        durability  ── will this matter next week?
        specificity ── "prefers pytest" vs "likes stuff"
        novelty     ── already stored? update instead of duplicate
        sensitivity ── secrets, health, PII → redact or refuse
        provenance  ── user-stated fact vs model inference
```

The librarian analogy: an archivist doesn't shelve every napkin — they select, deduplicate, label with source and date, and keep restricted material out of the open stacks.

### Build It
1. Generate candidates: after each exchange, ask the LLM "list durable facts, preferences, or decisions from this exchange worth remembering; return [] if none." An empty list must be a common, acceptable answer.
2. Score/filter: drop transient (weather, one-off tasks); drop low-specificity; block a sensitivity list (credentials, government IDs) outright.
3. Deduplicate: before insert, check similarity against existing memories — near-duplicates become *updates* (bump timestamp, merge detail) rather than new rows.
4. Tag provenance: `stated` (user said it) vs `inferred` (model guessed it). Inferred facts get lower confidence and earlier expiry.

```python
def maybe_write(exchange, store, llm):
    cands = json.loads(llm(EXTRACT_PROMPT + render(exchange)))   # often []
    for c in cands:
        if is_sensitive(c["text"]):        continue
        dup = store.most_similar(c["text"])
        if dup and dup.score > 0.9:        store.touch(dup.id, merge=c["text"])
        else:                              store.add(c["text"], src=c["provenance"])
```

5. Let the user see and veto. "I've noted that you prefer X" with a delete affordance beats silent accumulation — for trust *and* for correctness.

### Use It
| Policy | Failure it prevents |
|---|---|
| Durability filter | Landfill of trivia |
| Dedup-as-update | 14 copies of "uses Python" with conflicting details |
| Sensitivity blocklist | Storing secrets you must never store |
| Provenance tags | Model inferences hardening into "facts" |
| User-visible writes | Creepy, wrong, or unwanted memories persisting |

### War Story
Both major assistants converged on selective, visible writes: ChatGPT's Memory shows "Memory updated" notices and gives users a management screen to review and delete entries, and Anthropic's memory-tool guidance similarly emphasizes storing distilled, user-relevant facts rather than transcripts. The convergence is the lesson — every team that ships write-everything memory ends up rebuilding it as write-selectively memory.

### Checkpoint
1. Why must "nothing worth remembering" be a frequent output of the extraction step?
2. What goes wrong when near-duplicate memories are inserted instead of merged?
3. Why should model-inferred facts be stored with different metadata than user-stated ones?

## 08. Memory Retrieval: When to Recall What

**MOTTO:** Perfect memories are useless if they arrive in the wrong turn — or all at once.

### The Problem
You have clean stores: buffer, summary, entities, vectors. Now every turn poses a routing question: should this query trigger recall at all? From which store? How much? Injecting five memories into "hi" is noise; injecting none into "email that thing to the person we discussed" is amnesia. Retrieval that's always-on pollutes; retrieval that's never-on wastes everything you built.

### The Concept
Two architectures, often combined:

```
  IMPLICIT (reflex)                      EXPLICIT (deliberate)
  before every turn:                     memory is a TOOL:
  ┌──────────────────────┐               model decides to call
  │ score query vs stores │               search_memory("Priya deadline")
  │ inject hits > floor   │               when it notices it's missing info
  └──────────────────────┘
  + zero model effort                    + recall matches actual need
  − recalls on "hi", misses              − model must notice the gap
    implicit references                  − costs a turn
```

Implicit retrieval is a reflex — cheap, automatic, sometimes wrong. Explicit retrieval is deliberate recall — the agent notices "the person we discussed" is unresolved and goes looking. Mature systems use a light implicit pass (entities + high-similarity hits only) plus an explicit `search_memory` tool for everything else.

### Build It
1. Implicit pass, per turn: (a) entity scan → inject matched cards; (b) vector recall with a *high* floor (only confident hits); (c) always include the running summary. Budget the whole pass (e.g., ≤ 800 tokens).
2. Explicit tool: register `search_memory(query, store=all|episodic|semantic|entities)` through your Phase 3 router.
3. Placement: inject memories into a labeled system block — `[Recalled memories — may be stale, verify if critical]` — not spliced into user turns; label affects how the model weighs them.
4. Skip heuristics: no implicit recall on greetings, acknowledgments, or when the buffer already contains the answer (check before searching).

```python
def implicit_recall(user_msg, mem, budget=800):
    parts = [mem.summary()]
    parts += [render_card(c) for c in mem.entity_hits(user_msg)]
    parts += [m.text for m in mem.vector_recall(user_msg, k=3, floor=0.45)]
    return truncate_to("\n".join(p for p in parts if p), budget)
```

### Use It
| Situation | Strategy |
|---|---|
| Named entity in query | Implicit card injection |
| Vague reference ("that bug") | Explicit search_memory — model resolves the reference |
| Every turn, always | Running summary only |
| High-stakes fact (address, config) | Explicit recall + ask user to confirm |

### War Story
MemGPT (2023) staked out the explicit end of the spectrum: the model itself issues function calls to page memories in and out of context, deciding when to recall. Retrieval-augmented systems descended from Lewis et al. (2020) staked out the implicit end: retrieve-then-generate on every query, no model decision involved. A half-decade later, production agents almost universally run both — a reflex layer and a recall tool.

### Checkpoint
1. What does implicit retrieval get wrong on the query "hi", and on "email the person we discussed"?
2. Why label injected memories as possibly stale rather than presenting them as ground truth?
3. Why does the explicit-tool approach cost more latency even when it retrieves better?

## 09. Forgetting: Decay, Eviction, and Contradictions

**MOTTO:** A memory system that can't forget will eventually lie to you with its own history.

### The Problem
March: "user works at Acme." July: "just started at Initech!" Your store now holds both, and vector recall happily serves whichever is closer to the query. The agent congratulates the user on their job at Acme. Stale memory isn't a storage cost problem — it's a *correctness* problem: yesterday's truths become today's confident falsehoods, and unbounded stores bury good memories under dead ones.

### The Concept
Three forgetting mechanisms, mirroring how human memory actually stays useful:

```
  DECAY       score = relevance × recency_weight × use_count
              old, never-recalled memories fade from ranking
  EVICTION    hard caps: store full → archive/delete lowest-scoring
  SUPERSESSION new fact contradicts old ──► old marked superseded,
              kept as history, excluded from recall
              "works at Acme" ──X──► superseded_by ──► "works at Initech"
```

Generative Agents (2023) scored memories as relevance + recency + importance — forgetting as *ranking*, not deletion. Supersession is the subtle one: don't delete the contradicted fact (the history "user changed jobs in July" is itself informative); mark it and route recall to the current version.

### Build It
1. Metadata on every memory: `created`, `last_recalled`, `recall_count`, `status: active|superseded|archived`.
2. Decay in the ranking function, not the storage: `score = similarity * exp(-λ * days_since(last_recalled or created))`. Recalling a memory refreshes it — use it or lose it, literally.
3. On every write, check for contradictions: search for high-similarity *active* memories about the same subject; if the LLM judges them incompatible ("can both be true?"), mark the old one `superseded_by=new_id`.
4. Eviction job: past a store cap, archive `active` memories with the lowest decayed scores; never silently delete user-stated facts — archive is reversible.

```python
def write_with_supersession(new, store, llm):
    for old in store.similar(new.text, k=5, status="active"):
        verdict = llm(f"Fact A: {old.text}\nFact B: {new.text}\n"
                      "Can both be true simultaneously? YES/NO, one word.")
        if verdict.strip() == "NO":
            store.mark_superseded(old.id, by=new.id)
    store.add(new)
```

### Use It
| Mechanism | Handles | Doesn't handle |
|---|---|---|
| Recency decay | Gradual staleness | Sudden contradictions |
| Recall-refresh | Keeping used memories alive | First-recall of old-but-true facts |
| Supersession | Job changes, preference flips | Facts that quietly expired with no successor |
| TTL by category | "OOO until August" auto-expiry | Choosing good TTLs |

Give volatile categories (status, location, current project) short TTLs; give stable ones (name, profession) none.

### War Story
The Generative Agents paper (Park et al., 2023) is the canonical demonstration that forgetting-as-ranking works: each agent scored its memory stream by recency, importance, and relevance at retrieval time, letting a bounded context surface the right slice of an ever-growing log. Meanwhile, every long-lived assistant deployment independently discovers the contradiction problem — which is why ChatGPT's memory management UI lets users delete individual memories: manual supersession, shipped as a feature.

### Checkpoint
1. Why is supersession (mark + link) better than deletion for contradicted facts?
2. How does "recall refreshes recency" mimic human memory, and what pathology could it cause?
3. Which memory categories deserve TTLs, and name two with opposite TTL needs.

## 10. Build a Memory System From Scratch

**MOTTO:** Buffer for now, summary for the past, index for the forever — wire all three and ship it.

### The Problem
Ten lessons of parts. Time to assemble a working memory stack with zero dependencies: a windowed buffer (short-term), a rolling summary (compressed past), and keyword-vector recall over a persistent fact store (long-term) — the minimum honest implementation of everything above, in one class you fully understand.

### The Concept
```
                ┌───────────── MemoryAgent ─────────────┐
   user msg ──► │ 1 recall(msg)  → hits from fact store │
                │ 2 build ctx    → summary + hits + buf │──► llm() ──► reply
                │ 3 write        → extract fact? store  │
                │ 4 compact      → over budget? shrink  │
                └───────────┬───────────────────────────┘
                            ▼
                   memory.json  (facts survive restarts)
```

For recall we use TF-IDF-style keyword vectors — real cosine similarity over sparse term vectors, no embedding API needed. It's genuinely the same math as dense vector memory, just with hand-rolled features; swap in an embeddings call later and nothing else changes.

### Build It
```python
import json, math, re, os
from collections import Counter

def tokenize(t): return re.findall(r"[a-z0-9]+", t.lower())

class FactStore:                                   # long-term: keyword-vector recall
    def __init__(self, path="memory.json"):
        self.path = path
        self.facts = json.load(open(path)) if os.path.exists(path) else []
    def add(self, text):
        if not any(self._sim(text, f["text"]) > 0.8 for f in self.facts):  # dedup
            self.facts.append({"text": text}); self._save()
    def recall(self, query, k=3, floor=0.15):
        scored = sorted(((self._sim(query, f["text"]), f) for f in self.facts),
                        key=lambda x: x[0], reverse=True)
        return [f["text"] for s, f in scored[:k] if s > floor]
    def _sim(self, a, b):                          # cosine over term counts, IDF-weighted
        ta, tb = Counter(tokenize(a)), Counter(tokenize(b))
        idf = lambda w: math.log(1 + len(self.facts) / (1 + sum(w in tokenize(f["text"]) for f in self.facts)))
        dot = sum(ta[w] * tb[w] * idf(w) ** 2 for w in ta.keys() & tb.keys())
        na = math.sqrt(sum((c * idf(w)) ** 2 for w, c in ta.items()))
        nb = math.sqrt(sum((c * idf(w)) ** 2 for w, c in tb.items()))
        return dot / (na * nb + 1e-9)
    def _save(self): json.dump(self.facts, open(self.path, "w"))

class MemoryAgent:
    def __init__(self, llm, budget=6000):
        self.llm, self.budget = llm, budget
        self.buffer, self.summary, self.store = [], "", FactStore()
    def chat(self, msg):
        recalled = self.store.recall(msg)
        system = ("[Summary]: " + (self.summary or "none") + "\n"
                  "[Recalled facts — verify if critical]: " + ("; ".join(recalled) or "none"))
        reply = self.llm([{"role": "system", "content": system},
                          *self.buffer, {"role": "user", "content": msg}])
        self.buffer += [{"role": "user", "content": msg},
                        {"role": "assistant", "content": reply}]
        self._write(msg); self._compact()
        return reply
    def _write(self, msg):                          # crude write policy: durable statements only
        fact = self.llm(f"If this states a durable fact/preference, restate it in third "
                        f"person; else reply NONE.\n---\n{msg}")
        if fact.strip() != "NONE": self.store.add(fact.strip())
    def _compact(self):
        if sum(len(m["content"]) for m in self.buffer) // 4 > self.budget:
            old, self.buffer = self.buffer[:-6], self.buffer[-6:]
            self.summary = self.llm("Merge into one 150-word memory summary. Keep goals, "
                                    f"decisions, names.\nPrev: {self.summary}\nNew: {json.dumps(old)}")
```

Test the illusion: tell it your name, chat past the compaction threshold, restart the process, and ask "what's my name?" — the buffer is gone, the process died, and it still knows, via the store.

### Use It
| Component here | Production replacement |
|---|---|
| `FactStore` keyword vectors | Embeddings + Chroma/pgvector |
| `_write` single-prompt policy | Lesson 07's full policy + provenance |
| String summary | Chained compaction w/ pinned facts |
| `memory.json` | SQLite/Postgres + per-user namespacing |
| (missing) supersession | Lesson 09's contradiction check — add it! |

### War Story
The MemGPT paper (2023) closed with the argument this lesson embodies: context limits are an architecture problem, solvable with the same hierarchy tricks operating systems have used since the 1960s. The stack you just wrote — hot buffer, compressed summary, paged-in facts — is a tiny virtual-memory manager for a conversation, and it is structurally the same design running inside every long-lived assistant shipping today.

### Checkpoint
1. Trace what happens to "my name is Sanjay" through recall, context build, write, and compact.
2. Why does swapping keyword vectors for embedding vectors require no change to the recall interface?
3. Which lesson-09 mechanism is missing from this build, and what bug will eventually appear without it?
