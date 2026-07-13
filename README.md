# trading-bot-routines

## Voice emulator

A voice emulator that answers finance and law questions in a plain, direct
expert voice — no story, no flourish. It follows six writing rules from George
Orwell and bans story-like framing. It ships with an auditor that grades a draft
and a Ralph loop that drives generate → audit → revise until the draft reads
clean.

The skill lives at `.claude/skills/voice-emulator/`:

```
.claude/skills/voice-emulator/
  SKILL.md                 the voice spec (the six rules + anti-story directive)
  reference/
    orwell-rules.md        each rule, worked into concrete do/don't
    style-guide.md         banned phrases, word swaps, a direct-answer template
  audit.py                 grades text vs. the rules; exit 0 = PASS, 1 = FAIL
  ralph_loop.sh            generate -> audit -> revise loop
  tests/
    finance_law_question.md  the test prompt
    iteration_01..03.md      drafts from the loop run
    audit_log.md             what each round caught and how it was fixed
    final_answer.md          the passing answer
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
python3 .claude/skills/voice-emulator/audit.py <file>
python3 .claude/skills/voice-emulator/audit.py <file> --json
```

Run the loop over the recorded run (shows FAIL → FAIL → PASS):

```
bash .claude/skills/voice-emulator/ralph_loop.sh --replay .claude/skills/voice-emulator/tests
```

Live loop with your own generator command (it must rewrite the candidate file
each round; it gets the question file as `$1` and the last report as `$2`):

```
bash .claude/skills/voice-emulator/ralph_loop.sh --gen "<your-generator-cmd>" <candidate_file>
```

### The test run

Question: *"If I inherit my dad's traditional IRA, do I have to take the money
out right away, and will I owe taxes on it?"* The loop went from a story-like
first draft (8 hard findings) to a clean, direct, five-plus-sentence answer in
three rounds. See `tests/audit_log.md`.

> Note: this skill controls how an answer reads, not the facts in it. Check the
> facts before you ship. The sample answer reflects the SECURE Act ten-year rule
> as of 2026; tax rules change.
