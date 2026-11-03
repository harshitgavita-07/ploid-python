# ploid-python

A zero-dependency Python SDK for the [Ploid](https://ploid.com) people-data API
(search, resolve, enrich, datasets, monitors, LinkedIn/GitHub/social
intelligence, technographics).

**Unofficial.** Built from Ploid's public OpenAPI 2.0.0 document
(`https://api.ploid.com/v1/openapi.json`, 37 paths / 41 operations) and covers
every operation in it. Not affiliated with or endorsed by Ploid.

Pure standard library - no `requests`, no `httpx`, nothing to install.

```bash
pip install ./ploid-python   # or copy the ploid/ package into your project
```

## Quickstart

```python
import ploid

client = ploid.Client("pld_...")            # Bearer auth (default)
# client = ploid.Client("pld_...", auth_scheme="x-api-key")  # also supported

# Who am I, what do I have left?
print(client.account.credits())

# Resolve one person (free when nothing is found)
person = client.resolve_person({"name": "Kamran Karic", "company": "Ploid"})

# Search; big or async searches come back 202 with a People Set handoff
res = client.search.people({"query": "AI security founders in San Francisco", "num_results": 10})
if res.http_status == 202:
    done = client.search.wait_for_set(res)   # polls items_url until complete
    for item in done.items:
        print(item)

# Fill columns for rows you already have (async for >25 rows)
ds = client.datasets.create({"rows": [...], "columns": [...], "mode": "async"})
client.datasets.wait_until_ready(ds.dataset_id)
for row in client.datasets.rows_all(ds.dataset_id):
    print(row)

# Deep person research runs in the background; poll or wait
accepted = client.person.get({"person_id": "p_..."}, )
if accepted.http_status == 202:
    final = client.person.wait_for_run(accepted.run_id)
```

## What's in the box

- **Full coverage**: all 41 operations in the public spec, grouped into
  `search`, `companies`, `person`, `monitors`, `datasets`, `github`,
  `linkedin`, `account`, `harness` plus `resolve_person`, `reverse_email`,
  `technographics`, `enrich_person`, `enrich_social`.
- **Typed errors** mapped from Ploid's `PublicApiError` body:
  `AuthenticationError` (401), `PaymentRequiredError` (402),
  `PermissionDeniedError` (403), `NotFoundError` (404), `ConflictError` (409),
  `GoneError` (410), `PayloadTooLargeError` (413), `ValidationError`
  (400/422), `RateLimitError` (429, with `retry_after`), `ServerError` (5xx).
  `code`, `request_id`, `retryable` and `unavailable_fields` are preserved.
- **Retry discipline**: 429s honor `Retry-After`; 5xx uses exponential backoff
  with jitter; 4xx is never retried.
- **Idempotency keys** auto-generated for POST/PATCH (stable across internal
  retries) and overridable per call.
- **Async helpers**: `wait_for_set`, `person.wait_for_run`,
  `datasets.wait_until_ready`, `monitors.wait_for_run` with deadlines.
- **Cursor pagination iterators**: `monitors.list_all()`, `runs_all()`,
  `items_all()`, `datasets.rows_all()`.
- **SSE parser** (`ploid.iter_sse`) for People Set event streams.
- **Additive-change tolerant models**: responses are `PloidObject` (a dict
  with attribute access); new API fields never break the SDK.

## Tests

29 unit tests run against a scripted in-process mock server (no network):

```bash
cd tests && PYTHONPATH=..:. python3 -m unittest test_client
```

Live tests against the real API are included but skip without credentials.
They are split so the default tier is **uncharged** (account metadata reads,
the public OpenAPI document, auth-failure shape):

```bash
PLOID_API_KEY=pld_... PYTHONPATH=..:. python3 -m unittest test_live
```

Operations that consume workspace credits (ACU) only run when you opt in a
second time:

```bash
PLOID_API_KEY=pld_... PLOID_LIVE_CHARGED=1 PYTHONPATH=..:. python3 -m unittest test_live
```

## Notes

- Billing: most search/enrich/research operations consume workspace ACU
  credits. `GET /v1/account/credits` shows your balance and key budget.
- `resolve` is documented as free when nothing is found; `technographics` is
  free when no technology is found. The SDK does not change billing - check
  Ploid's docs for current pricing.
- Built by [Harshit Gavita](https://github.com/harshitgavita-07) as a proof of
  work. Issues and PRs welcome.
