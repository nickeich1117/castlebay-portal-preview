"""Centralized config — all env vars in one place."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent

# Monday
MONDAY_API_URL = "https://api.monday.com/v2"
MONDAY_API_VERSION = "2025-04"
MONDAY_API_KEY = os.getenv("MONDAY_API_KEY", "")
MONDAY_TIMEOUT_S = 30

# Auth / sessions
SESSION_SECRET = os.getenv("PREVIEW_SESSION_SECRET", "dev-only-not-for-prod")
SESSION_TTL_HOURS = int(os.getenv("PREVIEW_SESSION_TTL_HOURS", "24"))
SECURE_COOKIES = os.getenv("PREVIEW_SECURE_COOKIES", "false").lower() == "true"

# DB
DB_PATH = os.getenv("PREVIEW_DB_PATH", str(PROJECT_ROOT / "preview.db"))

# Cache
CACHE_TTL_S = int(os.getenv("PREVIEW_CACHE_TTL_SECONDS", "300"))

# Real Monday board IDs — pulled from board_columns.json on prod side
# These are the 7 active 2026 staffing boards.
ACTIVE_BOARDS = [
    {"id": "18404287515", "name": "2026 — Texas Farm Bureau Staffing"},
    {"id": "18407385797", "name": "2026 — JRIC"},
    {"id": "18404254687", "name": "2026 — Mutual of Enumclaw"},
    {"id": "18404282645", "name": "2026 — NTT Data"},
    {"id": "18406763020", "name": "2026 — FMI"},
    {"id": "18398705698", "name": "2026 — FrankCrum"},
    {"id": "18393952917", "name": "2026 — TDIC Staffing"},
]

# Pipeline buckets — copied verbatim from staffing_primitives.STATUS_DISPLAY_BUCKETS
DISPLAY_BUCKETS = ["Submitted", "In Review", "Interview", "Placed", "Declined", "On Hold"]

# Banner shown on every page so reviewers know it's not real
PREVIEW_BANNER_TEXT = "Preview · read-only · all writes disabled · data live from Monday"
