#!/usr/bin/env python3
"""Voice-emulator auditor.

Grades a piece of writing against the voice rules and prints findings. It exists
to make each pass of the Ralph loop objective: a draft that trips a HARD rule
gets exit code 1, a clean draft gets exit code 0.

The rules come from the voice-emulator skill:
  - story-like / weird writing  (the top thing to catch)
  - Orwell rule i   no stale figures of speech / similes   (HARD)
  - Orwell rule iv  no passive voice                        (HARD)
  - Orwell rule v   no jargon / foreign phrases             (HARD)
  - structure       answer first, five sentences or more    (HARD)
  - Orwell rule ii  short words over long ones               (SOFT)
  - Orwell rule iii cut filler                               (SOFT)

The auditor is a helper, not the judge (Orwell rule vi). A clean exit plus a
human read is the real bar.

Usage:
    python3 audit.py <file>          # human-readable report, exit 0/1
    python3 audit.py <file> --json   # machine-readable report
    python3 audit.py --text "..."    # audit a string instead of a file
"""

import json
import re
import sys
from collections import namedtuple

Finding = namedtuple("Finding", "category severity rule snippet message")

# --------------------------------------------------------------------------- #
# Phrase lists
# --------------------------------------------------------------------------- #

# Story-like openers: only a problem when they START the answer.
OPENER_PATTERNS = [
    r"imagine\b",
    r"picture (this|yourself|a)\b",
    r"(let'?s|lets) say\b",
    r"say you(?:'re| are)\b",
    r"suppose\b",
    r"you (just )?(wake up|woke up|found out|just found out)\b",
    r"meet [A-Z]",
    r"ever wonder(ed)?\b",
    r"have you ever\b",
    r"so,? what happens\b",
    r"what if\b",
    r"once upon\b",
    r"here'?s the thing\b",
    r"the truth is\b",
    r"(let'?s|lets) be honest\b",
    r"now,\s",
    r"think of it as\b",
]

# Narrative markers: a problem anywhere, not just the opener.
NARRATIVE_MARKERS = [
    r"\bimagine\b",
    r"\bpicture this\b",
    r"\byou wake up\b",
    r"\bonce upon a time\b",
    r"\blet'?s say\b",
    r"\bsay you'?re\b",
    r"\bhere'?s the thing\b",
    r"\bthink of it as\b",
    r"\bthe truth is\b",
]

# Orwell i: worn figures of speech and idioms.
CLICHES = [
    "double-edged sword", "perfect storm", "tip of the iceberg",
    "navigate the waters", "navigate these waters", "ticking clock",
    "safety net", "kick the can down the road", "moving the goalposts",
    "at the end of the day", "the bottom line", "level playing field",
    "low-hanging fruit", "low hanging fruit", "think outside the box",
    "when it comes to", "needless to say", "in a nutshell",
    "the name of the game", "a slippery slope", "the elephant in the room",
    "par for the course", "the lay of the land", "a double edged sword",
    "rule of thumb", "light at the end of the tunnel", "cut to the chase",
]

# Orwell v: foreign phrases and jargon that have plain swaps.
FOREIGN = [
    "per se", "vis-à-vis", "vis-a-vis", "de facto", "de jure",
    "prima facie", "inter alia", "ceteris paribus", "bona fide",
    "ipso facto", "ergo,",
]
JARGON = {
    "utilize": "use", "utilise": "use", "leverage": "use", "synergy": "teamwork",
    "incentivize": "encourage", "incentivise": "encourage",
    "operationalize": "put to work", "paradigm": "model",
    "circle back": "follow up", "touch base": "check in",
    "deep dive": "close look", "bandwidth": "time",
}

# Orwell ii: long word -> short word.
LONG_WORDS = {
    "utilize": "use", "purchase": "buy", "approximately": "about",
    "prior to": "before", "subsequent to": "after", "commence": "start",
    "terminate": "end", "sufficient": "enough", "additional": "more",
    "facilitate": "help", "demonstrate": "show", "numerous": "many",
    "require": "need", "obtain": "get", "assist": "help", "indicate": "show",
    "utilise": "use", "endeavor": "try", "ascertain": "find out",
    "commence": "start", "remuneration": "pay",
}

# Orwell iii: filler and dead intensifiers.
FILLER = [
    "in order to", "due to the fact that", "owing to the fact that",
    "the fact that", "it is important to note that",
    "it should be noted that", "for the purpose of", "in the event that",
    "at this point in time", "a number of", "in terms of",
    "needless to say", "as a matter of fact",
]
INTENSIFIERS = ["very", "really", "quite", "basically", "actually",
                "essentially", "literally", "simply just"]

# Hype adjectives — soft story-like signal.
HYPE = ["crucial", "vital", "powerful", "game-changing", "game changer",
        "seamless", "robust", "supercharge", "unlock", "revolutionary",
        "cutting-edge", "world-class"]

