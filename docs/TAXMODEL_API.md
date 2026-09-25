# tax-model API

tax-model is the upstream service that answers GST questions the bot cannot answer from its own FAQ.
It is **shared, rate-limited and unreliable by design**: your key is throttled, and requests
sometimes fail in the ways listed below. The bot must cope with all of them.

You work against `fake_taxmodel/`, which behaves exactly as described here: the tests use it
in-process, and you can run it over HTTP (see the README). The grader uses the same fake.

## A1. Endpoint

```
POST /v1/chat/completions
Authorization: Bearer <api_key>
Content-Type: application/json
Idempotency-Key: <optional, see A5>
```

The request body uses the OpenAI chat-completions format (a subset). Streaming is not supported.

```json
{
  "model": "tax-model-gst",
  "messages": [{"role": "user", "content": "What is the GST rate on restaurant services?"}],
  "temperature": 0,
  "max_tokens": 512
}
```

A successful response is **HTTP 200**:

```json
{
  "id": "chatcmpl-3f9a1c2b7d4e",
  "object": "chat.completion",
  "created": 1790000000,
  "model": "tax-model-gst",
  "choices": [{"index": 0, "message": {"role": "assistant", "content": "..."}, "finish_reason": "stop"}],
  "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
}
```

Response headers:

| Header | On | Meaning |
|---|---|---|
| `X-Request-Id` | every response | Unique per HTTP request, replays included |
| `X-RateLimit-Limit` | every response to a valid, unexpired key | Bucket capacity (burst) for this key |
| `X-RateLimit-Remaining` | every response to a valid, unexpired key | Whole tokens left after this request, rounded down |

A drop-off (A4.5) carries these headers too. Only its body is cut short.

`GET /healthz` is never throttled and never fails on purpose.

## A2. Latency

| | Value |
|---|---|
| Normal response time | 0.2 – 1.5 s |
| Slow response | 3 – 8 s |
| Stall | 40 s, then a normal 200 |

The server keeps no connection open for longer than **45 s**. The client picks its own timeouts.
The server never enforces one on the client's behalf.

## A3. Rate limiting (per API key)

Each key gets a **token bucket**:

| Parameter | Value |
|---|---|
| Capacity (burst) | 5 |
| Refill | 20 tokens / minute (1 token every 3 s) |
| Initial state | full |

Every request that gets past authentication and idempotency replay (A6 steps 1–3) costs 1 token.
With no token available the server returns:

```
HTTP 429
Retry-After: <integer seconds, >= 1>
{"detail": "rate limit exceeded for key 'cand_…'"}
```

**Penalty for ignoring `Retry-After`.** A 429 opens a *throttle window* that ends at
`now + Retry-After`. **Every request that arrives before the window ends** gets another 429 and
**extends the window by 5 s**. The extension is capped so the window never ends more than 60 s from
now. The new `Retry-After` is the rounded-up time left in the window. Requests rejected this way
cost nothing, but they keep you locked out.

A client that honours `Retry-After` loses one short wait. A client that retries in a tight loop can
lock itself out for up to a minute.

`Retry-After` is **always a whole number of seconds**, never an HTTP-date.

## A4. Failure modes

Any request that gets past the rate limiter may fail in one of these ways.

| # | Mode | What the client sees | Did the server do the work? | Safe to retry? |
|---|---|---|---|---|
| A4.1 | **Slow** | 200 after 3–8 s | yes | n/a |
| A4.2 | **Stall** | 200 after 40 s | yes, even if the client gave up | with an `Idempotency-Key` |
| A4.3 | **Overloaded** | `503`, `Retry-After: 2`, body `{"detail": "upstream overloaded"}` | no | yes, after `Retry-After` |
| A4.4 | **Bad gateway** | `502`, `Content-Type: text/html`, body `<html><body><h1>502 Bad Gateway</h1></body></html>` | no | yes |
| A4.5 | **Drop-off** | Status `200` and full headers, including a `Content-Length` for the whole body. The server sends the **first half** of the body bytes, then closes the connection. | **yes** | with an `Idempotency-Key` |

In a drop-off the client gets a valid status line and then a broken body. In `httpx` this shows up
as `httpx.RemoteProtocolError`. A client that checks only the status code and then parses the body
will crash on the JSON parse.

**Non-retryable errors** (retrying never helps):

| Status | When |
|---|---|
| `400` | `"stream": true`, or an `Idempotency-Key` header that breaks the A5 format |
| `401` | Missing, unknown, or expired key |
| `422` | Body is not valid JSON, fails schema validation, or reuses an `Idempotency-Key` with a different body (A5) |

## A5. Idempotency

Send `Idempotency-Key: <1–64 chars of [A-Za-z0-9_-]>` to make a request safe to retry. Keys are
scoped to your API key and remembered for **600 s**.

| The server has already seen this `Idempotency-Key`… | Response |
|---|---|
| …and it finished with a 200 | The **stored 200 is replayed**, with `Idempotent-Replayed: true`. **Costs no token and cannot fail** (no A4 mode applies). |
| …and it is still processing (e.g. a stall) | `409`, `Retry-After: 1`, `{"detail": "request with this idempotency key is in progress"}` |
| …with a **different request body** | `422`, `{"detail": "idempotency key reused with a different payload"}` |
| …and it failed with 502 or 503 | Nothing was stored, so the request runs fresh (normal cost, normal failure chances) |

Drop-offs (A4.5) and stalls (A4.2) **are** stored, because the server finished the work. Retrying
them with the same key gets a free replay. Retrying them without a key does the work again, costs
another token, and can fail again.

"Same body" means the SHA-256 of the raw request bytes is identical.

## A6. Evaluation order

For each `POST /v1/chat/completions`:

1. **Authenticate and validate.** Failures return 400 / 401 / 422 and cost nothing. When a
   request has several problems, which one is reported is not specified.
2. **Idempotency conflict.** A key seen with a different body returns 422. A key still in progress
   returns 409. Neither costs anything.
3. **Idempotency replay.** A completed key returns the stored 200 at no cost. Processing stops here.
4. **Rate limit (A3).** Returns 429, or takes 1 token.
5. **Failure roll (A4).** The server decides whether this request fails and how.
6. **Do the work** and return 200. If an `Idempotency-Key` was sent, the result is stored before
   the response body is written, so a drop-off can still be replayed.

## A7. Answers

Puzzle keys get deterministic answers from a fixed GST corpus. The same question always gets the
same answer, byte-for-byte. The lookup key is the text of the **last `user` message**, lowercased,
with runs of whitespace collapsed to one space and trimmed. A question not in the corpus gets:

```
I can only answer questions about Indian GST. Please rephrase your question.
```

## A8. Key lifetime

A key is valid only inside its assessment window. After the window, every request returns
`401 {"detail": "api key expired"}`.
