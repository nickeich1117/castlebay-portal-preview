# Read-Only Guarantees

This preview app uses the **production Monday.com API token** but is contractually read-only. Three layers prevent any write from reaching Monday.

## Layer 1 — Code-level mutation ban

Every Monday call goes through `app/monday_read.py::MondayReadClient.query()`. That method:

- Uses a regex to detect any string starting with the GraphQL keyword `mutation` (followed by space, `{`, or `(`).
- Raises `MutationBlockedError` *before* any HTTP request is made.
- Logs the rejection at ERROR level with the offending query's first 120 chars.

There is **no** `mutate()` method on the client. No write helpers. No `create_item`, `update_item`, `delete_item`, `add_update`. The single public surface is `query()`.

## Layer 2 — Repo-wide mutation guard (CI)

`tests/test_no_mutations.py::test_repo_contains_no_mutation_strings` walks every `.py` file under `app/` and fails if a line contains the keyword `mutation` inside what looks like a string literal. Exception: `monday_read.py` itself, which references the word in error messages.

`tests/test_no_mutations.py::test_monday_read_module_exposes_no_mutate_helper` asserts that the module never grows public functions named `mutate`, `create_item`, `update_item`, `delete_item`, `write`, or `post`.

CI must run `pytest tests/test_no_mutations.py` before any deploy. Render's build step runs `pip install -r requirements.txt`; add `pytest tests/test_no_mutations.py` to that step before going live for external review.

## Layer 3 — Audit logging

Every Monday call is logged at INFO level with:

- The operation signature (e.g. `query:boards`)
- The cache hit/miss status

If a mutation ever does fire (despite layers 1 and 2), it will appear in the Render logs as an ERROR with the query body. Operationally:

```
$ render logs --service castlebay-portal-preview | grep "Mutation blocked"
```

Should always return zero matches in steady state.

## What the preview is allowed to do

- Read boards, groups, items, column values from Monday.
- Display them to logged-in CastleBay internal users.
- Cache responses in memory for 5 minutes per the `PREVIEW_CACHE_TTL_SECONDS` env var.

## What the preview is forbidden to do

- Send any GraphQL `mutation`.
- Upload files (no `/v2/file` endpoint usage).
- Call any Monday endpoint other than `/v2`.
- Persist Monday data to disk beyond the in-memory cache.

## Backlog item before external review

The Monday API token currently shared with prod is read+write scoped. Before David, Don, or any vendor sees the preview at a real URL, cut a **read-only Monday token** in Monday admin and swap it in via the Render dashboard. That moves the read-only guarantee from "code discipline" to "Monday-side enforcement" — the strongest version of this contract.

Tracked in `~/castlebay/claude/portal-mocks-2026-05-08/BACKLOG.md` as **BL-NEW**.

## How to verify in production

```bash
# Hit the health endpoint
curl https://castlebay-portal-preview.onrender.com/health
# Expect: {"status": "ok", "monday_configured": true, "mode": "preview · read-only"}

# Tail logs and confirm only `query:` operations appear
render logs --service castlebay-portal-preview --tail | grep "monday_read query"

# Confirm zero mutation attempts
render logs --service castlebay-portal-preview | grep -c "Mutation blocked"
# Expect: 0
```