# Passive voice: be-verb + past participle. Allow common predicate adjectives.
BE_VERBS = r"(?:is|are|was|were|be|been|being|am|get|gets|got)"
IRREGULAR_PARTICIPLES = (
    "taken given made held paid sold bought sent kept left drawn shown known "
    "done seen written born built found told met set put cut lost won paid "
    "withheld withdrawn owed"
).split()
PASSIVE_ALLOW = {
    "retired", "married", "interested", "located", "related", "involved",
    "complicated", "dedicated", "limited", "detailed", "qualified", "based",
    "concerned", "supposed", "used", "tired", "pleased", "prepared",
}

# --------------------------------------------------------------------------- #
# Text helpers
# --------------------------------------------------------------------------- #

ABBREVS = ["e.g.", "i.e.", "U.S.", "U.S.C.", "U.K.", "Mr.", "Mrs.", "Ms.",
           "Dr.", "vs.", "etc.", "Inc.", "a.m.", "p.m.", "No.", "St."]


def split_sentences(text):
    protected = text
    for a in ABBREVS:
        protected = protected.replace(a, a.replace(".", "\x00"))
    parts = re.split(r"(?<=[.!?])\s+", protected)
    out = []
    for p in parts:
        p = p.replace("\x00", ".").strip()
        if p:
            out.append(p)
    return out


def word_count(s):
    return len(re.findall(r"[A-Za-z0-9']+", s))


def find_all(text, phrase):
    return [m.start() for m in re.finditer(re.escape(phrase), text, re.IGNORECASE)]


# --------------------------------------------------------------------------- #
# Checks
# --------------------------------------------------------------------------- #

def check_story_like(text, sentences):
    findings = []
    first = sentences[0] if sentences else ""

    for pat in OPENER_PATTERNS:
        if re.match(r"^\W*" + pat, first, re.IGNORECASE):
            findings.append(Finding(
                "story-like", "HARD", "anti-story:opener",
                first[:60], "Answer opens with a story/scene, not the answer."))
            break

    if first.rstrip().endswith("?"):
        findings.append(Finding(
            "story-like", "HARD", "anti-story:rhetorical-opener",
            first[:60], "Answer opens with a question instead of answering."))

    for pat in NARRATIVE_MARKERS:
        for m in re.finditer(pat, text, re.IGNORECASE):
            findings.append(Finding(
                "story-like", "HARD", "anti-story:narrative",
                m.group(0), "Narrative/scene-setting phrase; say the fact plainly."))

    # Dramatic fragments: very short sentences after the first, or short
    # rhetorical questions mid-text.
    for s in sentences[1:]:
        wc = word_count(s)
        if s.rstrip().endswith("?") and wc <= 6:
            findings.append(Finding(
                "story-like", "HARD", "anti-story:rhetorical-aside",
                s[:60], "Mid-answer rhetorical question; drop it, state the point."))
        elif wc <= 2 and not s.endswith(":"):
            findings.append(Finding(
                "story-like", "HARD", "anti-story:fragment",
                s[:60], "Dramatic fragment; write a full sentence."))

    for pat in [r"\bnot just\b.{0,60}?\bbut\b",
                r"\bnot only\b.{0,60}?\bbut also\b",
                r"\bit'?s not about\b.{0,60}?\bit'?s about\b"]:
        for m in re.finditer(pat, text, re.IGNORECASE | re.DOTALL):
            findings.append(Finding(
                "story-like", "HARD", "anti-story:flourish",
                m.group(0)[:60], '"not just X but Y" flourish; state it flat.'))

    if "!" in text:
        findings.append(Finding(
            "story-like", "HARD", "anti-story:exclamation",
            "!", "Exclamation mark; drop it."))
    if "..." in text or "…" in text:
        findings.append(Finding(
            "story-like", "HARD", "anti-story:ellipsis",
            "...", "Ellipsis for suspense; drop it."))

    dash_count = text.count("—") + len(re.findall(r"\s-\s", text))
    if dash_count > 3:
        findings.append(Finding(
            "story-like", "SOFT", "anti-story:em-dash",
            "%d dashes" % dash_count, "Many dashes; a comma or full stop is plainer."))

    for w in HYPE:
        for _ in find_all(text, w):
            findings.append(Finding(
                "story-like", "SOFT", "anti-story:hype",
                w, "Hype word; cut it or say the plain thing."))

    return findings


def check_cliches(text):
    findings = []
    for c in CLICHES:
        for _ in find_all(text, c):
            findings.append(Finding(
                "rule-i", "HARD", "orwell-i:cliche", c,
                "Worn figure of speech; say the literal thing."))
    for m in re.finditer(r"\blike an?\b|\bas \w+ as\b", text, re.IGNORECASE):
        # "would like a" is not a simile; skip that case.
        start = max(0, m.start() - 6)
        if re.search(r"\bwould\s*$", text[start:m.start()], re.IGNORECASE):
            continue
        findings.append(Finding(
            "rule-i", "HARD", "orwell-i:simile", m.group(0),
            "Simile; describe it plainly instead."))
    return findings


