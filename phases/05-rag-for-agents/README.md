# Phase 05 — 🔍 RAG for Agents

> The model knows nothing about your data. Fix that at query time.

Your model was trained on the public internet as of some cutoff date — not on your wiki, your codebase, your contracts, or anything from last Tuesday. Retrieval-Augmented Generation fixes this at query time: find the relevant documents, paste them into the context, and let the model answer *from* them instead of from its weights. This phase builds the whole pipeline — chunking, embeddings, indexes, hybrid search, reranking, query rewriting — and then hands the retrieval decision to the agent itself, because for agents, RAG isn't a pipeline bolted on front; it's a tool the agent wields.

## 01. Why RAG: Grounding Beats Fine-Tuning for Facts

**MOTTO:** Don't teach the model your facts — hand it the page and make it read.

### The Problem
"What's our parental leave policy?" The model wasn't trained on your HR docs, so it does what LLMs do with missing knowledge: generates something *plausible*. Fluent, structured, wrong. Your options seem to be fine-tuning (slow, expensive, stale the day after training, and notoriously unreliable at implanting specific facts) or... pasting the entire handbook into every prompt (doesn't fit, costs a fortune).

### The Concept
Split knowledge from reasoning. Keep facts in an external, updatable store; use the model for what it's actually good at — reading and synthesizing:

```
  query ──► RETRIEVER ──► top-k relevant chunks ──► ┌─────────────────────┐
              │                                     │ "Answer using ONLY  │
        document index                              │  these excerpts:"   │──► grounded answer
        (update anytime,                            │  [chunk][chunk][ck] │
         no retraining)                             └─────────────────────┘
```

The open-book exam analogy: fine-tuning is cramming for a closed-book test (lossy, forgets specifics); RAG is an open-book exam (look it up, cite the page). Facts update by editing documents. Answers become auditable — you can check the source. And knowledge can be per-user permissioned, which weights never can.

### Build It
1. Index your documents (lessons 02–05 cover how).
2. At query time, retrieve top-k relevant chunks.
3. Construct the prompt: instruction ("answer only from the excerpts; say 'not found' if absent") + chunks with source labels + question.
4. Generate. The model's job shrinks from "know everything" to "read carefully."

```python
def rag_answer(question, index, llm, k=4):
    chunks = index.retrieve(question, k)
    context = "\n\n".join(f"[{c.source}]\n{c.text}" for c in chunks)
    return llm(f"Answer using ONLY the excerpts below. If the answer isn't "
               f"in them, say so.\n\n{context}\n\nQuestion: {question}")
```

### Use It
| Need | Right tool |
|---|---|
| Current/private/changing facts | RAG |
| Style, format, domain jargon fluency | Fine-tuning |
| Behavior + your facts | Fine-tune style, RAG the facts |
| Small stable corpus, big context window | Sometimes: just paste it all (long-context beats bad retrieval) |

Long-context models shrink RAG's territory but don't eliminate it: cost scales with tokens, corpora scale past any window, and retrieval gives you provenance.

### War Story
The term comes from Lewis et al., "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks" (Facebook AI Research, 2020), which married a dense retriever to a seq2seq generator and beat parametric-only baselines on open-domain QA — while letting the knowledge base be swapped without retraining. The acronym outgrew the paper: by 2023 "RAG" meant the entire retrieve-then-generate pattern that most enterprise LLM deployments still run on.

### Checkpoint
1. Why is fine-tuning a poor mechanism for injecting specific, changing facts?
2. What does RAG give you for auditability that a fine-tuned model cannot?
3. When would "paste the whole corpus into context" legitimately beat RAG?

## 02. Chunking Strategies: Size, Overlap, Structure

**MOTTO:** Retrieval can only find what chunking didn't destroy.

### The Problem
You can't embed a 200-page PDF as one vector (everything averages into mush), and you can't retrieve it as one chunk (blows the context budget). So you split. Split carelessly — every 1,000 characters — and you cut sentences mid-thought, orphan a table from its header, and separate "the penalty is" from "5% per month." The retriever then faithfully returns fragments that are individually meaningless. Garbage chunks in, garbage answers out.

### The Concept
A chunk is the atomic unit of retrieval — it must be *self-contained enough to be understood alone* and *small enough to be about one thing*:

```
  too small: "…is 5% per month."      ← retrievable, incomprehensible
  too big:   [entire 40-page section]  ← comprehensible, dilute vector, budget-hog
  right:     one clause/section/function, with its heading attached

  overlap:   [ chunk 1 ······|■■■ ]
                         [ ■■■|······ chunk 2 ]   ← shared margin so boundary
                                                     sentences live in both
```

Structure beats arithmetic: split at natural seams — headings, paragraphs, functions, table boundaries — and only fall back to fixed sizes inside oversized sections. Recursive splitting formalizes this: try `\n\n## `, then `\n\n`, then `\n`, then sentence, then hard cut.

### Build It
1. Parse structure first (markdown headers, HTML tags, code AST if you have it).
2. Recursively split: if a unit fits the budget (say 200–500 tokens), keep it; else split by the next-finer separator.
3. Add overlap (10–20%) between adjacent fixed-size chunks.
4. Prepend context headers to every chunk — the file name and heading path — so a chunk carries its own provenance.

