# Dollax Panel — Setup Guide

Dollax is a small self-hosted admin panel for running a **VLESS-over-WebSocket-over-TLS**
proxy inbound. It's built with FastAPI + SQLite, and gives you a web UI to create
inbounds (entry points) and clients (users), each with a ready-to-copy `vless://` link.

## What was fixed in this package

The uploaded project referenced `/static/style.css` and `/static/app.js` from `pages.py`,
but no `static/` folder was included. FastAPI's `StaticFiles` mount also checks that the
directory exists **at import time**, so as shipped the app would have crashed immediately
on boot, before even reaching the health check. This package adds:

- `static/style.css` and `static/app.js` — a working single-page dashboard (overview,
  inbounds, clients, settings), talking to the JSON API that was already in `main.py`.
- `requirements.txt` — added `python-multipart`, which Starlette needs to parse the
  login form (`request.form()`); without it, the login POST throws a 500.
- `Dockerfile` — creates `static/` and `data/` defensively so a missing folder can't
  crash the container image build or boot.
- `main.py` — a startup warning in the logs if `SECRET_KEY` or `ADMIN_PASSWORD` are left
  unset/default, and a small cleanup (`json` imported properly instead of `__import__('json')`
  inline).

Everything else — the route logic, the VLESS/WebSocket relay in `protocol.py`, the
SQLite schema in `db.py` — was left as designed.

## 1. What's in this folder

```
main.py            FastAPI app, routes, WebSocket relay entrypoint
db.py               SQLite schema, migrations, password hashing
pages.py            Server-rendered HTML shells (login page, dashboard shell)
protocol.py         VLESS header parsing + link building + TCP<->WS relay
static/style.css    Dashboard styling
static/app.js       Dashboard SPA (overview / inbounds / clients / settings)
requirements.txt    Python dependencies
Dockerfile          Container build
railway.json        Railway deploy config (healthcheck, restart policy)
_env.example        Example environment variables
```

## 2. Environment variables

Set these in Railway → your service → **Variables** (or in a local `.env` for testing):

| Variable | Required | Purpose |
|---|---|---|
| `ADMIN_USERNAME` | no (default `dollax26`) | Created once, on first boot, if the `admins` table is empty. |
| `ADMIN_PASSWORD` | no (default `admin`) | Password for that first admin account. **Change this before your first deploy** — the app logs a warning if you don't. |
| `SECRET_KEY` | **yes, in production** | Signs the session cookie. If unset, a random key is generated on every process start, which silently logs everyone out on every restart or redeploy. Generate one with: `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `PUBLIC_BASE_URL` | recommended | The full public URL of your deployment, e.g. `https://dollax-production.up.railway.app`. Used to build correct `vless://` links and as the default WebSocket Host/SNI. Also editable later from the Settings page. |
| `DATA_DIR` | no (default `./data`) | Where the SQLite file lives when `RAILWAY_VOLUME_MOUNT_PATH` isn't set. |
| `RAILWAY_VOLUME_MOUNT_PATH` | set automatically by Railway once you attach a Volume | Takes priority over `DATA_DIR`. See §4 — **you must attach a Volume, or your admin account and every client you create are wiped on the next redeploy.** |

## 3. Running locally (optional, for testing before you deploy)

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
export ADMIN_USERNAME=admin
export ADMIN_PASSWORD=change-me-now
export SECRET_KEY=$(python3 -c "import secrets;print(secrets.token_urlsafe(48))")
uvicorn main:app --reload --port 8000
```

Open `http://localhost:8000`, log in with the username/password above.

## 4. Deploying on Railway

1. **Push this folder to a GitHub repo** (or use Railway's CLI to deploy from disk).
2. In Railway, **New Project → Deploy from GitHub repo**, pick the repo. Railway will
   detect the `Dockerfile` and build from it — no Nixpacks setup needed.
3. **Attach a Volume** (Railway service → Settings → Volumes → **New Volume**), mount
   path `/data`. This is not optional: SQLite lives on disk, and without a Volume every
   redeploy starts from an empty database — you'd lose the admin account and all clients.
4. Under **Variables**, set at minimum `ADMIN_PASSWORD` and `SECRET_KEY` from the table
   above. Leave `RAILWAY_VOLUME_MOUNT_PATH` alone — Railway sets it for you once the
   Volume is attached at `/data`.
5. Under **Settings → Networking**, click **Generate Domain** (or attach a custom domain).
   Railway terminates TLS for you at the edge, which is what makes this a valid
   VLESS+WS+**TLS** inbound — the app itself only speaks plain HTTP/WS on `$PORT`.
6. Deploy. Railway will hit `GET /health` (already wired in `railway.json`) to confirm
   the container is up.
7. Once it's live, open the app's domain, log in, and go to **Settings** — set
   **Public base URL** to your Railway domain (or custom domain) if you didn't set
   `PUBLIC_BASE_URL` as an env var. This is what gets embedded in every client's
   `vless://` link.
8. Create an **Inbound** (Inbounds tab). Leave protocol/network/security as VLESS/WS/TLS
   — that's the only combination this build supports (see §6). Note the WebSocket path
   it generates (or set your own).
9. Create a **Client** under that inbound. Copy the generated `vless://` link into any
   VLESS-compatible client app (v2rayN, v2rayNG, NekoBox, Streisand, etc.).

## 5. Security checklist before you expose this publicly

- [ ] Changed `ADMIN_PASSWORD` from the default.
- [ ] Set a fixed `SECRET_KEY` (not left to the random per-process fallback).
- [ ] Attached a Railway Volume, so your data survives redeploys.
- [ ] Set `PUBLIC_BASE_URL` to your real domain.
- [ ] Understand there's no login rate-limiting or 2FA built in — a strong, unique
      admin password is your main defense on the login page. If you want more, put
      Railway behind Cloudflare and add rate limiting / WAF rules there.
- [ ] There's currently no UI for managing multiple admin accounts — only the one
      created from `ADMIN_USERNAME`/`ADMIN_PASSWORD` on first boot. To rotate the
      password later, you'd currently need to edit the `admins` table directly
      (e.g. via a one-off script using `db.hash_password()`), since there's no
      "change password" endpoint yet.

## 6. Known limitations (by design in this build)

- **Only VLESS + WebSocket + TLS** is supported — `create_inbound` rejects anything
  else. This matches Railway's networking model, which only exposes HTTP(S)/WS, not
  raw TCP.
- **No UDP support.** `protocol.py` accepts VLESS command byte `2` (UDP) in the header
  parser but the relay loop treats it identically to TCP — real UDP-over-VLESS framing
  isn't implemented, so don't rely on it for anything UDP-based (e.g. QUIC/HTTP3, some
  games).
- **No per-client traffic accounting.** `limit_bytes` fields exist in the schema and UI,
  but nothing currently measures usage or enforces the limit at relay time — it's
  recorded but not yet acted on.
- **No brute-force protection on `/login`.**

## 7. Troubleshooting

- **"Invalid credentials" and you're sure the password is right** → you likely set
  `ADMIN_PASSWORD` *after* first boot. The admin row is only created once, when the
  `admins` table is empty. Attach a Volume, then either wipe `dollax.db` from it and
  redeploy, or update the row directly.
- **Logged out after every deploy** → `SECRET_KEY` isn't set; see §2.
- **Clients can't connect / links look wrong** → check `PUBLIC_BASE_URL` in Settings,
  and confirm the inbound's Host header/SNI match your actual domain.
- **App won't boot, Railway shows a crash loop** → check the deploy logs; the most
  common causes before this fix were the missing `static/` folder and the missing
  `python-multipart` dependency, both addressed here.
