# Deploying DataFix

**Setup:** the UI (React/Vite) runs on **Vercel**. The API (FastAPI) runs on a container host: **Render** in this guide, though the same `Dockerfile` works on Railway, Fly.io or any VPS. The browser calls the API directly at `VITE_API_URL`, and the API allows the Vercel origin through CORS.

## Why the API is not on Vercel too

Vercel runs Python as short-lived serverless functions, and the DataFix API needs to be one long-running process:

| DataFix needs | Vercel functions give |
|---|---|
| A session that stays in memory across many requests (scan → plan → review → export) and is saved to disk by a background thread | Each request may hit a different instance; the disk is temporary; background work stops after the response |
| Uploads of several MB (the 30k-row test files are 6 and 9 MB) | A request body limit of about 4.5 MB |
| Scans of 6 s (demo) to about 70 s (30k rows) | Time-limited invocations |

Moving the sessions to external storage would mean rewriting the engine's state handling. A container host runs the API unchanged.

## 0. Before you start

- The code must be on GitHub, since both Vercel and Render deploy from the repo: `git push origin main`.
- Keys stay out of git. They are entered in the Render dashboard, never in a file.
- Production settings, all already in `Dockerfile` / `render.yaml`:

| Variable | Production value | Purpose |
|---|---|---|
| `DATAFIX_PUBLIC` | `1` | Hides `GET /api/sessions`, `/api/debug/inflight` and the API docs, so a session can only be opened by someone who has its link |
| `DATAFIX_SESSION_TTL_H` | `24` | Deletes uploads that have been idle for 24 h (from memory and disk) |
| `DATAFIX_MAX_UPLOAD_MB` | `50` | Upload limit per file |
| `DATAFIX_SESSION_DIR` | `/tmp/datafix-sessions` | Session files. They are lost when the server restarts or redeploys, which is fine for a demo |
| `DATAFIX_CORS_ORIGINS` | your Vercel URL | Lets the UI call the API |
| `GEMINI_API_KEY`, `GEMINI_API_KEY_BACKUP`, `GROQ_API_KEY` | from `.env` | Optional. With no key the app uses offline templates |

## 1. API on Render

1. Sign in at render.com, then go to **New + → Blueprint** and connect the GitHub repo. Render reads `render.yaml` and proposes the `datafix-api` web service (Docker).
   - Manual alternative: **New + → Web Service** → this repo → Language **Docker**, Dockerfile path `./Dockerfile`, health check path `/api/health`.
2. When asked for the secret values, paste `GEMINI_API_KEY`, `GEMINI_API_KEY_BACKUP` and `GROQ_API_KEY` from your local `.env`. Leave `DATAFIX_CORS_ORIGINS` empty for now; it's filled in at step 3.
3. Click **Apply** / **Create**. The first build takes about 5 minutes (Node stage for the UI, then Python packages).
4. Check `https://<your-api>.onrender.com/api/health`. It should return `{"status":"ok", ..., "public": true}`.
   - The same URL also serves the full UI, so it already works as a single-host deployment.

**Demo dataset:** the image ships only the 1,000-row app demo (`data/demo_small`), which runs the whole flow in seconds even on the free plan. Set `DATAFIX_DEMO_DIR=data/demo` only if you also copy the full demo into the image.

**Auto-deploy:** `render.yaml` sets `autoDeploy: true`, so every push to `main` rebuilds and redeploys. If you created the service by hand rather than from the Blueprint, check **Settings → Build & Deploy → Auto-Deploy = On Commit**.

**Plan size:** measured peak memory is about 225 MB for the demo (fits the free 512 MB plan) and about 555 MB for a 30k-row file plus 81k linked orders. For files that size, pick a plan with at least 1 GB of RAM.

**Free plan:** the service sleeps after about 15 minutes without traffic, and the first request after that takes about a minute. Before a demo, open `/api/health` and wait for `ok`.

## 2. UI on Vercel

1. Go to vercel.com → **Add New… → Project** and import the same GitHub repo.
2. **Root Directory:** `frontend`. The framework (Vite), build command (`npm run build`) and output (`dist`) come from `frontend/vercel.json`.
3. **Environment Variables:** `VITE_API_URL` = `https://<your-api>.onrender.com`.
   - Enter the origin only: no trailing `/` and no `/api`.
   - Vite bakes this value into the build, so it must be set **before** deploying.
4. **Deploy.** You get `https://<project>.vercel.app`.

CLI alternative:
```bash
npm i -g vercel
cd frontend
vercel link                          # create or link the project (root = frontend)
vercel env add VITE_API_URL production   # paste https://<your-api>.onrender.com
vercel --prod
```

## 3. Connect the two

1. Render → `datafix-api` → **Environment** → `DATAFIX_CORS_ORIGINS` = `https://<project>.vercel.app` (exact, no trailing slash). Save, and Render redeploys.
   - Optional, for Vercel preview URLs: `DATAFIX_CORS_ORIGIN_REGEX` = `https://<project>-.*\.vercel\.app`.
2. Open the Vercel URL → **Load demo dataset** → Scan → Plan repairs → Apply → Export → **Download all (ZIP)**.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| "Cannot reach the DataFix server…" | The API is asleep (free plan): wait about a minute and retry, or check `/api/health` |
| Browser console shows a CORS error | `DATAFIX_CORS_ORIGINS` doesn't exactly match the Vercel URL (check `https`, no trailing `/`) |
| UI calls `https://<project>.vercel.app/api/...` and gets 404 | `VITE_API_URL` was missing at build time: set it, then **Redeploy** on Vercel |
| Refreshing `/s/<id>/repair` gives a Vercel 404 | Root Directory isn't `frontend`, so `vercel.json` (SPA rewrite) wasn't used |
| "Session not found" after a while | The API restarted or redeployed (sessions live on its temporary disk), or the 24 h expiry passed: upload again |
| A large file fails or the service restarts | Out of memory: use a bigger plan, or lower `DATAFIX_MAX_UPLOAD_MB` |

## Verified locally (2026-11-20)

- No-dev install from `uv.lock` (`uv sync --frozen --no-dev`) in a clean environment: imports OK, 180 MB (`scikit-learn` removed; it was never used).
- API in public mode on its own port, UI built with `VITE_API_URL` and served from another origin:
  - The full rehearsal passes 11/11, including the ZIP export across origins, with no requests to any outside host.
  - The session list, debug endpoint and API docs return 404.
  - An unknown origin gets no CORS headers.
- 83 tests pass, including `tests/test_deploy.py` (public mode, session expiry, upload limit).
- Not verified here: `docker build` (Docker isn't installed on this machine), so Render's first build is the first real run of the Dockerfile.
