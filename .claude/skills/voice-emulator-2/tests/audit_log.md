# Ralph-loop audit log

Question: see `finance_law_question.md` (inherited traditional IRA — withdrawal
timing and taxes). Generator: agent-driven (Claude drafts, `audit.py` grades,
Claude revises). Bar: zero HARD findings plus a clean human read.

Replay the whole run:

```
bash ralph_loop.sh --replay tests
# ROUND 1 iteration_01.md  FAIL
# ROUND 2 iteration_02.md  FAIL
# ROUND 3 iteration_03.md  PASS  -> converged
```

## Round 1 — `iteration_01.md` — FAIL (8 HARD, 3 SOFT)

A typical first draft that slid into a story. What the auditor caught:

- **story-like:** opened with "Imagine you've just found out..." (scene-setting)
  and a mid-answer rhetorical question ("So what does that mean for your wallet?").
- **rule-i:** "ticking clock," "at the end of the day," and the simile "like a
  windfall."
- **rule-iv:** "is taxed," "be emptied" (passive).
- **rule-v:** "utilize" (jargon).
- **soft:** "in order to," "really," "utilize."

Fix plan: delete the opener and answer the question in sentence one; drop the
figures of speech; make the tax sentence active; swap "utilize" for "use"; cut
the rhetorical aside and the filler.

## Round 2 — `iteration_02.md` — FAIL (1 HARD, 1 SOFT)

The rewrite answered first, dropped every cliché and the story frame, and got
the facts in. Two things remained:

- **rule-iv:** "it is taxed at your normal rate" (still passive).
- **soft:** "required" (a longer word than needed).

Fix plan: name the actor — "the IRS taxes it at your normal rate" — and rephrase
"his required withdrawals" as "yearly minimum withdrawals."

## Round 3 — `iteration_03.md` — PASS (0 HARD, 0 SOFT)

Clean. Six sentences, answers both parts of the question in sentence one, active
voice throughout, no story framing, plain words. Saved as `final_answer.md`.

### Why the final passes
- Opens with the answer ("No, you do not have to take the money out right
  away..."), not a scene or a question.
- No metaphor, simile, or worn idiom (rule i).
- Short, everyday words; no jargon or foreign phrases (rules ii, v).
- Active voice — the IRS taxes, you pull, you take, spreading keeps (rule iv).
- Five or more sentences, each carrying a fact the reader needs (structure).
