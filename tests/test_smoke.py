"""Smoke tests — every route returns a sensible response."""
import os
import tempfile

import pytest
from fastapi.testclient import TestClient

# Use a unique temp DB path per pytest session so stale state can never bleed in.
_TMP_DB = os.path.join(tempfile.gettempdir(), "preview-test.db")
os.environ["PREVIEW_DB_PATH"] = _TMP_DB
os.environ.setdefault("PREVIEW_SESSION_SECRET", "test")

# Always nuke the DB before importing app (app imports cache config at import time)
if os.path.exists(_TMP_DB):
    os.remove(_TMP_DB)

from app.auth import register_user
from app.db import get_user_by_email, init_db
from app.main import app


@pytest.fixture(scope="module")
def client():
    # Defensive: re-clean in case something else touched the path between import and fixture
    if os.path.exists(_TMP_DB):
        os.remove(_TMP_DB)
    init_db()
    if not get_user_by_email("test@example.com"):
        register_user("test@example.com", "testpassword12", "Test User", "cb_internal")
    return TestClient(app)


@pytest.fixture
def auth_client(client):
    """Logged-in client."""
    resp = client.post(
        "/login",
        data={"email": "test@example.com", "password": "testpassword12"},
        follow_redirects=False,
    )
    assert resp.status_code == 303, f"Login failed: {resp.status_code} {resp.text[:200]}"
    return client


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["mode"] == "preview · read-only"


def test_login_page_renders(client):
    r = client.get("/login")
    assert r.status_code == 200
    assert "Sign in" in r.text


def test_login_rejects_bad_password(client):
    r = client.post(
        "/login",
        data={"email": "test@example.com", "password": "wrong"},
        follow_redirects=False,
    )
    assert r.status_code == 401


def test_root_redirects_to_login_when_unauthenticated(client):
    # Drop any cookies first
    client.cookies.clear()
    r = client.get("/", follow_redirects=False)
    # Either 303 to /boards which then redirects to /login, or directly to /login
    assert r.status_code in (302, 303, 307)


@pytest.mark.parametrize("path", [
    "/boards", "/drilldown", "/kanban", "/vendor",
    "/interviewer", "/feedback", "/feedback/04766",
])
def test_authed_routes_render(auth_client, path):
    r = auth_client.get(path, follow_redirects=False)
    # 200 OK, or 303 if there's a cascade redirect — both are non-error
    assert r.status_code in (200, 303), f"{path} returned {r.status_code}: {r.text[:200]}"
