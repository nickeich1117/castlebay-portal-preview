"""
Monday.com read-only client.

Three layers of write-prevention (see READ_ONLY_GUARANTEES.md):
  1. MutationBlockedError raised if a query string contains 'mutation'
  2. Single MondayReadClient class — only `query()` method, no write helpers
  3. Audit logging — every call logs the operation type for forensic review

Cache: 5-min in-memory cache (TTL from PREVIEW_CACHE_TTL_SECONDS).
Cache key is a SHA1 of (query, variables) so identical queries dedupe.
"""

import hashlib
import json
import logging
import re
import time
from typing import Any, Optional

import httpx

from app.config import (
    CACHE_TTL_S,
    MONDAY_API_KEY,
    MONDAY_API_URL,
    MONDAY_API_VERSION,
    MONDAY_TIMEOUT_S,
)

logger = logging.getLogger("monday_read")


class MutationBlockedError(RuntimeError):
    """Raised when a GraphQL query contains a mutation. Hard refusal."""


class MondayAPIError(RuntimeError):
    """Raised when Monday returns errors."""


# Pattern matches 'mutation ' or 'mutation{' or 'mutation(' as a top-level keyword.
# Won't false-positive on a field literally named "mutation" inside a query body.
_MUTATION_PATTERN = re.compile(r"\bmutation\s*[\s({]", re.IGNORECASE)


def _is_mutation(query: str) -> bool:
    """True if the query contains a GraphQL mutation operation."""
    return bool(_MUTATION_PATTERN.search(query))


def _cache_key(query: str, variables: Optional[dict]) -> str:
    raw = query + "::" + json.dumps(variables or {}, sort_keys=True)
    return hashlib.sha1(raw.encode()).hexdigest()


class _Cache:
    def __init__(self, ttl: int = CACHE_TTL_S):
        self.ttl = ttl
        self._store: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Optional[Any]:
        if key not in self._store:
            return None
        expires_at, value = self._store[key]
        if time.time() > expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        self._store[key] = (time.time() + self.ttl, value)

    def clear(self) -> None:
        self._store.clear()


class MondayReadClient:
    """Read-only Monday.com GraphQL client.

    Refuses any query containing the keyword 'mutation'. There is no `mutate()`
    method — this is intentional. Adding one is a code-review bright-line.
    """

    def __init__(self, api_key: str = "", cache: Optional[_Cache] = None):
        self.api_key = api_key or MONDAY_API_KEY
        self.cache = cache or _Cache()

    def configured(self) -> bool:
        return bool(self.api_key)

    def query(self, gql: str, variables: Optional[dict] = None) -> dict:
        """Run a GraphQL query. Raises MutationBlockedError if mutation detected."""
        if _is_mutation(gql):
            logger.error("Mutation blocked: %s", gql[:120])
            raise MutationBlockedError(
                "Mutations are forbidden in the preview app. "
                "Read-only contract — see READ_ONLY_GUARANTEES.md"
            )

        # Forensic logging — every call recorded with op signature
        op_signature = self._extract_op_signature(gql)
        logger.info("monday_read query op=%s", op_signature)

        if not self.api_key:
            raise MondayAPIError("MONDAY_API_KEY is not set")

        cache_key = _cache_key(gql, variables)
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        headers = {
            "Authorization": self.api_key,
            "Content-Type": "application/json",
            "API-Version": MONDAY_API_VERSION,
        }
        body = {"query": gql, "variables": variables or {}}

        try:
            resp = httpx.post(
                MONDAY_API_URL,
                json=body,
                headers=headers,
                timeout=MONDAY_TIMEOUT_S,
            )
        except httpx.RequestError as e:
            raise MondayAPIError(f"Monday request failed: {e}") from e

        if resp.status_code >= 400:
            raise MondayAPIError(f"Monday HTTP {resp.status_code}: {resp.text[:300]}")

        payload = resp.json()
        if "errors" in payload and payload["errors"]:
            raise MondayAPIError(f"Monday GraphQL errors: {payload['errors']}")

        data = payload.get("data", {})
        self.cache.set(cache_key, data)
        return data

    @staticmethod
    def _extract_op_signature(gql: str) -> str:
        """Return a short signature like 'query:boards' for logging."""
        match = re.search(r"\b(query|fragment)\b[\s\w]*\{?\s*(\w+)", gql)
        if match:
            return f"{match.group(1)}:{match.group(2)}"
        return "unknown"


# Module-level singleton
_client: Optional[MondayReadClient] = None


def get_client() -> MondayReadClient:
    global _client
    if _client is None:
        _client = MondayReadClient()
    return _client


# ──────────────────────────────────────────────────────────────────────────────
# High-level read functions used by routes
# ──────────────────────────────────────────────────────────────────────────────


def get_board_summary(board_id: str) -> dict:
    """Return board name + groups + item count, for the boards index."""
    gql = """
    query ($id: [ID!]) {
      boards(ids: $id) {
        id
        name
        groups { id title }
        items_count
      }
    }
    """
    data = get_client().query(gql, {"id": [board_id]})
    boards = data.get("boards") or []
    return boards[0] if boards else {}


def get_board_groups(board_id: str) -> list[dict]:
    """Return groups (= roles) for a board."""
    gql = """
    query ($id: [ID!]) {
      boards(ids: $id) {
        groups { id title }
      }
    }
    """
    data = get_client().query(gql, {"id": [board_id]})
    boards = data.get("boards") or []
    return boards[0].get("groups", []) if boards else []


def get_group_items(board_id: str, group_id: str, limit: int = 50) -> list[dict]:
    """Return items in a single group with column values."""
    gql = """
    query ($board: [ID!], $group: [String!], $limit: Int!) {
      boards(ids: $board) {
        groups(ids: $group) {
          items_page(limit: $limit) {
            items {
              id
              name
              created_at
              updated_at
              column_values {
                id
                text
                value
              }
            }
          }
        }
      }
    }
    """
    data = get_client().query(
        gql, {"board": [board_id], "group": [group_id], "limit": limit}
    )
    boards = data.get("boards") or []
    if not boards:
        return []
    groups = boards[0].get("groups") or []
    if not groups:
        return []
    page = groups[0].get("items_page") or {}
    return page.get("items", [])


def get_board_pipeline_counts(board_id: str) -> dict:
    """Return rough pipeline buckets for a board.

    Walks all items, groups by status text. Cached upstream so this is cheap
    after the first hit.
    """
    gql = """
    query ($id: [ID!]) {
      boards(ids: $id) {
        items_page(limit: 200) {
          items {
            id
            column_values { id text }
          }
        }
      }
    }
    """
    data = get_client().query(gql, {"id": [board_id]})
    boards = data.get("boards") or []
    if not boards:
        return {"total": 0, "buckets": {}}

    items = boards[0].get("items_page", {}).get("items", [])
    buckets: dict[str, int] = {}
    for item in items:
        # Status column ID varies per board; for now just count all items
        # and use any column whose text matches one of our display buckets.
        for cv in item.get("column_values", []):
            text = (cv.get("text") or "").strip()
            if text in {"Submitted", "In Review", "Interview", "Placed", "Declined", "On Hold"}:
                buckets[text] = buckets.get(text, 0) + 1
                break
    return {"total": len(items), "buckets": buckets}
