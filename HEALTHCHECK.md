# Production checklist

- Set `BOT_TOKEN`.
- Set `ADMIN_IDS` to numeric Telegram user IDs only.
- In Docker, keep `REDIS_URL=redis://redis:6379/0`.
- Set `WEBHOOK_URL` to the complete public HTTPS webhook endpoint and configure the reverse proxy to forward `WEB_SERVER_PORT`.
- Set a long random `WEBHOOK_SECRET`.
- Configure `SENTRY_DSN` after creating a Sentry project.
- Back up `/app/data` if SQLite is used.
- For multi-instance production, migrate the persistent domain data to PostgreSQL and keep Redis for FSM.

- Configure `SENTRY_DSN` only when enabling monitoring. Certificates are free and do not use Telegram payments or credit-card flows.
