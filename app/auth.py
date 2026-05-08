"""Auth — bcrypt + sessions. Mirrors prod's `vendor_portal.auth` pattern."""
from typing import Optional

import bcrypt

from app.db import (
    create_session,
    create_user,
    delete_session,
    get_user_by_email,
    validate_session,
)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def register_user(
    email: str,
    password: str,
    display_name: str = "",
    role: str = "cb_internal",
) -> dict:
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")
    return create_user(email, hash_password(password), display_name, role)


def login(email: str, password: str) -> Optional[tuple[str, dict]]:
    user = get_user_by_email(email)
    if not user or not user.get("active"):
        return None
    if not verify_password(password, user["password_hash"]):
        return None
    token = create_session(user["id"])
    return token, user


def logout(token: str) -> None:
    delete_session(token)


def get_current_user(token: Optional[str]) -> Optional[dict]:
    if not token:
        return None
    return validate_session(token)
