# Production/Replit Fixes Applied

- Separated the legacy Telegram runtime tables under `academy_*` so they no longer collide with the normalized SQLAlchemy/Alembic schema.
- Added migration bootstrap for a fresh PostgreSQL database and safe migration of the previous legacy `users` schema.
- `ADMIN_IDS` are bootstrapped as `SUPER_ADMIN` during the first Alembic migration.
- Telegram registration now keeps the normalized RBAC `users` identity in sync.
- Web Admin published lessons are mirrored into the Telegram runtime catalog; drafts remain hidden from Telegram until published.
- Web Admin lesson update/delete also updates/removes the Telegram runtime copy after the normalized DB transaction succeeds.
- `main.py` validates production settings and runs `alembic upgrade head` automatically before importing the runtime store/routers.
- Replit deployment configuration now explicitly runs `python main.py` and exposes port 8080.
- `WEBHOOK_URL` can fall back to `REPLIT_APP_DOMAIN`; `WEBHOOK_SECRET` and `ADMIN_IDS` are required for production validation.
- Added clean shutdown of the SQLAlchemy PostgreSQL pool.

## Replit required Secrets

`BOT_TOKEN`
`ADMIN_IDS`
`DATABASE_URL`
`REDIS_URL`
`WEBHOOK_SECRET`
`WEBHOOK_URL` (unless Replit provides `REPLIT_APP_DOMAIN` and the fallback is suitable)

Optional: `OPENAI_API_KEY`, `AI_ENABLED`, `WEB_APP_URL`, Sentry/Piston settings.

## Replit file storage

- `CONTENT_STORAGE_BACKEND=replit` uses Replit App Storage for persistent uploads; create a bucket in the Replit project and set it as the default, or supply `APP_STORAGE_BUCKET_ID`.
- `CONTENT_STORAGE_BACKEND=local` is for development only. Deployment filesystems are not a durable upload store.
- The official `replit.object-storage` Python package currently requires Python <3.13; `.replit` therefore selects Python 3.12.

## Verification performed in this environment

- Python `compileall`: passed.
- Admin JavaScript `node --check`: passed in baseline; repeat after final edits.
- Alembic revision chain: 01 -> 02 -> 03; offline PostgreSQL SQL generation passed after parameter binding fix.
- Unit tests use SQLite and mocked Telegram/runtime storage; they do not establish connectivity to real PostgreSQL, Redis, Telegram, OpenAI, Piston, or Replit App Storage.