```python
def recursive_split(text, budget=400, seps=("\n\n", "\n", ". ")):
    if tokens(text) <= budget or not seps:
        return [text]
    parts, out, cur = text.split(seps[0]), [], ""
    for p in parts:
        if tokens(cur + p) > budget:
            if cur: out.extend(recursive_split(cur, budget, seps[1:]) if tokens(cur) > budget else [cur])
            cur = p
        else:
            cur += (seps[0] if cur else "") + p
    if cur: out.append(cur)
    return out

def chunk_doc(doc):
    return [{"text": f"[{doc.title} › {sec.heading}]\n{c}", "source": doc.path}
            for sec in doc.sections for c in recursive_split(sec.text)]
```

### Use It
| Strategy | Best for | Cost |
|---|---|---|
| Fixed size + overlap | Unstructured blobs | Boundary damage |
| Recursive / structural | Docs, markdown, code | Parsing effort |
| Semantic chunking (split at embedding-shift points) | Topic-drifting prose | Embedding calls at index time |
| Contextual enrichment (LLM-written chunk preamble) | High-stakes corpora | LLM call per chunk |

Anthropic's Contextual Retrieval write-up (2024) reported large retrieval-failure reductions from prepending LLM-generated context to each chunk before embedding — the "chunks must stand alone" principle, automated.

### War Story
Anthropic's "Contextual Retrieval" engineering post (September 2024) quantified the orphaned-chunk problem: a chunk saying "the company's revenue grew 3%" is unfindable when the query names the company, because the chunk doesn't. Prepending a short LLM-generated context blurb to each chunk before embedding and indexing cut retrieval failure rates dramatically in their published benchmarks — chunking, not the embedding model, was the bottleneck.

### Checkpoint
1. Why does an over-large chunk hurt retrieval even though it contains the answer?
2. What problem does overlap solve, and what does it cost?
3. Why does prepending the heading path to each chunk improve *retrieval*, not just readability?

## 03. Embeddings: Meaning as Geometry

**MOTTO:** An embedding model is a cartographer that maps every sentence onto the same globe — nearby means alike.

### The Problem
"How do I get my money back?" needs to match a document titled "Refund Policy." Zero shared words. Keyword search is blind here; you need a representation where *reimbursement*, *refund*, and *money back* land near each other — where similarity of meaning is computable.

### The Concept
An embedding model maps text to a fixed-length vector (typically 384–3072 floats) such that semantically similar texts get geometrically close vectors. Similarity becomes arithmetic:

```
   "refund my purchase"  ●●  "get my money back"        cos ≈ 0.86
                                                        
   "refund my purchase"  ●
                              …far away…
                         ● "install the GPU driver"     cos ≈ 0.07

   cos(a, b) = (a · b) / (|a||b|)   ← angle between meanings
```

These models are trained contrastively: pull paired texts (question/answer, sentence/paraphrase) together, push unrelated ones apart, over billions of pairs. Cosine similarity is standard; most APIs return unit-normalized vectors, making cosine just a dot product. Caveats that bite in practice: embeddings blur negation ("include tax" ≈ "exclude tax"), mangle rare exact identifiers (`ERR_QX_314`), and each model has its own incompatible space — never mix vectors from two models in one index.

### Build It
1. Embed every chunk at index time; store `(vector, text, source)`.
2. Embed the query at search time *with the same model* (some models want a query/document prefix — respect it).
3. Score by dot product, return top-k.

```python
import numpy as np

class DenseIndex:
    def __init__(self, embed):
        self.embed, self.vecs, self.meta = embed, [], []
    def add(self, chunks):
        for c in chunks:
            v = np.array(self.embed(c["text"]))
            self.vecs.append(v / np.linalg.norm(v)); self.meta.append(c)
    def search(self, query, k=5):
        q = np.array(self.embed(query)); q /= np.linalg.norm(q)
        sims = np.stack(self.vecs) @ q                 # cosine via dot product
        top = np.argsort(-sims)[:k]
        return [(float(sims[i]), self.meta[i]) for i in top]
```

Brute force over a matrix is exact and fast into the hundreds of thousands of vectors — don't reach for an ANN index before you need one (lesson 04).

### Use It
| Model class | Examples | Tradeoff |
|---|---|---|
| API embeddings | OpenAI text-embedding-3, Voyage, Cohere | Quality + zero ops; per-token cost, data leaves house |
| Open local | BGE, GTE, E5, sentence-transformers | Free, private; you host it |
| Small/fast | MiniLM (384-dim) | Speed; noticeably weaker recall |
| Benchmark | MTEB leaderboard | Rankings shift; test on *your* data |

Dimensions trade storage/speed against fidelity; Matryoshka-trained models let you truncate vectors and keep most quality.

### War Story
Word2vec (Mikolov et al., 2013) proved meaning could live in vector arithmetic — *king − man + woman ≈ queen* — but word vectors couldn't handle sentences. Sentence-BERT (Reimers & Gurevych, 2019) fixed that with siamese fine-tuning, cutting sentence-similarity search from BERT's pairwise hours to milliseconds of vector comparison, and effectively founding the modern embedding-model lineage every RAG system depends on.

### Checkpoint
1. Why must the query and the documents be embedded by the same model?
2. Give two query types where embeddings systematically underperform keyword search.
3. Why is cosine similarity equivalent to a dot product for normalized vectors?

## 04. Vector Databases and ANN Search

**MOTTO:** Exact nearest-neighbor search scales linearly; your patience doesn't.

### The Problem
Brute-force search compares the query to every vector: fine at 100k, painful at 10 million, impossible at 50 QPS on a billion. And high-dimensional space is cruel — there's no equivalent of a B-tree for 1024 dimensions (the "curse of dimensionality" defeats classic spatial indexes). You need approximate search: trade a sliver of recall for orders of magnitude in speed.

