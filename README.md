# WhatsApp Bot (WhatsApp Cloud API) – Phase 1 Menu Bot

Menu-driven WhatsApp webhook for Yala (event code → name → menu: brochure / donate / condolence).

## Setup

1. Create and activate a Python virtual environment.
2. Install dependencies:
   
   pip install -r requirements.txt

3. Copy .env.example to .env and set values.

## Run

python -m src.app

## Docker (bot + Redis)

1. Copy `.env.example` to `.env` and fill in the required values.
2. Start services:
   - `docker compose up --build`

This runs:
- the bot on `http://localhost:5000`
- Redis on `localhost:6379`

## Deploy to Render (Web Service + Redis)

This repo includes a Render Blueprint at `render.yaml` that creates:
- a Docker-based Web Service (the Flask/Gunicorn app)
- a managed Redis instance (for shared sessions + cross-worker de-dupe)

### Steps

1. Push this repo to GitHub.
2. In Render, choose **New → Blueprint** and select your repo.
3. Render will read `render.yaml` and provision the services.
4. In the Web Service settings, set these required environment variables:
   - `PUBLIC_BASE_URL` = your Render service URL (e.g. `https://<service>.onrender.com`)
   - `META_WA_ACCESS_TOKEN`
   - `META_WA_PHONE_NUMBER_ID`
   - `META_WEBHOOK_VERIFY_TOKEN`
   - `META_APP_SECRET`
   - `BACKEND_BASE_URL` (if you’re using the backend integration)
   - `BACKEND_AUTH_BEARER_TOKEN` (only if your backend requires it)

### Meta webhook configuration

In the Meta developer dashboard (WhatsApp Cloud API):
- Callback URL: `https://<service>.onrender.com/webhook/meta`
- Verify token: set to the same value as `META_WEBHOOK_VERIFY_TOKEN`

Use `https://<service>.onrender.com/health` to confirm the service is up.

## Production notes (concurrency)

For multiple concurrent users, run behind a production WSGI server (not Flask's dev server).

- Example (2 workers, 8 threads each):
   - `gunicorn -w 2 --threads 8 -b 0.0.0.0:5000 src.app:app`

Background Meta webhook processing is handled by a bounded worker pool to keep webhook responses fast.
You can tune it with:

- `WEBHOOK_WORKER_THREADS` (default `16`)
- `WEBHOOK_MAX_INFLIGHT` (default `WEBHOOK_WORKER_THREADS * 8`)

### Redis (recommended for multiple workers/instances)

If you run more than one worker/process, in-memory sessions will not be shared and users may lose conversation state.
Enable Redis to share sessions across workers and to de-dupe Meta webhook retries across workers:

- `REDIS_URL` (e.g. `redis://localhost:6379/0`)
- `REDIS_KEY_PREFIX` (default `wa_bot`)
- `REDIS_REQUIRED=1` to fail fast if Redis is not reachable

## Meta WhatsApp Cloud API (Webhook)

This repo also supports receiving messages via Meta WhatsApp Cloud API.

- Verification endpoint: `GET /webhook/meta`
- Message webhook endpoint: `POST /webhook/meta`

Environment variables (see `.env.example`):
- `META_WA_ACCESS_TOKEN`
- `META_WA_PHONE_NUMBER_ID`
- `META_WEBHOOK_VERIFY_TOKEN`
- `META_APP_SECRET`

Local dev with ngrok:
1. Run the server.
2. Run `ngrok http 5000`.
3. In Meta dashboard, set Callback URL to `https://<ngrok-host>/webhook/meta` and Verify Token to match `META_WEBHOOK_VERIFY_TOKEN`.

## Troubleshooting (Cloud API)

If you send "Hi" and get no reply:

1. Confirm Meta is delivering webhooks (Meta dashboard should show deliveries to your callback URL).
2. Confirm your WABA is subscribed to your Meta app:
   - `python scripts/meta_subscribe_check.py`
   - If needed: `python scripts/meta_subscribe_check.py --subscribe`

Optional local debug endpoints (disabled by default):
- Set `DEBUG_ENDPOINTS=1` and `DEBUG_TOKEN=<random>`
- View last webhook receipts: `GET /debug/meta/last?token=<DEBUG_TOKEN>`
- Send a test outbound message: `POST /debug/meta/send?token=<DEBUG_TOKEN>` with JSON `{ "to": "<wa_id>", "body": "hello" }`

## Environment Variables

- PUBLIC_BASE_URL (required to send the brochure as media)
- SESSION_TTL_SECONDS (optional, default 1500)
- BACKEND_BASE_URL (Yala API base url, e.g. https://api.example.com/)
- BACKEND_TIMEOUT_SECONDS (optional, default 15)
- BACKEND_AUTH_BEARER_TOKEN (optional, if backend requires auth)
