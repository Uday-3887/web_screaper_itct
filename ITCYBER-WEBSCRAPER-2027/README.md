# Direct-access build

This version permanently removes the login page and disables backend authentication checks.

# ITCYBER Connected Business Scraper — Vercel + Railway

Production-style split deployment of the ITCYBER Google Business and public social-profile scraper.

## Architecture

| Folder | Deploy to | Responsibility |
| --- | --- | --- |
| `frontend/` | Vercel | Responsive admin dashboard |
| `backend/` | Railway | Python API, Playwright Chromium worker, login, jobs and exports |

The frontend authenticates using a short-lived bearer session kept in browser `sessionStorage`. The Railway API accepts requests only from configured Vercel origins. Admin data, job history, browser state and exported files live under `/data` on a Railway persistent volume.

## Start here

Follow [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) exactly. Deploy the Railway backend first, paste its generated URL into `frontend/config.js`, then deploy the frontend to Vercel.

## Included deployment features

- Dockerized Playwright/Chromium backend
- Railway health check and restart policy
- Railway persistent-volume paths
- Vercel security headers and static configuration
- Cross-origin authorization without third-party cookies
- First-deploy administrator bootstrap through Railway secrets
- Protected job history, previews, stop controls and file downloads
- Result target from 1 to 2,000
- Google-only, website-enriched and full-public-social modes
- CSV, JSON and Excel output
- Automated Python, JavaScript and API integration checks

## Important limits

- `2,000` is a target, not a guarantee that Google Maps will expose 2,000 unique public listings.
- Cloud browser traffic may encounter CAPTCHA or unusual-traffic pages. This project does not bypass them.
- Manual social login is intended for local use and is not exposed by the cloud dashboard.
- Use Railway paid compute with at least 2 GB RAM; 4 GB is recommended for longer jobs.
- Run only one scraping job at a time.

## Verification

From the project root:

```bash
python verify_project.py
```

Backend unit tests can also be run directly:

```bash
cd backend
python -m unittest -v test_dashboard.py test_utils.py
```

## Railway v4.0.1 healthcheck fix

For the simplest Railway deployment, leave the Railway Root Directory blank. The repository now includes a root `Dockerfile` and `railway.toml` that run the backend and use `/health` for deployment healthchecks. Keep Railway Build Command and Start Command blank. See `RAILWAY_HEALTHCHECK_FIX.txt` and `DEPLOYMENT_GUIDE.md`.

