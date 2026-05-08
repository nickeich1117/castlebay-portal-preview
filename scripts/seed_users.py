"""Seed initial users. Idempotent — safe to re-run.

Usage:
    python scripts/seed_users.py

Reads passwords from env (so they don't end up in git history):
    PREVIEW_NICK_PW   — Nick's initial password
    PREVIEW_DAVID_PW  — David's initial password
    PREVIEW_DON_PW    — Don's initial password

If any are unset, generates a random 16-char password and prints it to stdout
(only at first creation — re-runs don't reset).
"""
import os
import secrets
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.auth import register_user
from app.db import get_user_by_email, init_db

USERS = [
    {"email": "nick@securuscsi.com", "name": "Nick Eichelberger", "env": "PREVIEW_NICK_PW"},
    {"email": "david@castlebayconsulting.com", "name": "David Durbin", "env": "PREVIEW_DAVID_PW"},
    {"email": "don@castlebayconsulting.com", "name": "Don MacFarland", "env": "PREVIEW_DON_PW"},
]


def main() -> int:
    init_db()
    print("Seeding users into preview.db...")
    print()
    created = 0
    for u in USERS:
        existing = get_user_by_email(u["email"])
        if existing:
            print(f"  exists  {u['email']}")
            continue
        pw = os.getenv(u["env"]) or secrets.token_urlsafe(12)
        register_user(
            email=u["email"],
            password=pw,
            display_name=u["name"],
            role="cb_internal",
        )
        print(f"  CREATED {u['email']}  password: {pw}  (display: {u['name']})")
        created += 1
    print()
    print(f"{created} new user(s) created. Save those passwords somewhere safe.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
