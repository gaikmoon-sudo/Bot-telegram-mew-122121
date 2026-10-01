# Telegram Academy V5.2 — Production/Replit Patch

This build applies the reviewed hardening and runtime fixes while preserving the existing bot UX.

## Fixed

- Fixed invalid duplicated `tsconfig.json` root object.
- Added optional `DATABASE_URL` configuration so the SQLAlchemy PostgreSQL layer can be imported safely without PostgreSQL configured.
- Added `SQLAlchemy` and `asyncpg` dependencies for the optional PostgreSQL layer.
- Scoped AI Redis cache keys by Telegram user and added best-effort per-user cache deletion during account deletion.
- Added bounded in-memory throttling storage to prevent unbounded growth.
- Added admin re-authorization on every lesson-creation FSM step.
- Added size validation to admin-created lesson fields.
- Validated lesson IDs before recording lesson completion.
- Made progress snapshots count only the requested core lesson range, preventing custom lessons from inflating the 13-lesson progress display.
- Added configurable IANA timezone (`APP_TIMEZONE`) for reminder/streak date calculations.
- Removed Python bytecode artifacts from the release package.

## Replit setup

Required Secret:

- `BOT_TOKEN`

Optional:

- `REDIS_URL` — enables persistent FSM/cache/rate-limit acceleration where configured.
- `OPENAI_API_KEY` — required only when AI is enabled.
- `AI_ENABLED=true` — enables AI.
- `AI_MODEL` — model name configured for the OpenAI account.
- `APP_TIMEZONE=UTC` — IANA timezone used by daily reminders and local-date streak/quota logic.
- `DATABASE_URL` — optional; enables the separate SQLAlchemy PostgreSQL layer. The current default bot runtime remains SQLite for simple Replit operation.

The bot now requires `WEBHOOK_URL` and runs through the aiohttp Telegram webhook endpoint.
