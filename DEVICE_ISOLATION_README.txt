ITCYBER Web Scraper - Device Session Isolation v4.1.0

What changed
------------
1. Every browser/device receives a persistent unique device id in localStorage.
2. Frontend sends that id to Railway using the X-Client-ID request header.
3. Backend stores the device id with each scraping job.
4. Job history, job details, result preview, downloads and stop controls are filtered/enforced by device id.
5. A different device cannot view or control another device's jobs/results, even if it knows a job id.
6. Existing legacy jobs that do not have a device id are intentionally hidden.
7. Responsive styles.css from the latest mobile-responsive build is included.

Deployment IMPORTANT
--------------------
Both sides changed, so redeploy BOTH:
- Railway backend: repository root (Dockerfile at root)
- Vercel frontend: Root Directory = frontend

The backend CORS configuration now allows the X-Client-ID header.
Keep ITCYBER_ALLOWED_ORIGINS set to your Vercel production domain or https://*.vercel.app.

Behavior note
-------------
The device id persists per browser profile. Clearing site storage or using an incognito/private window creates a new device identity and therefore a separate empty job history.
