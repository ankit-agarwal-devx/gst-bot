# Notes

Fill this in as you go and commit it with your code: it travels with every submission, and we read
it alongside your git history. Short and specific beats long. An example of the level of detail we
like is at the bottom.

## Task 1

- **Plan (sub-tasks, in order):**
- **Root cause(s):**
- **What broke when you fixed something, and why:**
- **Time spent:**

## Task 2

- **Plan (sub-tasks, in order):**
- **Root cause(s):**
- **What broke when you fixed something, and why:**
- **Time spent:**

## Task 3

- **Plan (sub-tasks, in order):**
- **Root cause(s):**
- **What broke when you fixed something, and why:**
- **Time spent:**

## Task 4

- **Plan (sub-tasks, in order), written before you start:**
- **Design decisions and trade-offs:**
- **What broke, and why:**
- **Time spent:**

## If I had more time

-

---

<details><summary>Example (a different, made-up bug)</summary>

- **Plan:** 1. Reproduce with a test at 18:45 IST. 2. Find where the report date is computed.
  3. Fix, plus a regression test.
- **Root cause:** `report.py` used `datetime.utcnow().date()`. IST is UTC+5:30, so after 18:30 IST
  the UTC date is already tomorrow.
- **What broke:** switching to `timezone.localdate()` broke the CSV export test, which had the UTC
  date hard-coded. I fixed the test fixture, not the export, because the export was right.
- **Time spent:** 1.5 h

</details>
