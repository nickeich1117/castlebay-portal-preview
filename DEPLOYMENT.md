# Deployment Guide

Step-by-step to ship the preview to Render.

## Pre-flight

- [ ] You have the prod Monday API key handy (same one prod uses; cutover to read-only token is a backlog item).
- [ ] You have a Render account with payment method on file (free tier still requires one to spin up Postgres-free services).
- [ ] You have GitHub access to `nickeich1117`.

## 1 — Local sanity check

```bash
cd ~/Claude\ AI\ Work/castlebay/portal-preview
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Initialize the local DB and seed users
python scripts/seed_users.py
# Save the printed passwords to 1Password.

# Set Monday key for local
export MONDAY_API_KEY="<paste prod key>"

# Boot
uvicorn app.main:app --reload
# Visit http://localhost:8000 → /login → sign in with one of the seeded accounts
```

## 2 — Run the read-only guard tests

```bash
pytest tests/test_no_mutations.py -v
# All 6 must pass. If any fail, fix code before pushing.

pytest tests/test_smoke.py -v
# 8+ should pass. The "authed_routes" cases hit Monday — they pass even with key
# unset because the routes degrade to "—" rather than crash.
```

## 3 — Push to GitHub

```bash
cd ~/Claude\ AI\ Work/castlebay/portal-preview

# Clean up any partial .git from the build session
rm -rf .git

git init
git add .
git commit -m "Initial portal-preview build — read-only Monday fork"

# Create the empty repo via the GitHub web UI:
#   https://github.com/new
#   name: castlebay-portal-preview
#   private: yes
#   no readme/license/gitignore (we have our own)

git branch -M main
git remote add origin https://github.com/nickeich1117/castlebay-portal-preview.git
git push -u origin main
```

## 4 — Create the Render service

1. Render dashboard → **New +** → **Blueprint**.
2. Connect the `nickeich1117/castlebay-portal-preview` repo.
3. Render auto-detects `render.yaml`. Click **Apply**.
4. On the env-var screen, paste:
   - `MONDAY_API_KEY` = `<your prod key>` (read-only token replacement comes later)
   - All others auto-generate / use defaults from `render.yaml`.
5. **Create**. First build takes ~3 min.

## 5 — Seed users on the live instance

Render gives the disk a `/data` mount but doesn't auto-run scripts. Two options:

**Option A — Render Shell (recommended):**

1. Once deployed, open the service in Render → **Shell** tab.
2. Run:
   ```
   PREVIEW_NICK_PW="<choose a password>" \
   PREVIEW_DAVID_PW="<choose>" \
   PREVIEW_DON_PW="<choose>" \
     python scripts/seed_users.py
   ```
3. Save the passwords; share David's and Don's via 1Password.

**Option B — Add to startCommand temporarily:**

Edit `render.yaml`:
```yaml
startCommand: python scripts/seed_users.py && uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Push, wait for redeploy, copy the printed passwords from the build logs, then **revert** that change so seed_users doesn't run on every restart (it's idempotent, but it's noise).

## 6 — Verify

```bash
PREVIEW=https://castlebay-portal-preview.onrender.com

curl $PREVIEW/health
# Expect 200 with status: ok, monday_configured: true

# Browser:
open $PREVIEW
# Should redirect to /login
# Sign in with your account → land on /boards
# Click any board → /drilldown → see real Monday role groups
```

## 7 — Lock down before sharing externally

Before David, Don, or any vendor hits the URL:

- [ ] Cut a read-only Monday token in Monday admin (Settings → Developers → New token, scope: Read only).
- [ ] Swap `MONDAY_API_KEY` in the Render dashboard → **Manual Deploy** to pick it up.
- [ ] Confirm `/health` still returns `monday_configured: true`.
- [ ] Tail logs for 5 minutes and confirm zero `Mutation blocked` lines.

## 8 — Iterating

Each `git push origin main` triggers an auto-deploy. To roll back:

```bash
# Render dashboard → service → "Events" → pick a past deploy → "Redeploy"
```

Or via CLI:

```bash
git revert <bad-commit-sha>
git push
```

## Tearing it down

If the preview's job is done:

1. Render dashboard → service → **Delete service**.
2. GitHub → repo → **Settings** → **Delete this repository**.
3. The prod portal is unaffected; nothing was shared.
