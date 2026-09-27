# Notes

Fill this in as you go and commit it with your code: it travels with every submission, and we read
it alongside your git history. Short and specific beats long. An example of the level of detail we
like is at the bottom.

## Task 1

- **Plan (sub-tasks, in order):** 1. Reproduce Task 1's first failure. 2. Normalize Unicode, case, whitespace and punctuation; load the FAQ's plural `aliases` key. 3. Require exact normalized matches and run the Task 1 test file.
- **Root cause(s):** FAQ matching only lowercased and trimmed text, accepted prefixes, and loaded `alias` even though `faq.json` uses `aliases`.
- **What broke when you fixed something, and why:** Nothing observed; all 25 Task 1 tests pass.
- **Time spent:** 40 mins.
- **Test Command:**  `uv run pytest tests/bot/test_task1_faq.py -q`

## Task 2

- **Plan (sub-tasks, in order):** 1. Reproduce the invalid GSTIN rejection. 2. Correct checksum weighting and calculator tax rules. 3. Use exact decimal arithmetic and run the Task 2 tests.
- **Root cause(s):** The GSTIN checksum weights started in the wrong position; currency calculations used binary floats; place-of-supply and SEZ inputs were handled incorrectly; Delhi was classified for UTGST; the new rate date was exclusive.
- **What broke when you fixed something, and why:** The first Decimal helper change exposed float totals in the calculator; totals were converted to Decimal as well. The final Task 2 suite passes.
- **Time spent:**  2 hrs.
- **Test Command:** `uv run pytest tests/bot/test_task2_gst.py -q`

## Task 3

- **Plan (sub-tasks, in order):** 1. Reproduce the missing-timeout failure. 2. Add bounded retries, backoff, and idempotency for upstream calls. 3. Make duplicate-message handling and daily usage concurrency-safe. 4. Run Tasks 1-3 together.
- **Root cause(s):** Upstream calls had no timeout or deadline, retried every status without honoring `Retry-After`, and lacked an idempotency key. Message IDs were not unique per conversation, and daily usage used a racy read-modify-write.
- **What broke when you fixed something, and why:** The race test continued to create eight messages until a database uniqueness constraint was added; an in-progress duplicate now receives 409. All 17 Task 3 tests pass.
- **Time spent:** 2 hrs.
- **Test Command:** `uv run pytest tests/bot/test_task3_upstream.py -q`

## Task 4

- **Plan (sub-tasks, in order), written before you start:** 1. Add a thread-safe closed/open/half-open breaker using configured threshold and open duration. 2. Integrate it with upstream calls, leaving budget exhaustion out of breaker failures. 3. Return an immediate busy reply with relevant FAQ questions and omit degraded replies from model history. 4. Run Task 4 and regression tests.
- **Design decisions and trade-offs:** A lock protects breaker transitions so only one caller gets the half-open trial. The breaker is process-local; FAQ suggestions use weighted word overlap so unrelated questions are not suggested. Budget exhaustion does not count as an upstream failure.
- **What broke, and why:** The initial focused test confirmed the missing breaker module; after adding it, integration covered the module-level chat breaker. All visible tests now pass.
- **Time spent:**  3.5 hrs.
- **Test Command:** `uv run pytest tests/bot/test_task4_resilience.py -q`

## If I had more time

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
