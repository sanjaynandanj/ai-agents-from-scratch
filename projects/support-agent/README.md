# Project: Support Agent

> **MOTTO:** A support agent's job is knowing which tickets it must NOT
> handle -- the replies are the easy part.

Every "AI customer support" product is a router bolted to a toolbox
bolted to a set of tripwires. This project builds all three in one
stdlib-only file: five simulated tickets flow through an injection
guardrail, a classifier, and specialist handlers armed with real tools --
including a refund tool that refuses to trust anyone, especially the
agent calling it.

## What you're building

A pipeline that processes a stream of five tickets -- a refund request, a
bug report, a how-to, an angry escalation, and a prompt-injection attempt
-- and ends the run with exactly the right split: three handled by the
bot, one queued for a human, one quarantined for security review.

```
  TICKET STREAM (5)
       |
       v
  +---------------------+   patterns hit    +--------------------+
  | INJECTION GUARDRAIL |------------------>| QUARANTINE         |
  | scans RAW text      |                   | security review    |
  +----------+----------+                   +--------------------+
             | clean
             v
  +---------------------+   "furious/manager"   +----------------+
  | CLASSIFIER (mockLLM)|---------------------->| HUMAN QUEUE    |
  | escalate/howto/     |                       +----------------+
  | billing/tech        |
  +----+------+----+----+
       |      |    |
   billing  tech howto
       |      |    |
       v      v    v
  +---------------------------------------------------+
  | SPECIALIST HANDLERS + TOOLS                        |
  |  order_lookup(id)      -> fake orders DB           |
  |  kb_search(query)      -> keyword-scored articles  |
  |  refund(id, requester) -> GATED:                   |
  |     order exists? owner matches? amount <= $50?    |
  +------------------------+--------------------------+
                           v
              reply  /  refund  /  punt to human
```

## The security story (the actual point)

Three separate mechanisms, three separate failure modes:

1. **Input guardrail.** Ticket text is scanned for injection patterns
   *before* any model or tool touches it. Ticket text is data from a
   stranger; treating it as instructions is the original sin of agent
   security.
2. **Routing tripwire.** The classifier's first rule is "is this beyond
   my pay grade?" -- rage goes to humans, not to a bot that will make it
   worse with a chirpy apology.
3. **Tool-level permission gate.** `refund()` re-checks everything
   itself: order exists, requester owns it, amount under the auto-limit.
   Even if the injection ticket (T-05, demanding $10,000 on someone
   else's order) slipped past the guardrail, the gate would deny it
   twice over. Defense in depth means the last line doesn't know there
   was a first line.

## Milestones

1. **Fake world.** Orders dict, three KB articles with keyword strings,
   five hardcoded tickets. Boring, and the foundation of everything.
2. **Tools.** `order_lookup` (dict get), `kb_search` (keyword-overlap
   scoring with a deterministic tie-break), and `refund` with its
   three-check gate returning `(ok, message)`.
3. **Guardrail.** A pattern list and a scan function. Run it FIRST in
   the pipeline; a blocked ticket produces no classification, no tool
   calls, and no reply -- silence is the safest output.
4. **Classifier.** Mock LLM with ordered trigger phrases; first match
   wins. Order matters: escalation outranks everything, and "how do I
   get a refund?" is a how-to, not a refund -- so howto outranks
   billing. (You will get this wrong once. That's the lesson.)
5. **Handlers.** billing (extract order id -> lookup -> policy check ->
   gated refund), tech (kb_search -> known-issue reply), howto
   (kb_search -> instructions). Each returns
   `(outcome, tools_used, reply)`.
6. **Pipeline + reporting.** Per-ticket transcript with indented tool
   logs, then a summary table and the human-escalation queue.

## How to run

```bash
python agent.py --demo
```

Offline, seeded, exits by itself. Expected end state:

| id | route | outcome |
|---|---|---|
| T-01 | billing | REFUNDED ($18.50, under the gate) |
| T-02 | tech | REPLIED (KB-11) |
| T-03 | howto | REPLIED (KB-12) |
| T-04 | escalate | ESCALATED (angry customer) |
| T-05 | - | BLOCKED (injection quarantine) |

## What to notice while it runs

- **T-05 never reaches the classifier.** No route is even assigned.
  The cheapest place to stop an attack is before anything smart runs.
- **The refund gate logs its reasoning.** Approvals should be as
  auditable as denials; "the AI refunded it" is not an audit trail.
- **The bot brags about NOT handling tickets.** The closing line counts
  escalations as successes. An agent that punts correctly is worth more
  than one that answers everything confidently.

## Extension ideas

1. **Plug in a real model.** Replace `MockLLM.classify` and
   `draft_reply` with API calls returning JSON
   (`{"route": ..., "confidence": ...}`). Keep the guardrail and the
   refund gate as plain code -- security logic in a prompt is a
   suggestion, not a control.
2. **Confidence thresholds.** Give the classifier a confidence score;
   below 0.7, route to a human instead of the best guess. Measure how
   the summary table shifts.
3. **Smarter injection defense.** Pattern lists are trivially evaded
   ("1gnore prev1ous..."). Add a second check: after drafting a reply,
   scan the *planned tool calls* for anomalies (a refund the customer
   never asked for) -- output-side guardrails catch what input-side
   ones miss.
4. **Conversation memory.** Let tickets be multi-turn: T-04's customer
   calms down after a human reply; does your classifier route their
   next message differently?
5. **A refund approval queue.** Add order ORD-1002's owner requesting
   their $74 refund. It exceeds the gate -- build the human-approval
   flow the DENIED message promises.
6. **Metrics.** Track deflection rate, escalation rate, and blocked
   attacks across a 50-ticket generated stream. Those three numbers are
   the entire business case for support agents.

## Checkpoint

- Why does the injection scan run before classification instead of
  after?
- The refund gate re-checks facts the billing handler already looked
  up. Why is that duplication a feature?
- Why should trigger order place "howto" above "billing" in the
  classifier?
