# trading-bot-routines

## Voice emulator 2

A voice emulator that answers finance and law questions in a plain, direct
expert voice — no story, no flourish. It follows six writing rules from George
Orwell and bans story-like framing. It ships with an auditor that grades a draft
and a Ralph loop that drives generate → audit → revise until the draft reads
clean.

This is a net-new skill built in this repo, named `voice-emulator-2` because it
is not an edit of any prior voice-emulator skill — no such skill existed in
this environment or repo to modify.

The skill lives at `.claude/skills/voice-emulator-2/`:

```
.claude/skills/voice-emulator-2/
  SKILL.md                 the voice spec (the six rules + anti-story directive)
  reference/
    orwell-rules.md        each rule, worked into concrete do/don't
    style-guide.md         banned phrases, word swaps, a direct-answer template
  audit.py                 grades text vs. the rules; exit 0 = PASS, 1 = FAIL
  ralph_loop.sh            generate -> audit -> revise loop
  tests/
    finance_law_question.md  test case 1: the test prompt
    iteration_01..03.md      test case 1: drafts from the loop run
    audit_log.md             test case 1: what each round caught and the fix
    final_answer.md          test case 1: the passing answer
    case_02_debt_lawsuit/    test case 2: a second, unrelated question, same
                             structure (question/iterations/audit_log/final)
```

### The six rules

1. Never use a metaphor, simile or figure of speech you're used to seeing in print.
2. Never use a long word where a short one will do.
3. If it is possible to cut a word out, always cut it out.
4. Never use the passive where you can use the active.
5. Never use a foreign phrase, a scientific or jargon word if an everyday word exists.
6. Break any of these rules sooner than say anything outright barbarous.

The user's main ask sits on top of these: **limit weird or story-like writing.**
The auditor treats story-like framing (scene-setting openers, rhetorical
questions, dramatic fragments, hype) as the top hard-fail category.

### Use it

Grade a draft:

```
python3 .claude/skills/voice-emulator-2/audit.py <file>
python3 .claude/skills/voice-emulator-2/audit.py <file> --json
```

Run the loop over the recorded run (shows FAIL → FAIL → PASS):

```
bash .claude/skills/voice-emulator-2/ralph_loop.sh --replay .claude/skills/voice-emulator-2/tests
```

Live loop with your own generator command (it must rewrite the candidate file
each round; it gets the question file as `$1` and the last report as `$2`):

```
bash .claude/skills/voice-emulator-2/ralph_loop.sh --gen "<your-generator-cmd>" <candidate_file>
```

The skill is registered as a project skill and loads through Claude Code's
`Skill` tool (`voice-emulator-2`) — it is not just files on disk; Claude can
invoke it directly to draft an answer in this voice before auditing it.

### Test runs

**Case 1 — inherited IRA.** *"If I inherit my dad's traditional IRA, do I have
to take the money out right away, and will I owe taxes on it?"* The loop went
from a story-like first draft (8 hard findings) to a clean, direct,
five-plus-sentence answer in three rounds. See `tests/audit_log.md`.

**Case 2 — debt lawsuit (generalization check).** *"If a credit card company
sues me for unpaid debt and I don't respond to the lawsuit, what happens?"* A
second, unrelated question, drafted through a live `Skill` invocation rather
than hand-written. Same shape: a naive first draft tripped 11 hard findings
(story opener, a simile, a cliché, four passive constructions, a rhetorical
aside, a "not just X but Y" flourish); round 2 fixed all but one leftover
passive; round 3 passed clean. See `tests/case_02_debt_lawsuit/audit_log.md`.
Replay it: `bash .claude/skills/voice-emulator-2/ralph_loop.sh --replay
.claude/skills/voice-emulator-2/tests/case_02_debt_lawsuit`.

Both cases converge the same way — many real findings on a naive draft, one or
two left after a revision pass, zero on the final — which is the evidence that
the auditor is catching genuine problems and not rubber-stamping everything.

> Note: this skill controls how an answer reads, not the facts in it. Check the
> facts before you ship. The sample answers reflect US federal rules as of
> 2026 (SECURE Act ten-year rule; default-judgment procedure varies by state);
> rules change and state law differs.
