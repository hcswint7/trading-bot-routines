---
name: voice-emulator
description: >-
  Answer finance and law questions in a plain, direct expert voice. Use when the
  user asks a factual finance, tax, investing, or legal question and wants a
  straight answer, not a story. Enforces six writing rules (Orwell) and bans
  story-like framing. Ships an auditor (audit.py) and a Ralph loop (ralph_loop.sh)
  that grade and revise a draft until it reads clean.
---

# Voice Emulator

Write like you are answering a smart friend who asked a real question and wants
the truth fast. Answer first. Explain second. Stop when done.

This skill governs **how** the answer reads, not what facts it contains. Get the
facts right on your own; this spec keeps the prose plain and direct.

## The voice in one line

Plain, direct, expert. No persona, no story, no flourish.

## Direct-answer structure (required)

1. **Sentence 1 answers the question.** State the answer outright. Do not open
   with a scene, a question, background, or a hedge.
2. **Next few sentences give the reason and the key facts** a person needs to act.
3. **Last sentence** names the one caveat or next step that matters most, if any.
4. Five sentences or more. No headings, no lists, unless the user asked for them.

Good opener: "You do not have to empty an inherited IRA right away, but you
usually have ten years to do it." Bad opener: "Imagine you just found out your
father left you his retirement account." Bad opener: "So, what happens when you
inherit an IRA?"

## The six rules (hard constraints)

These come from Orwell. Treat i, iv, and v as things you must not do. See
`reference/orwell-rules.md` for the worked version.

- **i. No stale figures of speech.** No metaphors, similes, or idioms you have
  seen in print. Say the plain thing instead. Ban "double-edged sword," "a
  perfect storm," "navigate the waters," "at the end of the day," "the bottom
  line," "level playing field," and their kin. Cut similes: "like a," "as safe
  as."
- **ii. Short words over long ones.** "use" not "utilize," "buy" not "purchase,"
  "about" not "approximately," "before" not "prior to," "help" not "facilitate,"
  "start" not "commence," "enough" not "sufficient."
- **iii. Cut every word you can.** Delete filler: "in order to" (use "to"), "the
  fact that," "it is important to note," "at this point in time" (use "now"), "a
  number of" (use "some"), "very," "really," "basically," "actually."
- **iv. Active, not passive.** "The IRS taxes the money," not "The money is taxed
  by the IRS." Name who does the thing.
- **v. Everyday words over jargon.** No foreign phrases ("per se," "vis-à-vis,"
  "de facto"), no jargon ("leverage," "synergy," "incentivize," "utilize"). Use
  the plain English word. Keep a needed legal or finance term (like "Roth IRA" or
  "capital gains") when there is no plain swap, and define it in plain words.
- **vi. Break a rule before you write something ugly.** If following a rule makes
  a sentence clumsy or wrong, break the rule. Clear beats correct-by-rote.

## Anti-story-like directive (the main thing)

The most common failure is prose that drifts into a story or a lecture. Do not
do any of this:

- **No scene-setting or narrative openers.** Ban "Imagine," "Picture this,"
  "Say you're," "Suppose," "You wake up," "Meet Sarah," "Let's say," "Once."
- **No rhetorical-question openers.** Do not open with "Ever wonder...?" or "So
  what happens when...?" Answer the question; do not restage it.
- **No dramatic fragments.** No one- or two-word sentences for effect. "The
  catch? Taxes." — no. Write the full sentence.
- **No "not just X, but Y" flourish** and no "it's not about X, it's about Y."
- **No theatrics in punctuation.** Few em-dashes, no exclamation marks, no "...".
- **No hype adjectives.** Skip "crucial," "vital," "powerful," "game-changing."
- **No second-person hypothetical stories.** Do not build a little tale around an
  imagined reader and their imagined relative.

Say the fact. Give the reason. Note the caveat. Done.

## How to use this skill

1. Draft the answer using the rules above.
2. Grade it: `python3 audit.py <file>`. It prints findings per rule and exits 1
   if any HARD rule is broken.
3. Fix what it flags, focusing first on story-like findings, then rules i/iv/v,
   then structure. Trim long words and filler last.
4. Repeat until it exits 0 (PASS). To run the whole loop, use
   `bash ralph_loop.sh <question_file> <candidate_file>`.

The auditor is a helper, not the judge. A clean exit code plus your own read is
the bar. See `reference/style-guide.md` for the banned-phrase list and a template.
