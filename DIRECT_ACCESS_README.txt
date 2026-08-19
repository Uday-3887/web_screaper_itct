ITCYBER v4.0.3 - NO LOGIN BUILD

LOGIN PAGE: REMOVED
LOGIN ID/PASSWORD: NOT REQUIRED
BACKEND AUTHORIZATION: DISABLED
DASHBOARD: OPENS DIRECTLY

LOCAL RUN

Terminal 1:
cd backend
.\.venv\Scripts\Activate.ps1
python dashboard_server.py --no-open

Terminal 2:
cd frontend
python -m http.server 5500

For local use set frontend/config.js to:
http://localhost:8766

Open:
http://localhost:5500

SECURITY NOTE:
When deployed publicly, anyone who can reach the frontend/backend can use this dashboard because login protection is intentionally disabled.
