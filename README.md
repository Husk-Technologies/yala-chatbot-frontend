# WhatsApp Bot (WhatsApp Cloud API) – Phase 1 Menu Bot

Menu-driven WhatsApp webhook for Yala (event code → name → menu: brochure / donate / condolence).

## Setup

1. Create and activate a Python virtual environment.
2. Install dependencies:
   
   pip install -r requirements.txt

3. Copy .env.example to .env and set values.

## Run

python -m src.app

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

## Legacy: Twilio WhatsApp

This repo previously supported Twilio WhatsApp webhooks via TwiML at `POST /webhook`.

To enable it:
- Set `CHANNEL=twilio` or `ENABLE_TWILIO_WEBHOOK=1`
- Configure Twilio to send webhooks to `https://<your-host>/webhook`

## Environment Variables

- PUBLIC_BASE_URL (required to send the brochure as media)
- SESSION_TTL_SECONDS (optional, default 1500)
- BACKEND_BASE_URL (Yala API base url, e.g. https://api.example.com/)
- BACKEND_TIMEOUT_SECONDS (optional, default 15)
- BACKEND_AUTH_BEARER_TOKEN (optional, if backend requires auth)
- TWILIO_AUTH_TOKEN (only required if VERIFY_TWILIO_SIGNATURES=1)
- VERIFY_TWILIO_SIGNATURES (default: 0)

## Optional: Interactive Menu (Buttons)

This project can send an interactive WhatsApp menu using Twilio's Content API.

1. Create a Content template in Twilio that renders a WhatsApp interactive menu (buttons/list).
2. Configure the button replies to send back `1`, `2`, `3`.
3. Set:
   - `INTERACTIVE_MENU_MODE=content`
   - `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`
   - `TWILIO_CONTENT_SID_MENU=<your content sid>`
