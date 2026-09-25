# Tasks

Four user stories, done **in order**: each one unlocks when the previous one passes on the grader
(see the README for `/start` and submitting). Budget about 10 hours in total. Some fixes will
uncover further problems: that's expected, and it's what the "What broke" part of `NOTES.md` is for.

A task is done when every test in its file passes locally (`uv run python progress.py`) **and** its
hidden checks pass on the grader.

## Task 1: The bot doesn't recognise my question (≈ 1 h)

> As a business owner, when I type a common question a little differently (capital letters, extra
> spaces, a curly apostrophe, two question marks) the bot doesn't recognise it. Sometimes it answers
> a different question: I asked "What is GSTIN?" and got the answer about GST.

Done when: `tests/bot/test_task1_faq.py` passes, plus hidden checks.

## Task 2: The GST on my invoice is wrong (≈ 2.5 h)

> As an accountant, the breakdown from `/api/gst/calculate` doesn't match what I file. Valid GSTINs
> are rejected, SEZ invoices come out as intra-state, Delhi invoices show UTGST, and totals are
> sometimes off by a paisa, including on our Rs 45 crore invoice.

Done when: `tests/bot/test_task2_gst.py` passes, plus hidden checks.

## Task 3: The bot sometimes spins forever, then errors (≈ 4 h)

> As a user, when I ask something the FAQ doesn't cover, the bot sometimes spins forever and then
> errors. Ops say we hammer tax-model when it's struggling, get throttled harder, and sometimes pay
> for the same answer twice. Double-clicking Send sometimes posts my message twice.

Done when: `tests/bot/test_task3_upstream.py` passes, plus hidden checks.
tax-model's behaviour is documented in [docs/TAXMODEL_API.md](docs/TAXMODEL_API.md).

## Task 4: Keep helping users when tax-model is struggling (new feature, ≈ 2.5 h)

> As a user, when tax-model is struggling I'd rather get a quick "busy right now" reply listing
> related questions the bot can answer than wait. As ops, we want the bot to stop calling tax-model
> for a while after repeated failures, then carefully try again.

**Plan before you build:** write your sub-tasks in `NOTES.md` first.

Done when: `tests/bot/test_task4_resilience.py` passes, plus hidden checks.