### The Concept
HNSW (Hierarchical Navigable Small World, Malkov & Yashunin, 2016) — the workhorse ANN index — is a multi-level skip-list over a proximity graph. Think of navigating to an address: motorways first, then A-roads, then streets:

```
  Layer 2:  A ─────────────── F            few nodes, long hops (motorways)
             \                 │
  Layer 1:  A ──── C ──── E ─ F            more nodes, shorter hops
             \     │      │    │
  Layer 0:  A─B─C─D─E─F─G─H─…              every vector, local links (streets)

  search: enter at top layer, greedily hop toward the query,
          drop a layer, repeat → land in the right neighborhood in O(log N) hops
```

Each vector gets linked to ~M near neighbors per layer; upper layers sample exponentially fewer nodes. Greedy routing from the top finds the true neighborhood with high probability — "approximate" means occasionally missing a true neighbor, tunable via the search-width parameter (`ef`).

### Build It
Build a navigable graph in miniature — one layer, greedy search, to feel the mechanism:
1. Insert: link each new vector to its M nearest existing nodes (found via the same greedy search).
2. Search: start anywhere, repeatedly move to the neighbor closest to the query; keep a best-so-far beam of size `ef`; stop when no neighbor improves.

```python
def greedy_search(graph, vecs, query, entry, ef=8):
    import heapq
    visited, best = {entry}, [(-sim(vecs[entry], query), entry)]
    candidates = list(best)
    while candidates:
        d, node = heapq.heappop(candidates)
        if -d < -best[0][0] and len(best) >= ef: break
        for nb in graph[node]:
            if nb not in visited:
                visited.add(nb)
                heapq.heappush(candidates, (-sim(vecs[nb], query), nb))
                heapq.heappush(best, (-sim(vecs[nb], query), nb))
                best = heapq.nsmallest(ef, best)
    return sorted(best)
```

3. Note the tradeoffs you now own: bigger `M`/`ef` → better recall, more memory, slower inserts. This is the dial every vector DB exposes.

### Use It
| Option | Sweet spot | Notes |
|---|---|---|
| NumPy brute force | < ~500k vectors | Exact; start here, seriously |
| FAISS / hnswlib | Library, in-process | You manage persistence |
| Chroma / LanceDB | Local dev, embedded DB | Batteries included |
| pgvector | Data already in Postgres | HNSW + SQL filters + joins |
| Qdrant / Weaviate / Milvus / Pinecone | Scale, filters, ops | Server (or SaaS) to run |

Metadata filtering ("only docs where team=finance") is the feature that actually differentiates vector *databases* from vector *indexes* — and pre-filter vs post-filter semantics matter for recall.

### War Story
The HNSW paper (Malkov & Yashunin, 2016) came out of Novosibirsk well before the LLM boom, targeting classic nearest-neighbor workloads. When RAG exploded in 2023, HNSW was sitting there ready and became the default index in nearly every vector database — while a 2021 Google-era alternative (ScaNN) and IVF-PQ variants competed on the billion-scale end. A five-figure-citation reminder that infrastructure often predates its killer app.

### Checkpoint
1. Why do B-tree-style exact indexes fail in 1024 dimensions?
2. In HNSW, what do the upper layers buy you, and what does raising `ef` trade?
3. When is brute-force exact search the *correct* engineering choice over ANN?

## 05. Hybrid Search: Dense + Sparse (BM25)

**MOTTO:** Embeddings know what you mean; BM25 knows what you typed. Ask both.

### The Problem
A user searches for `error QX-1147 in load_batch()`. Dense retrieval returns chunks about error handling *in general* — semantically adjacent, useless. Exact tokens like error codes, function names, SKUs, and legal clause numbers are precisely what embeddings blur away. Meanwhile keyword search, which nails those, whiffs on "how do I get reimbursed" → "Refund Policy." Each retriever fails where the other shines.

### The Concept
Run both, merge the rankings:

```
  query ──┬─► DENSE (embeddings) ──► ranked list A   (meaning)
          └─► SPARSE (BM25)      ──► ranked list B   (exact terms)
                          │
                    RRF merge: score(d) = Σ 1/(60 + rank_i(d))
                          │
                          ▼
                final ranking — strong in either list ⇒ strong overall
```

