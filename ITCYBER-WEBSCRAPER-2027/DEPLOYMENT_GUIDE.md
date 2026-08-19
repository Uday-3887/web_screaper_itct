# ITCYBER v4.0.1 — Vercel + Railway Deployment Guide

This package contains a static frontend for Vercel and a Python/Playwright backend for Railway.
The Railway healthcheck/startup configuration has been hardened so the backend can start reliably.

## 1. Push the project to GitHub

Open the `ITCYBER_Vercel_Frontend_Railway_Backend` folder in VS Code.

```powershell
git init
git add .
git commit -m "Fix Railway healthcheck and Vercel backend connection"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/YOUR-REPOSITORY.git
git push -u origin main
```

If the repo is already connected, use only:

```powershell
git add .
git commit -m "Fix Railway healthcheck"
git push origin main
```

## 2. Railway backend — recommended setup

The easiest setup is to deploy from the repository root. This ZIP now contains a root `Dockerfile` that copies and runs only the backend.

1. Railway → open your backend service.
2. Settings → Source → connect the GitHub repository.
3. **Root Directory: leave blank / default `/`.**
4. **Build Command: blank.**
5. **Start Command: blank.** Do not enter a custom start command.
6. Railway should detect the root `Dockerfile`.
7. Healthcheck Path: `/health`
8. Healthcheck Timeout: `300`
9. Do not create a manual `PORT` variable. Railway supplies `PORT` automatically.

### Railway variables

Add these in Railway → Variables:

```text
ITCYBER_ALLOWED_ORIGINS=https://YOUR-VERCEL-PROJECT.vercel.app
ITCYBER_BOOTSTRAP_ADMIN_NAME=Admin
ITCYBER_BOOTSTRAP_ADMIN_EMAIL=YOUR-REAL-ADMIN-EMAIL
ITCYBER_BOOTSTRAP_ADMIN_PASSWORD=YOUR-STRONG-PRIVATE-PASSWORD
ITCYBER_DATA_DIR=/data/dashboard_data
ITCYBER_OUTPUT_DIR=/data/output
ITCYBER_BROWSER_PROFILE_DIR=/data/browser_profile
ITCYBER_HEADLESS=false
```

Use all three `ITCYBER_BOOTSTRAP_ADMIN_*` variables together. In this fixed version, a partially entered bootstrap set no longer crashes the server, but all three are still required to auto-create the admin account.

### Railway volume

For persistent jobs/admin data:

1. Railway → Volumes → Add Volume.
2. Attach it to the backend service.
3. Mount path: `/data`

The API can start without the volume, but data will not survive container replacement unless a persistent volume is mounted.

## 3. Verify the backend before connecting Vercel

After deployment, Railway logs should show something similar to:

```text
ITCYBER scraper API running at http://0.0.0.0:12345/
```

Generate a public Railway domain and open:

```text
https://YOUR-RAILWAY-DOMAIN.up.railway.app/health
```

Expected response:

```json
{"ok": true, "status": "healthy"}
```

Then open:

```text
https://YOUR-RAILWAY-DOMAIN.up.railway.app/api/health
```

The response should contain:

```json
"ok": true
```

Do not continue to Vercel login testing until these URLs work.

## 4. Alternative Railway setup using `/backend`

If you prefer to keep Railway Root Directory set to `/backend`, this fixed ZIP still supports it.

Use:

```text
Root Directory: /backend
Config File Path: /backend/railway.toml
Build Command: blank
Start Command: blank
Healthcheck Path: /health
```

The explicit Config File Path is important for current Railway monorepo behavior.

## 5. Connect frontend to Railway

Edit:

```text
frontend/config.js
```

Replace:

```javascript
apiBaseUrl: "https://YOUR-RAILWAY-SERVICE.up.railway.app"
```

with your real Railway domain, without a trailing slash:

```javascript
apiBaseUrl: "https://your-real-backend.up.railway.app"
```

Commit and push the change.

## 6. Vercel frontend

1. Vercel → Add New → Project.
2. Import the same GitHub repository.
3. Root Directory: `frontend`
4. Framework Preset: Other
5. Build command: none
6. Deploy.

After Vercel gives you the final production URL, update Railway:

```text
ITCYBER_ALLOWED_ORIGINS=https://YOUR-FINAL-VERCEL-DOMAIN.vercel.app
```

No trailing slash.

Redeploy Railway after changing the origin variable.

## 7. Login test

1. Confirm Railway `/health` returns 200.
2. Confirm Railway `/api/health` contains `"ok": true`.
3. Open the Vercel frontend.
4. Sign in with the Railway bootstrap email/password.
5. Open browser DevTools → Network if login fails.
6. The login request must go to:

```text
https://YOUR-RAILWAY-DOMAIN/api/auth/login
```

It must not go to localhost and must not contain the placeholder `YOUR-RAILWAY-SERVICE`.

## 8. Why the old Railway healthcheck could fail

The previous `backend/railway.toml` contained a custom start command using `$PORT` directly. On Dockerfile/image deployments, a Railway Start Command override does not perform shell variable expansion unless it is explicitly wrapped in a shell. That can result in the backend never binding to Railway's injected port.

The fixed project removes that risky override. The Dockerfile itself starts the app through `sh -c`, so `${PORT:-8080}` is expanded correctly.

The fixed backend also provides a minimal `/health` endpoint that returns HTTP 200 as soon as the API server is alive.

## 9. If Railway still says Healthcheck failure

Check Deployment Logs first. You must see the `ITCYBER scraper API running` startup line.

If that line is missing, the process crashed before the web server started. Look for the first Python/Docker error above the healthcheck message.

If the startup line is present but the healthcheck still fails, verify:

```text
Healthcheck Path = /health
Start Command = blank
PORT variable = not manually created
```

Then redeploy.
