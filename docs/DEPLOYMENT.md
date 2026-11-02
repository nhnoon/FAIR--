# Deployment (frontend and backend deployed separately)

Nothing has been deployed yet. These steps work on any host that can run a Python web process
(backend) and serve static files (frontend).

## 1. Backend (FastAPI)

| Setting | Value |
|---|---|
| Root directory | `backend` |
| Python | 3.11 (`backend/.python-version`) |
| Build command | `pip install -r requirements.txt` |
| Start command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips="*" --no-server-header` (also in `backend/Procfile`) |
| Health check path | `/api/health` (needs no API key, not rate limited) |

Environment variables (set in the host's dashboard, **never** in the repo):

| Variable | Production value |
|---|---|
| `MODEL_API_KEY` | your Meta Model API key (secret) |
| `MODEL_LIVE_CALLS_ENABLED` | `true` once live calls are approved |
| `MODEL_NAME` | `muse-spark-1.3` |
| `MODEL_MAX_OUTPUT_TOKENS` | `8000` (per-request ceiling, including reasoning tokens) |
| `MODEL_BASE_URL` | `https://api.meta.ai/v1` |
| `CORS_ORIGINS` | exact frontend origin(s), e.g. `https://fair.example.app` (no trailing slash) |
| `RATE_LIMIT_PER_MINUTE` | `10` (per client IP) |
| `DAILY_ANALYSIS_LIMIT` | e.g. `300`, to cap credit spend per day |
| `API_DOCS_ENABLED` | `false` |

Notes
- `--forwarded-allow-ips="*"` trusts `X-Forwarded-For`. That is only safe when the host's proxy is
  the sole way in (true on typical managed platforms). Otherwise, set it to the proxy's IP.
- Rate limits are in memory and per process. Run **one** instance/worker for the demo.
- Logs contain metadata only (verdict, latency, token counts, error code), never user text or the key.
- **Public cost risk:** with live calls on, every visitor's analysis is a billable request. Output is capped at 8,000 tokens per request, and input has no provider-enforced ceiling. Set `DAILY_ANALYSIS_LIMIT` deliberately, and note that it resets when the process restarts.

## 2. Frontend (static site)

| Setting | Value |
|---|---|
| Root directory | `frontend` |
| Build command | `npm ci && npm run build` |
| Publish directory | `frontend/dist` |
| Node | 20 or newer |
| Build env var | `VITE_API_BASE_URL=https://<your-backend-host>` (public, embedded at build time) |

`VITE_API_BASE_URL` must be an absolute `http(s)` origin with no credentials or query string. Otherwise
the app throws at request time. Rebuild the frontend whenever this value changes.

## 3. Connect and verify

1. Deploy the backend and note its URL. Check `GET https://<backend>/api/health` returns 200.
2. Deploy the frontend with `VITE_API_BASE_URL` set to that URL. Note the frontend URL.
3. Set `CORS_ORIGINS` on the backend to the frontend URL and restart it.
4. Open the frontend and run one analysis.
   - Without a key or live flag, the page shows "Live analysis isn't set up yet". The UI ↔ API
     connection is working.
   - If the page shows "Can't reach the FAIR server", the cause is the CORS origin or the URL.
5. Only after approval: set `MODEL_API_KEY` and `MODEL_LIVE_CALLS_ENABLED=true`, then run **one**
   analysis and confirm a card labeled **Live analysis · Model: muse-spark-1.3**.

## Verified locally (production build, separate origins)
- The frontend built with `VITE_API_BASE_URL=http://127.0.0.1:8000` and was served by `vite preview`
  on :4173 / :4174. The backend ran with `CORS_ORIGINS=http://127.0.0.1:4173`.
- From the allowed origin, the browser sent OPTIONS then POST, and the page showed the 503
  `model_not_configured` message. No `Authorization` header was sent.
- From the non-allowed origin, the request was blocked by CORS and the page showed "Can't reach the FAIR server".
- With `API_DOCS_ENABLED=false`, `/docs` returns 404. With `--no-server-header`, no `server` header is sent.
