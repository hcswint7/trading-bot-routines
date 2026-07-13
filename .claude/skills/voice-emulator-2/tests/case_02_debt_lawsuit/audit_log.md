# Ralph-loop audit log — case 2 (debt lawsuit / default judgment)

Question: see `question.md`. This run tests generalization: a second,
unrelated finance/law question, invoked live through the `voice-emulator-2`
skill (via Claude Code's `Skill` tool) rather than pre-written by hand.

Replay this case:

```
bash ../../ralph_loop.sh --replay .
```

## Round 1 — `iteration_01.md` — FAIL (11 HARD, 2 SOFT)

A naive first draft, the kind a model writes without the skill applied:

- **story-like:** opened with "Imagine you get a letter..." (scene-setting);
  contained the narrative filler "here's the thing"; a mid-answer rhetorical
  question ("What happens if you miss it?"); a "not just X, but Y" flourish.
- **rule-i:** the simile "like a nightmare" and the cliché "at the end of the
  day."
- **rule-iv:** four separate passive constructions — "[a response] must be
  filed," "which is set by the court," "a default judgment is entered," "wages
  can be garnished."
- **soft:** "in order to" (filler), "really" (intensifier).

Fix plan: cut the story frame and the rhetorical question, drop the cliché and
simile, rewrite every passive with a named actor (the court enters, the court
sets, the creditor garnishes), and drop the flourish.

## Round 2 — `iteration_02.md` — FAIL (1 HARD, 1 SOFT)

The rewrite fixed all story-like and rule-i findings and three of the four
passives. Two things remained:

- **rule-iv:** "after you are served" — still passive.
- **soft:** "in order to" — filler, not yet cut.

Fix plan: name the actor — "once the company serves you with the lawsuit" —
and drop "in order to" in favor of a direct clause.

## Round 3 — `iteration_03.md` / `final_answer.md` — PASS (0 HARD, 0 SOFT)

Clean. Six sentences, answers the question in sentence one, active voice
throughout ("the court will enter," "the company serves you," "the creditor can
garnish"), no story framing, plain words, the one real caveat (courts do not
always reopen a default judgment) placed last.

### Why this matters
The same auditor, unmodified, caught 11 real problems across every hard
category on a brand-new question, then correctly passed a genuinely clean
answer — 0/0 both times it should. That is the generalization check this case
was for.
