"""Standalone verifier — runs the read-only guard checks without pytest.

Useful as a pre-commit hook or quick sanity check during development.
Exits 0 if all checks pass, non-zero otherwise.
"""
import os
import pathlib
import re
import sys

# Add project root to path
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PATTERN = re.compile(r"\bmutation\s*[\s({]", re.IGNORECASE)
ALLOWED = {"monday_read.py"}

failures = []


def check_pattern():
    if not PATTERN.search("mutation { foo }"):
        failures.append("Pattern does not match 'mutation { foo }'")
    if PATTERN.search("query { mutation_field }"):
        failures.append("Pattern false-positives on 'mutation_field'")


def check_repo():
    app_dir = ROOT / "app"
    for f in app_dir.rglob("*.py"):
        if f.name in ALLOWED:
            continue
        text = f.read_text()
        for i, line in enumerate(text.splitlines(), start=1):
            if PATTERN.search(line) and ('"' in line or "'" in line):
                failures.append(f"Mutation in {f.relative_to(ROOT)}:{i}  {line.strip()}")


def check_module_surface():
    try:
        import app.monday_read as m
    except ImportError as e:
        failures.append(f"Cannot import monday_read: {e}")
        return
    forbidden = {"mutate", "create_item", "update_item", "delete_item", "write", "post"}
    public = {n for n in dir(m) if not n.startswith("_")}
    overlap = public & forbidden
    if overlap:
        failures.append(f"Forbidden write helpers exposed: {overlap}")


def check_client_blocks():
    try:
        from app.monday_read import MondayReadClient, MutationBlockedError
    except ImportError as e:
        failures.append(f"Cannot import client: {e}")
        return
    c = MondayReadClient(api_key="fake")
    try:
        c.query("mutation { create_item(board_id: 1) { id } }")
        failures.append("Client did not raise on mutation!")
    except MutationBlockedError:
        pass


def main() -> int:
    check_pattern()
    check_repo()
    check_module_surface()
    check_client_blocks()

    if failures:
        print("FAILURES:")
        for f in failures:
            print(f"  ✗ {f}")
        return 1
    print("✓ Read-only contract holds")
    print("  · mutation pattern works")
    print("  · no mutation strings in app/ code")
    print("  · monday_read exposes no write helpers")
    print("  · client raises MutationBlockedError on mutation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
