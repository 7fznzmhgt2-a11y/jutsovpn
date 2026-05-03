# JutsoVPN

Monorepo for JutsoVPN — a Telegram-bot-based VPN service.

## Layout

- `bot/` — Telegram bot (aiogram). Handles `/start` and shows user profile + Mini App link. Powered by [@jutsovpnbot](https://t.me/jutsovpnbot).
- `backend/` — FastAPI backend with admin panel at `/jutso`. Stores in-memory state (users, payments, broadcasts, promos), serves the Mini App static, exposes `/api/admin/*` endpoints.
- `site/` — Mini App frontend (vanilla JS + CSS). Mirrored into `backend/static/` at deploy time.

## Channels

- App: https://jutsovpn-backend-gfyfeciw.fly.dev/
- Admin: https://jutsovpn-backend-gfyfeciw.fly.dev/jutso
- News: https://t.me/jutsovpn
- Support: https://t.me/jutsovpn_support

## Running locally

### Backend
```bash
cd backend
uv sync  # or pip install -e .
BOT_USERNAME=jutsovpnbot SESSION_SECRET=dev INTERNAL_API_KEY=dev uvicorn app.main:app --reload
```

### Bot
```bash
cd bot
pip install aiogram aiohttp
BOT_TOKEN=... BOT_USERNAME=jutsovpnbot \
  WEBAPP_URL=http://localhost:8000/ \
  ADMIN_URL=http://localhost:8000/jutso \
  BACKEND_URL=http://localhost:8000 \
  INTERNAL_API_KEY=dev \
  CHANNEL_URL=https://t.me/jutsovpn \
  SUPPORT_URL=https://t.me/jutsovpn_support \
  python bot.py
```

### Site
The site is served by the backend statically — copy `site/` files into `backend/static/` before deploy, or symlink during dev.

## Deploy

Backend deploys to Fly.io as `jutsovpn-backend`. See `backend/fly.toml`.
