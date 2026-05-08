"""All HTTP routes for the preview app.

Internal mocks (boards, drilldown, kanban) pull live data from Monday.
Vendor mocks (vendor, feedback inbox, single feedback) and interviewer mock
render with static demo data — they're UX previews, not data demos.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth import get_current_user, login as auth_login, logout as auth_logout
from app.config import ACTIVE_BOARDS
from app.db import cursor as db_cursor
from app.monday_read import (
    MondayAPIError,
    MutationBlockedError,
    get_board_groups,
    get_board_pipeline_counts,
    get_client,
    get_group_items,
)

logger = logging.getLogger("routes")
router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


# ──────────────────────────────────────────────────────────────────────────────
# Auth helpers
# ──────────────────────────────────────────────────────────────────────────────


def _require_user(request: Request) -> dict:
    token = request.cookies.get("session")
    user = get_current_user(token)
    if not user:
        raise HTTPException(status_code=302, headers={"Location": "/login"})
    return user


# ──────────────────────────────────────────────────────────────────────────────
# Login / logout
# ──────────────────────────────────────────────────────────────────────────────


@router.get("/login", response_class=HTMLResponse)
def login_get(request: Request, error: Optional[str] = None):
    return templates.TemplateResponse(
        request, "login.html", {"error": error, "user": None}
    )


@router.post("/login")
def login_post(request: Request, email: str = Form(...), password: str = Form(...)):
    result = auth_login(email, password)
    if not result:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Invalid email or password.", "email": email, "user": None},
            status_code=401,
        )
    token, _user = result
    response = RedirectResponse("/", status_code=303)
    secure = request.url.scheme == "https"
    response.set_cookie(
        "session", token, httponly=True, secure=secure, samesite="lax", max_age=60 * 60 * 24,
    )
    return response


@router.get("/logout")
def logout(request: Request):
    token = request.cookies.get("session")
    if token:
        auth_logout(token)
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie("session")
    return response


# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────


PIPELINE_COLORS = {
    "Submitted": "#6c7a89",
    "In Review": "var(--accent)",
    "Interview": "var(--navy-2)",
    "Placed": "var(--success)",
    "Declined": "var(--text-3)",
    "On Hold": "var(--warn)",
}


def _enrich_board(board: dict) -> dict:
    """Pull live counts for one board, fall back to None on error."""
    out = {**board, "role_count": None, "total_candidates": None,
           "pipeline_pct": {}, "pipeline_colors": PIPELINE_COLORS}
    try:
        groups = get_board_groups(board["id"])
        out["role_count"] = len(groups)
        counts = get_board_pipeline_counts(board["id"])
        out["total_candidates"] = counts.get("total", 0)
        buckets = counts.get("buckets", {})
        total = sum(buckets.values()) or 1
        out["pipeline_pct"] = {
            stage: int(round(100 * buckets.get(stage, 0) / total))
            for stage in PIPELINE_COLORS if buckets.get(stage)
        }
    except (MondayAPIError, MutationBlockedError, Exception) as e:
        logger.warning("Board %s enrichment failed: %s", board["id"], e)
    return out


def _all_boards_enriched() -> tuple[list[dict], Optional[str]]:
    """Return all boards with live counts. Second item is monday_error string or None."""
    monday_error = None
    if not get_client().configured():
        return (
            [{**b, "role_count": None, "total_candidates": None,
              "pipeline_pct": {}, "pipeline_colors": PIPELINE_COLORS}
             for b in ACTIVE_BOARDS],
            "MONDAY_API_KEY not set",
        )
    try:
        boards = [_enrich_board(b) for b in ACTIVE_BOARDS]
    except Exception as e:
        monday_error = str(e)
        boards = [{**b, "role_count": None, "total_candidates": None,
                  "pipeline_pct": {}, "pipeline_colors": PIPELINE_COLORS}
                 for b in ACTIVE_BOARDS]
    return boards, monday_error


# ──────────────────────────────────────────────────────────────────────────────
# Dashboard (root)
# ──────────────────────────────────────────────────────────────────────────────


def _sync_decorate(b: dict) -> dict:
    """Add sync_class / sync_label / status_label / last_fetched fields based on data presence."""
    out = dict(b)
    if b.get("total_candidates") is None:
        out["sync_class"] = "error"
        out["sync_label"] = "error"
        out["status_label"] = "Error"
        out["last_fetched"] = "—"
    else:
        out["sync_class"] = "fresh"
        out["sync_label"] = "live"
        out["status_label"] = "Healthy"
        out["last_fetched"] = "≤ 5 min ago"
    return out


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    user = _require_user(request)
    boards_raw, monday_error = _all_boards_enriched()
    boards = [_sync_decorate(b) for b in boards_raw]

    # Aggregate KPIs from what we have
    open_roles = sum((b.get("role_count") or 0) for b in boards) or None
    in_flight = sum((b.get("total_candidates") or 0) for b in boards) or None
    active_boards = len([b for b in boards if b.get("total_candidates") is not None])

    kpis = {
        "open_roles": open_roles,
        "in_flight": in_flight,
        "interviews_week": None,   # backlog — needs cb_interview_date scan
        "placements_mtd": None,    # backlog — needs historical snapshots
        "active_boards": active_boards,
    }

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "user": user,
            "active_nav": "dashboard",
            "kpis": kpis,
            "boards": boards,
            "monday_error": monday_error,
            "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        },
    )


@router.get("/boards")
def boards_legacy_redirect():
    """Backward compat — old /boards URL now lands on dashboard."""
    return RedirectResponse("/", status_code=303)


# ──────────────────────────────────────────────────────────────────────────────
# Live data: drill-down
# ──────────────────────────────────────────────────────────────────────────────


def _short(name: str) -> str:
    """Strip the '2026 — ' prefix for compact column headers."""
    return name.replace("2026 — ", "").replace("2026 - ", "")


@router.get("/drilldown")
def drilldown_legacy_redirect(board_id: Optional[str] = None, role_id: Optional[str] = None):
    """Backward compat — /drilldown was renamed to /pipeline."""
    qs = ""
    if board_id:
        qs = f"?board_id={board_id}"
        if role_id:
            qs += f"&role_id={role_id}"
    return RedirectResponse(f"/pipeline{qs}", status_code=303)


@router.get("/pipeline", response_class=HTMLResponse)
def pipeline(request: Request, board_id: Optional[str] = None,
             role_id: Optional[str] = None, view: str = "list"):
    user = _require_user(request)

    boards = [{**_enrich_board(b), "short_name": _short(b["name"])} for b in ACTIVE_BOARDS]

    active_board = None
    if board_id:
        active_board = next((b for b in boards if b["id"] == board_id), None)
    if not active_board and boards:
        active_board = boards[0]

    roles = []
    monday_error = None
    if active_board and get_client().configured():
        try:
            groups = get_board_groups(active_board["id"])
            roles = [{"id": g["id"], "title": g["title"]} for g in groups]
        except Exception as e:
            monday_error = f"Couldn't fetch roles: {e}"

    active_role = None
    stages = []
    if role_id and active_board:
        active_role = next((r for r in roles if r["id"] == role_id), None)
        if active_role:
            try:
                items = get_group_items(active_board["id"], role_id, limit=50)
            except Exception as e:
                items = []
                monday_error = f"Couldn't fetch candidates: {e}"

            # Bucket items by status text
            stage_defs = [
                ("Submitted",  "submitted"),
                ("In Review",  "review"),
                ("Interview",  "interview"),
                ("Placed",     "placed"),
                ("Declined",   "declined"),
                ("On Hold",    "hold"),
            ]
            buckets: dict[str, list[dict]] = {name: [] for name, _ in stage_defs}
            for item in items:
                status_text = ""
                vendor_text = ""
                rate_text = ""
                for cv in item.get("column_values", []):
                    text = (cv.get("text") or "").strip()
                    cid = cv.get("id", "")
                    if text in buckets and not status_text:
                        status_text = text
                    if "vendor" in cid.lower() or "source" in cid.lower():
                        if not vendor_text and text:
                            vendor_text = text
                    if "rate" in cid.lower() and not rate_text and text:
                        rate_text = text
                bucket = status_text or "Submitted"
                buckets.setdefault(bucket, []).append({
                    "id": item.get("id", "")[-5:],
                    "title": (item.get("name") or "")[:60],
                    "vendor": vendor_text or "—",
                    "rate": rate_text,
                    "when": "",
                })

            for name, dot in stage_defs:
                stages.append({"name": name, "dot_class": dot, "candidates": buckets.get(name, [])})

    return templates.TemplateResponse(
        request,
        "pipeline.html",
        {
            "user": user,
            "active_nav": "pipeline",
            "boards": boards,
            "active_board": active_board,
            "roles": roles,
            "active_role": active_role,
            "stages": stages,
            "monday_error": monday_error,
            "view": "kanban" if view == "kanban" else "list",
        },
    )


# ──────────────────────────────────────────────────────────────────────────────
# Static demo pages (kanban, vendor, feedback, interviewer) — wrapped via Jinja
# ──────────────────────────────────────────────────────────────────────────────


@router.get("/kanban")
def kanban_legacy_redirect():
    """Backward compat — kanban is now a view of /pipeline."""
    return RedirectResponse("/pipeline?view=kanban", status_code=303)


@router.get("/vendor", response_class=HTMLResponse)
def vendor(request: Request):
    user = _require_user(request)
    return templates.TemplateResponse(
        request, "C_vendor.html",
        {"user": user, "active_nav": "vendor"},
    )


@router.get("/interviewer", response_class=HTMLResponse)
def interviewer(request: Request):
    user = _require_user(request)
    return templates.TemplateResponse(
        request, "D_interviewer.html",
        {"user": user, "active_nav": "interviewer"},
    )


@router.get("/feedback", response_class=HTMLResponse)
def feedback_inbox(request: Request):
    user = _require_user(request)
    return templates.TemplateResponse(
        request, "G_feedback_inbox.html",
        {"user": user, "active_nav": "feedback"},
    )


@router.get("/feedback/{candidate_id}", response_class=HTMLResponse)
def feedback_detail(request: Request, candidate_id: str):
    user = _require_user(request)
    return templates.TemplateResponse(
        request, "F_vendor_feedback.html",
        {"user": user, "active_nav": "feedback",
         "candidate_id": candidate_id},
    )


# ──────────────────────────────────────────────────────────────────────────────
# Audit
# ──────────────────────────────────────────────────────────────────────────────


@router.get("/audit", response_class=HTMLResponse)
def audit(request: Request, tab: str = "actions"):
    user = _require_user(request)

    rows: list[dict] = []
    sessions: list[dict] = []
    logins: list[dict] = []

    if tab == "sessions":
        # Pull active sessions from local DB
        with db_cursor() as c:
            db_rows = c.execute(
                """
                SELECT u.email, u.display_name, s.created_at, s.expires_at
                FROM sessions s JOIN users u ON s.user_id = u.id
                ORDER BY s.created_at DESC
                """
            ).fetchall()
        sessions = [dict(r) for r in db_rows]

    return templates.TemplateResponse(
        request,
        "audit.html",
        {
            "user": user,
            "active_nav": "audit",
            "tab": tab if tab in ("actions", "logins", "sessions") else "actions",
            "rows": rows,
            "sessions": sessions,
            "logins": logins,
        },
    )


# ──────────────────────────────────────────────────────────────────────────────
# Sync status
# ──────────────────────────────────────────────────────────────────────────────


@router.get("/sync", response_class=HTMLResponse)
def sync_status(request: Request):
    user = _require_user(request)
    boards_raw, monday_error = _all_boards_enriched()
    boards = [_sync_decorate(b) for b in boards_raw]
    return templates.TemplateResponse(
        request,
        "sync.html",
        {
            "user": user,
            "active_nav": "sync",
            "boards": boards,
            "monday_error": monday_error,
            "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "token_type": "prod token (read+write scope)" if get_client().configured() else "not configured",
        },
    )


# ──────────────────────────────────────────────────────────────────────────────
# Healthcheck
# ──────────────────────────────────────────────────────────────────────────────


@router.get("/health")
def health():
    client = get_client()
    return {
        "status": "ok",
        "monday_configured": client.configured(),
        "mode": "preview · read-only",
    }
