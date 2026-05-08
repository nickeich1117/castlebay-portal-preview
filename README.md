# CastleBay Portal Preview

A **read-only fork** of the CastleBay vendor portal, built to ship the v2 design mocks as a live, reviewable site without touching production data.

- **Live data:** read-only queries to Monday.com (boards, roles, candidates).
- **Zero writes:** every layer of the app refuses to send a mutation. See [`READ_ONLY_GUARANTEES.md`](./READ_ONLY_GUARANTEES.md).
- **Independent:** own database, own Render service, own GitHub repo. Tearing it down doesn't touch the prod portal.

## What's here

```
portal-preview/
├── app/
│   ├── main.py            FastAPI entrypoint
│   ├── routes.py          /boards, /drilldown, /kanban, /vendor, /interviewer, /feedback, /login
│   ├── auth.py            bcrypt + sessions
│   ├── db.py              SQLite (users + sessions only)
│   ├── monday_read.py     read-only Monday client with mutation-ban
│   ├── config.py          env vars + active-board list
│   ├── templates/         Jinja2 (8 mocks)
│   └── static/            CSS, logo, favicon
├── scripts/seed_users.py  Idempotent user seeder
├── tests/                 pytest — mutation guard + smoke tests
├── render.yaml            Render service config (free tier)
├── requirements.txt
├── DEPLOYMENT.md          Step-by-step deploy guide
└── READ_ONLY_GUARANTEES.md  How writes are prevented
```

## Quickstart

```bash
pip install -r requirements.txt
export MONDAY_API_KEY="your-key"
python scripts/seed_users.py    # creates Nick/David/Don users (passwords printed once)
uvicorn app.main:app --reload
# http://localhost:8000
```

## Routes

| Route | Mock | Data source |
|-------|------|-------------|
| `/boards` | E | Live Monday |
| `/drilldown` | A | Live Monday |
| `/kanban` | B | Static demo |
| `/vendor` | C | Static demo |
| `/feedback` | G | Static demo |
| `/feedback/{id}` | F | Static demo |
| `/interviewer` | D | Static demo |
| `/login` | — | Local DB |
| `/health` | — | — |

The internal-facing routes (E, A) pull live data because the Monday API supports it without per-vendor scoping. The vendor-side routes (C, F, G) and the interviewer route (D) render with static demo data — when real vendor accounts exist on prod they can move to live data trivially.

## Read-only contract

See [`READ_ONLY_GUARANTEES.md`](./READ_ONLY_GUARANTEES.md). Three layers:

1. **Code** — `MondayReadClient.query()` rejects any string containing `mutation`.
2. **CI tests** — repo-wide grep for mutation strings; module surface check.
3. **Logging** — every Monday call logged with operation signature; blocked mutations logged at ERROR.

## Deploy

See [`DEPLOYMENT.md`](./DEPLOYMENT.md).

## Tearing down

`render dashboard → service → delete`, then `github → repo → delete`. Prod portal unaffected.
