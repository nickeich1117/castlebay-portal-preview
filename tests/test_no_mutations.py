"""Bright-line guard: refuse to ship if any code calls Monday with a mutation.

This is the first line of the read-only contract (READ_ONLY_GUARANTEES.md).
If this test fails, do NOT bypass it — the preview app is not allowed to
introduce any write paths. Fix the offending code instead.
"""
import pathlib
import re

import pytest

from app.monday_read import (
    MondayReadClient,
    MutationBlockedError,
    _is_mutation,
)


def test_mutation_pattern_matches_obvious_mutation():
    assert _is_mutation("mutation { foo(id: 1) { id } }")


def test_mutation_pattern_matches_with_variables():
    assert _is_mutation("mutation Foo($id: ID!) { foo(id: $id) { id } }")


def test_mutation_pattern_matches_lowercase_or_uppercase():
    assert _is_mutation("MUTATION { foo { id } }")


def test_mutation_pattern_does_not_false_positive_on_query_with_field_named_mutation():
    # A query that asks for a field literally called 'mutation' should not be blocked.
    # (Unlikely in Monday, but be precise.)
    q = "query { boards { mutation_field } }"
    assert not _is_mutation(q)


def test_client_blocks_mutation():
    c = MondayReadClient(api_key="fake")
    with pytest.raises(MutationBlockedError):
        c.query("mutation { create_item(board_id: 1) { id } }")


def test_repo_contains_no_mutation_strings():
    """Walk all .py files in the app/ tree, fail if any contain 'mutation' in a GraphQL string.

    This catches `gql = "mutation ..."` even before runtime.
    Allowed exceptions: this test file, monday_read.py (which mentions 'mutation' in
    error messages and comments only).
    """
    repo = pathlib.Path(__file__).resolve().parent.parent
    app_dir = repo / "app"
    pattern = re.compile(r"\bmutation\s*[\s({]", re.IGNORECASE)
    allowed = {"monday_read.py"}

    offenders = []
    for f in app_dir.rglob("*.py"):
        if f.name in allowed:
            continue
        text = f.read_text()
        # Check inside string literals only (rough heuristic — line contains a quote AND mutation)
        for i, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line) and ('"' in line or "'" in line):
                offenders.append(f"{f.relative_to(repo)}:{i}  {line.strip()}")
    assert not offenders, "Mutation strings found in app code:\n" + "\n".join(offenders)


def test_monday_read_module_exposes_no_mutate_helper():
    import app.monday_read as m
    forbidden = {"mutate", "create_item", "update_item", "delete_item", "write", "post"}
    public = {n for n in dir(m) if not n.startswith("_")}
    overlap = public & forbidden
    assert not overlap, f"Forbidden write helpers exposed: {overlap}"
