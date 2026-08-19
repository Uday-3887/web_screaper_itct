# Vercel Frontend

This folder is a static Vercel dashboard. Set Vercel Root Directory to `frontend`.

Before deploying, edit `config.js` and replace `YOUR-RAILWAY-SERVICE` with the generated Railway backend domain. The browser requires an HTTPS backend except during localhost development.

The frontend stores the short-lived login token in `sessionStorage`, attaches it as a bearer token to protected API calls and downloads result files through an authenticated CORS request.