BM25 is the battle-tested keyword ranker (Robertson et al., born of the TREC era, default in Elasticsearch/Lucene): a term-frequency × inverse-document-frequency score with saturation (the 10th occurrence of a word adds little) and length normalization (long docs don't win by verbosity). Reciprocal Rank Fusion (RRF) merges the two lists using only *ranks*, sidestepping the fact that cosine scores and BM25 scores live on incomparable scales.

### Build It
1. BM25 score for doc D given query q: `Σ_t IDF(t) · tf(t,D)·(k1+1) / (tf(t,D) + k1·(1 − b + b·|D|/avgdl))`, with k1≈1.5, b≈0.75.
2. Build an inverted index: `term → [(doc_id, tf)]` — that's what makes sparse search fast.
3. Query both indexes, then RRF:

```python
def bm25_idf(term, N, df): return math.log((N - df + 0.5) / (df + 0.5) + 1)

def rrf(rankings, k=60):
    scores = {}
    for ranking in rankings:                       # each: ordered list of doc_ids
        for rank, doc in enumerate(ranking):
            scores[doc] = scores.get(doc, 0) + 1 / (k + rank + 1)
    return sorted(scores, key=scores.get, reverse=True)

final = rrf([dense.search(q, 20), sparse.search(q, 20)])[:5]
```

4. `k=60` is the paper's constant and nobody's bothered to change it — it damps the difference between rank 1 and rank 3 so one retriever's overconfidence can't dominate.

### Use It
| Setup | Notes |
|---|---|
| Elasticsearch/OpenSearch + kNN | BM25 native, dense bolted on; one system |
| Qdrant/Weaviate hybrid mode | Vector-first with sparse support built in |
| pgvector + Postgres FTS | Both in SQL; DIY fusion |
| `rank_bm25` (Python) + your dense index | From-scratch friendly |
| Learned sparse (SPLADE) | Term expansion, sparse speed; needs its own model |

Hybrid is the boring, reliable win: on mixed workloads it beats either retriever alone often enough that most production RAG defaults to it.

### War Story
BM25 dates to the Okapi system and TREC-3 (Robertson et al., 1994) — it is old enough to have grandchildren. When the BEIR benchmark (Thakur et al., 2021) evaluated dense retrievers across 18 heterogeneous datasets, plain BM25 remained a brutally strong zero-shot baseline, beating many neural retrievers out of domain. Three decades on, the right answer is still "use both."

### Checkpoint
1. Which query characteristics predict dense failure, and which predict sparse failure?
2. Why does RRF merge on ranks instead of raw scores?
3. What do BM25's saturation and length-normalization terms each prevent?

## 06. Reranking: The Second-Stage Filter

**MOTTO:** Retrieve with a net, rerank with tweezers.

### The Problem
Your top-20 from hybrid search contains the answer... at position 14. First-stage retrievers must be fast, so they compress every document into one vector (or a bag of terms) *before ever seeing the query* — a lossy summary scored blind. Send top-5 to the model and you miss the answer; send top-20 and you stuff the context with noise the model must wade through (and, per "lost in the middle," may ignore).

### The Concept
A reranker is a slower, smarter judge applied only to the shortlist. The architectural difference is *when* the query meets the document:

```
  BI-ENCODER (stage 1)                    CROSS-ENCODER (stage 2)
  doc ──► [encoder] ──► vec ┐             ┌──────────────────────────┐
                            ├─ cos ──►    │ [query ⊕ doc] ──► score  │
  qry ──► [encoder] ──► vec ┘             │ full attention between   │
  fast: docs precomputed                  │ every query & doc token  │
  blind: doc encoded without query        └──────────────────────────┘
                                          accurate, but O(1 forward pass
                                          per candidate) — shortlist only

  1M docs ──[stage 1: ms]──► top 50 ──[stage 2: ~100ms]──► top 5 ──► LLM
```

Recruiting analogy: stage 1 is keyword-screening a thousand résumés; stage 2 is actually interviewing the shortlist. You'd never interview everyone, and you'd never hire off a keyword screen.

### Build It
1. Over-retrieve: pull 3–10× more candidates than you'll keep (top 50 for a final 5).
2. Score each `(query, candidate)` pair with a cross-encoder — or, in a pinch, an LLM prompt: "Rate 0–10 how well this passage answers the question. Passage: … Question: … Score:".
3. Re-sort by reranker score; keep top-k; optionally drop candidates under an absolute floor (relevance, not just rank).

```python
def rerank(query, candidates, scorer, k=5, floor=0.3):
    scored = [(scorer(query, c.text), c) for c in candidates]   # the expensive loop
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for s, c in scored[:k] if s >= floor]
```

4. Latency math: 50 candidates × ~2–5ms each on GPU (or one batched call) ≈ tens of ms — almost always worth it before a multi-second LLM generation.

### Use It
| Reranker | Tradeoff |
|---|---|
| Cross-encoder (BGE-reranker, MiniLM CE) | Strong, self-hosted, GPU-happy |
| Cohere Rerank / Voyage rerank APIs | One HTTP call; per-query cost |
| LLM-as-reranker (listwise prompt) | No new model; slow, pricey, surprisingly good |
| ColBERT (late interaction) | Middle ground: token vectors precomputed, cheap MaxSim at query time |

Diminishing returns warning: reranking can't rescue what stage 1 never retrieved. Fix recall first (better chunks, hybrid), then precision (rerank).

### War Story
When the MS MARCO passage-ranking leaderboard era began (dataset released 2016, deep-learning track ~2018–2019), BERT cross-encoder rerankers (Nogueira & Cho, 2019) delivered one of the largest single jumps in IR benchmark history over BM25-era baselines — establishing the retrieve-then-rerank pattern as standard. ColBERT (Khattab & Zaharia, SIGIR 2020) then showed you could keep most of that accuracy at a fraction of the query cost via late interaction.

### Checkpoint
1. Why can a cross-encoder outscore a bi-encoder on the same pair — what does it see that the bi-encoder can't?
2. Why is reranking applied to 50 candidates rather than the whole corpus?
3. Your reranked top-5 is still wrong. Why might the fix live in stage 1, not the reranker?

## 07. Query Rewriting and Decomposition

**MOTTO:** Users ask questions; retrievers need queries — someone has to translate.

### The Problem
User: "that didn't work either, any other ideas?" Embed *that* and you retrieve chunks about things not working. The real query — "alternative fixes for CUDA out-of-memory during fine-tuning" — lives in the conversation history, not the message. Other queries are retrievable but *compound*: "Compare our 2023 and 2024 refund policies" needs two different retrievals; no single vector nails both.

### The Concept
Insert a translation layer between the user and the retriever — an LLM that turns conversational, vague, or compound inputs into one or more sharp, standalone queries:

```
  "that didn't work either"
        │  REWRITE (+ history)
        ▼
  "alternative fixes for CUDA OOM when fine-tuning"      ← contextualized

  "compare 2023 vs 2024 refund policy"
        │  DECOMPOSE
        ├──► "refund policy 2023"   ──► retrieve ┐
        └──► "refund policy 2024"   ──► retrieve ┴──► merged context ──► answer
```

Three standard moves: **contextualize** (fold conversation history into a standalone query), **decompose** (split multi-part questions into sub-queries, retrieve each), and **expand** (generate paraphrases / a hypothetical answer and retrieve with those too — HyDE, Gao et al. 2022, embeds a *fake answer* because answers live nearer to documents than questions do).

### Build It
1. Rewrite prompt: "Given the conversation and the latest message, write 1–3 standalone search queries that would retrieve the needed information. JSON list."
2. Retrieve per query (in parallel — Phase 3, lesson 03), dedupe by chunk id, then RRF-merge or rerank the union.
3. Skip the rewrite when it's useless: single-turn, self-contained queries go straight through. A cheap heuristic (pronouns/ellipsis/anaphora present? multi-part?) or a tiny classifier gates the extra LLM call.

```python
def smart_retrieve(msg, history, index, llm, k=5):
    queries = json.loads(llm(REWRITE_PROMPT.format(history=history[-6:], msg=msg)))
    seen, pool = set(), []
    for q in queries:
        for c in index.retrieve(q, k):
            if c.id not in seen:
                seen.add(c.id); pool.append(c)
    return rerank(msg, pool, k=k)          # rerank against the ORIGINAL message
```

4. Note the last line: rewritten queries drive *retrieval*, but the original user intent drives *ranking* — rewrites can drift, and this catches it.

### Use It
| Technique | Fixes | Cost |
|---|---|---|
| Contextualization | Follow-ups, pronouns | 1 small LLM call |
| Decomposition | Compare/multi-hop questions | N retrievals |
| Multi-query expansion | Vocabulary mismatch | N retrievals + merge |
| HyDE | Question↔document gap | 1 generation + embed |
| Step-back prompting | Over-specific queries | 1 LLM call |

This is the single highest-leverage upgrade for chat-over-docs products — most "RAG is broken" complaints are actually "we embedded the raw follow-up message."

### War Story
The HyDE paper (Gao et al., 2022) formalized a counterintuitive trick: ask the LLM to hallucinate an answer, then embed the *hallucination* and search with it. The fake answer is factually unreliable but *distributionally* correct — it sounds like the documents you want — and it improved zero-shot dense retrieval across benchmarks. A rare case of hallucination deployed as a feature.

### Checkpoint
1. Why does embedding a follow-up message like "why not?" fail, mechanically?
2. Why rerank against the original message rather than the rewritten query?
3. What insight makes HyDE work despite the generated answer being unreliable?

## 08. Agentic RAG: Retrieval as a Tool Decision

**MOTTO:** Stop bolting retrieval onto every query — hand the agent a search tool and let it decide.

### The Problem
Classic RAG is a fixed pipeline: every input triggers exactly one retrieve-then-generate pass. So "thanks, looks good!" triggers a pointless (and possibly misleading) retrieval, while a genuinely hard question gets one shot — if the first retrieval misses, the model answers from bad context with no chance to try a different query. A pipeline can't decide, and can't iterate. An agent can do both.

### The Concept
Flip the architecture: retrieval stops being a stage in front of the model and becomes a *tool* the model calls — zero, one, or many times — inside the agent loop you built in Phase 3:

```
  PIPELINE RAG:  query ─► retrieve ─► generate           (always, once)

  AGENTIC RAG:   query ─► agent loop:
                   ├─ answer directly            (no retrieval needed)
                   ├─ search("refund policy")    → judge results…
                   ├─   thin? → search("reimbursement terms 2024")   (reformulate!)
                   ├─   compound? → search A, search B               (decompose!)
                   └─ generate, grounded in accumulated evidence
```

The agent gains three abilities pipelines lack: **deciding whether** to retrieve, **judging** result quality and retrying with a better query, and **chaining** retrievals for multi-hop questions ("who manages the team that owns billing?" — find the team, then its manager).

### Build It
1. Wrap your retriever as a Phase-3 tool: `search_docs(query: str, k: int=5) -> chunks`. The description is load-bearing: "Search internal documents. Call multiple times with reformulated queries if results look irrelevant. Prefer specific queries over broad ones."
2. Return results *with scores and sources* so the model can judge thinness.
3. System prompt sets the policy: "Answer from your own knowledge for general questions. For anything about [corpus domain], you MUST ground answers in search_docs results. If results don't answer the question, reformulate and search again, up to 3 times, then say what you couldn't find."
4. Cap it: a max-searches-per-turn limit prevents the agent from spelunking forever.

```python
@tool
def search_docs(query: str, k: int = 5) -> str:
    """Search company documents. If results look irrelevant, call again
    with a reformulated, more specific query (max 3 attempts)."""
    hits = rerank(query, index.retrieve(query, k * 4), k=k)
    if not hits:
        return "No relevant documents found. Try different terms."
    return "\n\n".join(f"[{h.source} | score={h.score:.2f}]\n{h.text}" for h in hits)
```

### Use It
| Pattern | When |
|---|---|
| Pipeline RAG | High-volume, uniform queries (support deflection); cheapest, most predictable |
| Agentic single-tool | Mixed chit-chat + knowledge queries |
| Agentic multi-source | Several corpora/tools: docs, tickets, web — agent routes |
| Self-reflective loops (Self-RAG-style, 2023) | Model critiques retrievals/its own answer; +quality, +latency |

Tradeoff in one line: pipelines are cheap and predictable; agents are adaptive and unbounded. Latency-sensitive products often run a pipeline with an agentic fallback for hard queries.

### War Story
The research arc is visible in the papers: Self-RAG (Asai et al., 2023) trained models to emit reflection tokens deciding *when* to retrieve and critiquing what came back, and FLARE (Jiang et al., 2023) retrieved actively mid-generation whenever the model's next-sentence confidence dropped. Production tooling converged the same way from the engineering side — retrieval as a callable tool in an agent loop is now the default architecture in agent frameworks.

### Checkpoint
1. Name the three capabilities agentic RAG adds over pipeline RAG.
2. Why must search results include sources and scores when retrieval is a tool?
3. When is dumb pipeline RAG still the right architecture?

## 09. GraphRAG and Structured Knowledge

**MOTTO:** Vector search finds passages; some questions need the map, not the pages.

### The Problem
"Which of our projects depend on the payments service?" The answer isn't *in* any chunk — it's smeared across forty documents, one dependency mention at a time. Similarly, "what are the main themes across all customer interviews?" defeats top-k retrieval by construction: k chunks can't summarize a thousand. Vector RAG answers *local* questions (the answer sits in a few passages); it structurally cannot answer *global* or *relational* ones.

### The Concept
Extract structure at index time — entities and relations — into a knowledge graph, and retrieve *subgraphs* instead of (or alongside) chunks:

```
  docs ──LLM extraction──►  (ProjectA) ─depends_on─► (Payments) ◄─owns─ (Team Rho)
                                 │                        ▲
                             uses│                        │depends_on
                                 ▼                        │
                             (Postgres)              (ProjectB)

  relational query ──► graph traversal ──► "ProjectA and ProjectB depend on Payments"
  global query     ──► community summaries (pre-computed per cluster) ──► themes
```

Microsoft's GraphRAG (2024) adds the second trick: cluster the graph into communities (Leiden algorithm), pre-summarize each community with an LLM at index time, and answer global "what are the themes" questions from those summaries — map-reduce over a knowledge graph.

### Build It
1. Extraction pass per chunk: "List entities (name, type) and relations (source, relation, target) as JSON." Merge across chunks; resolve duplicate entities (the hard part — normalize names, use aliases).
2. Store triples; SQLite is fine: `edges(src, rel, dst, source_chunk)`.
3. Query time, three retrieval modes: (a) local — match query entities, expand 1–2 hops, verbalize the subgraph into context; (b) global — retrieve community summaries; (c) hybrid — subgraph + supporting chunks (keep `source_chunk` pointers so every edge can cite its evidence).

```python
def local_graph_retrieve(query, graph, hops=2):
    seeds = [e for e in graph.entities if e.name.lower() in query.lower()]
    sub = graph.expand(seeds, hops)
    return "\n".join(f"{s} —{r}→ {t}  (source: {src})" for s, r, t, src in sub.edges)
```

### Use It
| Question shape | Best tool |
|---|---|
| "What does the policy say about X?" | Plain vector RAG |
| "How is A connected to B?" | Graph traversal |
| "Summarize themes across the corpus" | Community summaries |
| Entity-heavy corpora (orgs, codebases, contracts) | Graph + chunks hybrid |

Costs to respect: extraction is an LLM call per chunk (indexing gets expensive), entity resolution is never fully solved, and the graph goes stale unless re-extraction is in your update path. GraphRAG is a scalpel, not a default.

### War Story
Microsoft Research released GraphRAG in 2024 (paper: Edge et al., "From Local to Global") with an honest framing: baseline RAG *fails* on query-focused summarization over whole corpora, and their entity-graph + community-summary approach substantially beat vector RAG on comprehensiveness and diversity of answers for exactly those global questions. The open-source release triggered a wave of graph-flavored RAG variants — and an equally useful wave of "you probably don't need it for local questions" follow-ups.

### Checkpoint
1. Why can't top-k chunk retrieval answer corpus-wide thematic questions, regardless of k?
2. What do community summaries precompute, and which query class do they serve?
3. Why keep `source_chunk` provenance on every extracted edge?

## 10. Citations and Faithfulness

**MOTTO:** An answer you can't trace to a source is a hallucination with good posture.

### The Problem
Your RAG system retrieves the right chunks — and the model answers with a blend of the chunks and its pretraining, seasoned with plausible invention. The user can't tell which sentences are grounded. Worse, RAG *increases* misplaced trust: "it searched our docs, so it must be right." Grounding isn't automatic; retrieval puts evidence in the room, but nothing yet forces the model to use it — or admit when it can't.

### The Concept
Two properties, enforced separately: **faithfulness** — every claim in the answer is supported by retrieved context — and **attribution** — each claim points at its supporting source:

```
  chunks in ──► [1] refund-policy.md  [2] terms-2024.md  [3] faq.md
  answer out:  "Refunds are allowed within 30 days [1]. Digital goods
                are excluded [2]. Shipping costs are not refunded [1]."
                                          │
                verify: for each sentence, does the cited chunk entail it?
                sentence with no support ──► flag / strip / regenerate
```

Mechanics that make it work: number the chunks in the prompt, instruct sentence-level citation, explicitly authorize refusal ("if the excerpts don't contain the answer, say so — this is a correct answer, not a failure"), and — for high stakes — verify claims *post-hoc* with an entailment check. The refusal instruction matters most: a model not offered "not found" as an option will always find something.

### Build It
1. Prompt with numbered sources and citation rules; require `[n]` after each factual sentence.
2. Parse citations from the answer; any factual sentence without one is suspect.
3. Verify (high-stakes mode): for each (sentence, cited chunk) pair, ask a cheap model "Does the passage support the claim? SUPPORTED / NOT_SUPPORTED." Strip or flag failures; regenerate if too many fail.

```python
CITE_PROMPT = """Answer using ONLY the numbered excerpts. After every factual
sentence, cite its source like [2]. If the excerpts don't contain the answer,
reply exactly: "Not found in the provided documents."

{numbered_chunks}

Question: {q}"""

def verify(answer, chunks, judge):
    for sent, refs in parse_citations(answer):
        if not refs:
            yield sent, "UNCITED"
        elif not any(judge(chunks[r], sent) == "SUPPORTED" for r in refs):
            yield sent, "UNSUPPORTED"
```

4. UX detail with outsized impact: render citations as clickable snippets showing the actual source text — users catch model errors your verifier misses.

### Use It
| Mechanism | Strength | Cost |
|---|---|---|
| Prompted `[n]` citations | Easy, decent | Model can cite wrong chunk |
| Anthropic Citations API / grounded-generation APIs | Spans tied to sources at generation time | Provider-specific |
| Post-hoc NLI/LLM verification | Catches fabrication | Extra calls, latency |
| "Not found" refusal path | Kills the worst failure | Users must accept "no answer" |

### War Story
GopherCite (Menick et al., DeepMind, 2022) trained a model via RLHF to answer with verbatim supporting quotes and — crucially — to *decline* to answer when unsure, boosting the rate of plausible-and-supported answers on NaturalQuestions substantially. Its sobering finding presaged today's practice: citation improves but does not guarantee correctness — models can quote accurately from sources that don't actually settle the question.

### Checkpoint
1. Distinguish faithfulness from attribution — can an answer have one without the other?
2. Why does explicitly authorizing "not found" reduce hallucination?
3. What class of error survives even perfect citation formatting, per GopherCite's findings?

## 11. RAG Evaluation: Retrieval and Generation Metrics

**MOTTO:** If you didn't measure retrieval separately from generation, you don't know which half is broken.

### The Problem
"The RAG bot gave a wrong answer." Was the right chunk never retrieved (retrieval failure)? Retrieved but ranked 9th and ignored (ranking failure)? In context but contradicted by the model (faithfulness failure)? Each has a different fix — better chunking, a reranker, a stronger prompt — and eyeballing outputs can't tell them apart. Un-decomposed evals produce vibes, and vibes don't regress-test.

### The Concept
Evaluate the stages independently, then end-to-end:

```
  RETRIEVAL (needs: query → relevant-chunk labels)
    recall@k   = fraction of queries where a relevant chunk is in top k
    precision@k= fraction of top k that are relevant
    MRR        = mean(1 / rank of first relevant result)
                 first hit at rank 1 → 1.0; rank 3 → 0.33; miss → 0
    nDCG@k     = graded relevance, discounted by log(rank)

  GENERATION (needs: judge — human or LLM)
    faithfulness      = claims supported by retrieved context?
    answer relevance  = does it address the question?
    correctness       = matches gold answer? (needs gold answers)
```

Recall@k is the metric to watch first: if the evidence isn't in the top k, *nothing downstream can save you* — it's the ceiling on the whole system. MRR then tells you whether the evidence arrives near the top, where the model actually attends.

### Build It
1. Build a golden set: 50–200 real queries, each labeled with relevant chunk IDs (label with an LLM, verify by hand — tedious, non-negotiable).
2. Compute retrieval metrics per configuration; this is now your regression suite for every chunking/embedding/reranker change.
3. Generation: score faithfulness by claim-decomposition — split the answer into atomic claims, judge each against the retrieved context (this is what RAGAS-style tooling automates).

```python
def eval_retrieval(golden, retriever, k=5):
    hits, rr = 0, 0.0
    for q in golden:
        got = [c.id for c in retriever(q["query"], k)]
        rel = set(q["relevant_ids"])
        if rel & set(got): hits += 1
        ranks = [i + 1 for i, cid in enumerate(got) if cid in rel]
        rr += 1 / ranks[0] if ranks else 0
    n = len(golden)
    return {"recall@k": hits / n, "MRR": rr / n}
```

4. Read the matrix diagnostically: low recall@k → fix chunking/embeddings/hybrid; good recall, low MRR → add reranking; good retrieval, bad answers → fix prompt/faithfulness/model.

### Use It
| Tool | Covers | Note |
|---|---|---|
| Hand-rolled golden set (above) | Retrieval metrics | Start here; you own it |
| RAGAS | Faithfulness, relevance, context metrics | LLM-judged; validate the judge |
| TREC/BEIR-style harnesses | Retriever benchmarking | Public data ≠ your data |
| LangSmith / Braintrust / Arize | Tracing + eval infra | Ops layer, not metrics theory |

LLM-as-judge caveat: judges have biases (verbosity, position, self-preference — documented in Zheng et al.'s MT-Bench/Chatbot Arena paper, 2023). Spot-check the judge against humans before trusting the dashboard.

### War Story
The BEIR benchmark (Thakur et al., 2021) delivered the field's favorite cautionary tale: dense retrievers that dominated in-domain (MS MARCO) evaluation were beaten by 1994-vintage BM25 on many out-of-domain datasets. The lesson generalizes to every RAG deployment: a retriever's leaderboard score is not its score on *your* corpus — which is why the golden set you hand-label this week outvalues every published benchmark.

### Checkpoint
1. Why is recall@k the ceiling metric for an entire RAG system?
2. Good recall@10, terrible MRR — what's the diagnosis and the standard fix?
3. Why must an LLM judge itself be evaluated before its scores are trusted?

## 12. Build a RAG Pipeline From Scratch

**MOTTO:** One index, one retriever, one prompt, zero dependencies — earn your abstractions.

### The Problem
You've studied every stage. Frameworks will now happily hide them all behind `RetrievalQA.from_chain_type(...)` — and when relevance is bad, you won't know if it's the chunker, the scorer, or the prompt. So: a complete pipeline — chunk, index (TF-IDF), retrieve (cosine), generate with citations — in pure stdlib Python. Small enough to read in one sitting, real enough to answer questions over actual files.

### The Concept
```
  *.md files ─► chunk (paragraphs, ~1200 chars) ─► TF-IDF vectors ─► index
                                                                       │
  question ─► TF-IDF vector ─► cosine top-k ─► numbered context ─► prompt ─► cited answer
```

TF-IDF is the honest stand-in for embeddings: each chunk becomes a sparse vector of term weights — `tf × idf`, where idf up-weights rare, discriminative words — and retrieval is the same cosine-similarity ranking you'd run over dense vectors. Sparse features, identical machinery: swap `_vectorize` for an embeddings call and the pipeline is production-shaped.

### Build It
```python
import json, math, os, re, sys
from collections import Counter

def tokenize(text):
    return re.findall(r"[a-z0-9]+", text.lower())

def chunk_file(path, max_chars=1200):
    text = open(path, encoding="utf-8").read()
    paras, chunks, cur = text.split("\n\n"), [], ""
    for p in paras:
        if len(cur) + len(p) > max_chars and cur:
            chunks.append(cur.strip()); cur = ""
        cur += p + "\n\n"
    if cur.strip(): chunks.append(cur.strip())
    return [{"source": os.path.basename(path), "text": c} for c in chunks]

class TfidfIndex:
    def __init__(self):
        self.chunks, self.vecs, self.df, self.N = [], [], Counter(), 0
    def build(self, chunks):
        self.chunks, self.N = chunks, len(chunks)
        toks = [Counter(tokenize(c["text"])) for c in chunks]
        for t in toks: self.df.update(t.keys())
        self.vecs = [self._vectorize(t) for t in toks]
    def _idf(self, w):
        return math.log(1 + self.N / (1 + self.df.get(w, 0)))
    def _vectorize(self, tf):
        v = {w: (1 + math.log(c)) * self._idf(w) for w, c in tf.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {w: x / norm for w, x in v.items()}          # unit vector
    def retrieve(self, query, k=4, floor=0.05):
        q = self._vectorize(Counter(tokenize(query)))
        scored = []
        for i, v in enumerate(self.vecs):                    # cosine = dot (both unit)
            s = sum(q[w] * v[w] for w in q.keys() & v.keys())
            scored.append((s, i))
        scored.sort(reverse=True)
        return [(s, self.chunks[i]) for s, i in scored[:k] if s > floor]

PROMPT = """Answer using ONLY the numbered excerpts. Cite like [1] after each
factual sentence. If the excerpts don't contain the answer, say
"Not found in the indexed documents."

{context}

Question: {question}
Answer:"""

def answer(question, index, llm, k=4):
    hits = index.retrieve(question, k)
    if not hits:
        return "Not found in the indexed documents.", []
    context = "\n\n".join(f"[{i+1}] (source: {c['source']})\n{c['text']}"
                          for i, (s, c) in enumerate(hits))
    return llm(PROMPT.format(context=context, question=question)), hits

if __name__ == "__main__":
    index = TfidfIndex()
    docs = [c for f in sys.argv[1:] for c in chunk_file(f)]
    index.build(docs)
    print(f"Indexed {len(docs)} chunks from {len(sys.argv)-1} files.")
    mock_llm = lambda p: "(plug in a real LLM here)\n--- prompt was ---\n" + p[:600]
    while True:
        q = input("\nquestion> ").strip()
        if not q: break
        text, hits = answer(q, index, mock_llm)
        print(text)
        print("\nSources:", ", ".join(f"[{i+1}] {c['source']} ({s:.2f})"
                                      for i, (s, c) in enumerate(hits)))
```

Run it on this repo's own phase READMEs and interrogate it. Then break it deliberately: ask a paraphrased question TF-IDF misses (embeddings fix that), ask a compound question (query decomposition fixes that), shrink `max_chars` until chunks fragment (chunking lesson, felt in the hands).

### Use It
| Component here | Production swap |
|---|---|
| Paragraph chunker | Recursive/structural splitter + overlap |
| TF-IDF `_vectorize` | Embedding model (same interface!) |
| Linear cosine scan | pgvector / HNSW when N demands it |
| Single retrieve | Hybrid (keep TF-IDF! it's your sparse leg) + rerank |
| `mock_llm` | Real API + faithfulness verification |
| Nothing | The lesson-11 golden set — build it first |

### War Story
The distance from Lewis et al.'s 2020 RAG paper to the code above is smaller than the framework ecosystem suggests: the paper's contribution was jointly *training* retriever and generator, but the deployed pattern that conquered industry — retrieve top-k, stuff the prompt, generate — is what you just wrote. When the 2023 RAG boom hit, teams that understood these ~90 lines debugged their systems; teams that only knew the framework wrapper filed issues.

### Checkpoint
1. Which single function would you replace to convert this to dense retrieval, and why does nothing else change?
2. Why are vectors normalized at build time instead of at query time?
3. This pipeline retrieves nothing for "how do I get reimbursed?" over a refunds doc — name the failure and two lessons from this phase that fix it.
