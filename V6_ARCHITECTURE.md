# Telegram Academy V6 — Architecture

V6 separates editable course content, application learning logic, security helpers, Telegram presentation, storage, AI, and Web App.

## Runtime
- Telegram: Aiogram Webhook through the aiohttp API server; `WEBHOOK_URL` is required.
- HTTP: aiohttp for health and Web App.
- Runtime DB: PostgreSQL configured exclusively through `DATABASE_URL`.
- Redis: required for FSM and cache, configured through `REDIS_URL`.
- AI: provider configured through environment variables.
- Code execution: Piston API through `PISTON_API_URL`, with normalized results and timeout/error handling.

## Content
Core C++ lessons are stored in `content/cpp_beginner.json` so content can be edited without touching Telegram handlers.
