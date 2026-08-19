# Railway Backend

This folder is the cloud API and Playwright worker. Deploy it with Railway Root Directory set to `backend`.

Required production configuration:

- Variables from `.env.example`
- Persistent volume mounted at `/data`
- At least 2 GB RAM; 4 GB recommended
- Generated public Railway domain

The API listens on Railway's `PORT`, exposes `/api/health`, accepts bearer sessions from the Vercel dashboard, starts one scraper subprocess at a time, checkpoints every record and protects all job/download routes with administrator authentication.

Run tests:

```bash
python -m unittest -v test_dashboard.py test_utils.py
```
