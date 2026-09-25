# GST Bot

A small Django service that helps Indian businesses with GST: it answers questions in a chat,
and it works out the GST on an invoice. It was started in a hurry by several people, and it
shows. Users have filed bug reports, and one feature is still missing.

[TASKS.md](TASKS.md) lists the work as four user stories. Record your plan and findings in
[NOTES.md](NOTES.md) as you go. This README covers setting up and the rules.

## Setup

You need Python 3.12, [uv](https://docs.astral.sh/uv/) and Postgres 16. Postgres is required:
some tests exercise concurrency and only behave correctly on a real database.

```bash
docker compose up -d db          # or use your own Postgres 16 (see gstbot/settings.py for the env vars)
uv sync
uv run python manage.py migrate
uv run pytest                    # most tests fail at the start; that's the job
```

## Running it by hand

The bot talks to **tax-model**, an upstream GST service described in
[docs/TAXMODEL_API.md](docs/TAXMODEL_API.md). Everything here uses the fake in `fake_taxmodel/`,
which throttles and fails exactly as that document says. The tests run it in-process; to try the
bot by hand, run it over HTTP:

```bash
uv run python -m fake_taxmodel.server --port 8081 &
TAXMODEL_BASE_URL=http://127.0.0.1:8081 uv run python manage.py runserver
```

```bash
curl -X POST localhost:8000/api/conversations
curl -X POST localhost:8000/api/conversations/1/messages \
     -H 'Content-Type: application/json' \
     -d '{"client_message_id": "m1", "text": "What is reverse charge?"}'
curl -X POST localhost:8000/api/gst/calculate -H 'Content-Type: application/json' -d '{
  "supplier_gstin": "29AABCG1234K1ZO", "buyer_gstin": "27AACCM5678P1ZN", "invoice_date": "2025-10-01",
  "lines": [{"description": "Widget", "quantity": "2", "unit_price": "499.99", "rate": "18"}]}'
```

| Method | Path | Body |
|---|---|---|
| POST | `/api/conversations` | none. Returns `{"id"}` |
| POST | `/api/conversations/<id>/messages` | `{"client_message_id", "text"}`. Returns `{"message", "reply"}` |
| GET | `/api/conversations/<id>/messages` | none |
| POST | `/api/gst/calculate` | `{"supplier_gstin", "invoice_date", "lines": [...], "buyer_gstin"?, "place_of_supply"?, "sez"?}` |
| GET | `/healthz` | none |

## Rules

1. **The tests are the specification.** `tests/bot/test_task*.py` map to the tasks in TASKS.md.
   Read them: they say exactly what "working" means.
2. **Don't edit `tests/` or `fake_taxmodel/`.** The grader replaces both with its own copies, and it
   also runs extra tests that follow the same rules with different inputs and failure sequences.
   Code written to pass only the visible cases will fail those.
3. **Change anything else you like.** Refactor freely. Keep the HTTP API and the names the tests
   import working.
4. **Commit as you go**, with messages that say why, and keep `NOTES.md` up to date. Your git
   history and your notes are part of the assessment.
5. **Time budget: about 10 hours.** If you run out, stop and write down what you would do next.
   An honest, well-reasoned partial solution beats a rushed complete one.
6. **AI coding agents are allowed.** Work with the AI coding agent of your choice (Claude Code,
   Cursor, Copilot or any other), plus any documentation or search engine. You own the result:
   you must be able to explain every line you submit and every decision in your notes.
7. **Everything goes through the grader.** Never email code or notes. Your key stops
   working when your time window ends; anything not submitted by then does not count.

## Your clock, progress and submitting

You can read the code and set up before your clock starts. Your time window (10 hours unless
your invitation says otherwise) begins when you call `/start`, which you must do **before
27 Sep 2026, 23:59 IST**. After that date an unstarted key no longer works.

```bash
KEY=cand_a42bf07652c69728
GRADER=https://gst-bot-submission.jinacode.systems
curl -X POST -H "X-Candidate-Key: $KEY" $GRADER/start
```

Check your progress locally at any time:

```bash
uv run python progress.py          # one line per task; a task's visible part is done when all its tests pass
```

Submit **one task at a time, in order**. Task 2 unlocks when task 1 passes, and so on. A task
passes when all its visible tests and all its hidden checks pass. Every submission also re-runs the
tasks you've already cleared, and a regression there blocks the new task.

```bash
git bundle create submission.bundle --all
curl -X POST --data-binary @submission.bundle -H "X-Candidate-Key: $KEY" "$GRADER/submit?task=1"
curl -H "X-Candidate-Key: $KEY" $GRADER/status/<id from the reply>
curl -H "X-Candidate-Key: $KEY" $GRADER/progress
```

The status reply says pass or fail. Failing visible tests are listed in full; for hidden checks you
see which rule failed, not the inputs. Attempts are unlimited, but you can submit only once every
few minutes, so run the tests locally first.

Your `NOTES.md` travels inside every bundle, so there is nothing else to send. Make sure your
final notes are committed and in a submission before your time runs out.
