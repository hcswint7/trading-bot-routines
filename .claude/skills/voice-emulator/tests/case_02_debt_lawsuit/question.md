# Test case 2 (finance / law) — generalization check

> If a credit card company sues me for unpaid debt and I don't respond to the
> lawsuit, what happens?

Purpose: the first test (`tests/finance_law_question.md`, the inherited IRA
question) proved the loop works once. This case is a second, unrelated
finance/law question, run independently, to check the skill and auditor
generalize rather than being tuned to one prompt.

Target answer must:
- open by answering the question (what happens if you don't respond),
- be factually right (default judgment; wage garnishment / bank levy / liens
  where allowed; interest and costs accrue; a default judgment can sometimes be
  reopened for good cause),
- pass `audit.py` with zero HARD findings,
- read as a direct answer, not a story.