def check_passive(text):
    findings = []
    pat = re.compile(
        r"\b" + BE_VERBS + r"\b\s+(\w+ed|" + "|".join(IRREGULAR_PARTICIPLES) + r")\b",
        re.IGNORECASE)
    for m in pat.finditer(text):
        participle = m.group(1).lower()
        if participle in PASSIVE_ALLOW:
            continue
        findings.append(Finding(
            "rule-iv", "HARD", "orwell-iv:passive", m.group(0),
            "Passive voice; name who does the thing and use the active."))
    return findings


def check_jargon(text):
    findings = []
    for f in FOREIGN:
        for _ in find_all(text, f):
            findings.append(Finding(
                "rule-v", "HARD", "orwell-v:foreign", f,
                "Foreign phrase; use the plain English word."))
    for j, swap in JARGON.items():
        for _ in find_all(text, j):
            findings.append(Finding(
                "rule-v", "HARD", "orwell-v:jargon", j,
                'Jargon; use "%s".' % swap))
    return findings


def check_structure(text, sentences):
    findings = []
    n = len(sentences)
    if n < 5:
        findings.append(Finding(
            "structure", "HARD", "structure:length",
            "%d sentences" % n, "Fewer than five sentences; expand the answer."))
    first = sentences[0] if sentences else ""
    # A direct opener is a declarative sentence. Question openers and scene
    # openers are caught in check_story_like; here we catch background/hedge
    # openers that bury the answer.
    hedges = [r"^(well|so|now|honestly|look|okay|right),",
              r"^there (is|are) (a|an|several|many|some|two|three)",
              r"^one (thing|question|of)"]
    for h in hedges:
        if re.match(h, first, re.IGNORECASE):
            findings.append(Finding(
                "structure", "HARD", "structure:buried-answer",
                first[:60], "Opener hedges or sets up; put the answer first."))
            break
    return findings


def check_long_words(text):
    findings = []
    for long, short in LONG_WORDS.items():
        for _ in find_all(text, long):
            findings.append(Finding(
                "rule-ii", "SOFT", "orwell-ii:long-word", long,
                'Long word; try "%s".' % short))
    return findings


def check_filler(text):
    findings = []
    for f in FILLER:
        for _ in find_all(text, f):
            findings.append(Finding(
                "rule-iii", "SOFT", "orwell-iii:filler", f,
                "Filler; cut it or rewrite."))
    for w in INTENSIFIERS:
        for _ in re.finditer(r"\b" + re.escape(w) + r"\b", text, re.IGNORECASE):
            findings.append(Finding(
                "rule-iii", "SOFT", "orwell-iii:intensifier", w,
                "Dead intensifier; cut it."))
    return findings


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #

def audit(text):
    sentences = split_sentences(text)
    findings = []
    findings += check_story_like(text, sentences)
    findings += check_cliches(text)
    findings += check_passive(text)
    findings += check_jargon(text)
    findings += check_structure(text, sentences)
    findings += check_long_words(text)
    findings += check_filler(text)

    hard = [f for f in findings if f.severity == "HARD"]
    soft = [f for f in findings if f.severity == "SOFT"]
    words = word_count(text)
    avg_len = round(words / len(sentences), 1) if sentences else 0
    summary = {
        "sentences": len(sentences),
        "words": words,
        "avg_sentence_words": avg_len,
        "hard": len(hard),
        "soft": len(soft),
        "verdict": "PASS" if not hard else "FAIL",
    }
    return findings, summary


CATEGORY_ORDER = ["story-like", "rule-i", "rule-iv", "rule-v", "structure",
                  "rule-ii", "rule-iii"]


def print_report(findings, summary):
    print("=" * 66)
    print("VOICE AUDIT")
    print("=" * 66)
    print("sentences: %(sentences)d   words: %(words)d   "
          "avg sentence: %(avg_sentence_words)s words" % summary)
    print("HARD findings: %(hard)d   SOFT findings: %(soft)d" % summary)
    print("-" * 66)
    if not findings:
        print("No findings. Clean.")
    else:
        by_cat = {}
        for f in findings:
            by_cat.setdefault(f.category, []).append(f)
        for cat in CATEGORY_ORDER:
            if cat not in by_cat:
                continue
            print("\n[%s]" % cat)
            for f in by_cat[cat]:
                print("  %-4s %-26s %-22s %s" % (
                    f.severity, f.rule, repr(f.snippet)[:22], f.message))
    print("-" * 66)
    print("VERDICT: %s" % summary["verdict"])
    print("=" * 66)


def main(argv):
    text = None
    as_json = "--json" in argv
    args = [a for a in argv if not a.startswith("--")]
    if "--text" in argv:
        idx = argv.index("--text")
        text = argv[idx + 1]
    elif args:
        with open(args[0], encoding="utf-8") as fh:
            text = fh.read()
    else:
        print("usage: audit.py <file> [--json] | --text \"...\"", file=sys.stderr)
        return 2

    findings, summary = audit(text)
    if as_json:
        print(json.dumps({
            "summary": summary,
            "findings": [f._asdict() for f in findings],
        }, indent=2))
    else:
        print_report(findings, summary)
    return 0 if summary["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
