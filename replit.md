# Telegram Academy V5 — Replit

Telegram educational bot with persistent learning progress, AI Tutor, AI Code Reviewer, and a Telegram Mini App IDE.

## Run on Replit

1. Import the repository/ZIP into Replit.
2. Open **Secrets** and add `BOT_TOKEN`.
3. Add `OPENAI_API_KEY` only when you are ready to enable AI.
4. Keep `AI_ENABLED=false` until the key and model are verified.
5. Click **Run**. The HTTP server listens on port 8080 and receives Telegram updates through the HTTPS webhook configured in `WEBHOOK_URL`.
6. Set `WEB_APP_URL` to the public HTTPS URL of this Replit app if you want the Telegram IDE button to open.

### Replit Secrets

Never commit `.env` or API keys. Use Replit Secrets for:

- `BOT_TOKEN`
- `OPENAI_API_KEY`
- `ADMIN_IDS`
- `WEB_APP_URL`
- `AI_ENABLED`
- `AI_MODEL`
- `DATABASE_URL` (required PostgreSQL connection)
- `REDIS_URL` (required Redis connection)
- `PISTON_API_URL` (Piston execution endpoint)
- `PISTON_API_KEY` (only when the selected Piston service requires authorization)

Recommended AI settings after testing:

```text
AI_ENABLED=true
AI_PROVIDER=openai
AI_MODEL=gpt-5.6-luna
AI_TUTOR_DAILY_LIMIT=10
AI_REVIEW_DAILY_LIMIT=3
AI_QUIZ_DAILY_LIMIT=1
```

## Code execution
The IDE sends C++/Python code to Piston through the bot server. The bot does not run learner code locally and no public sandbox container is required. Configure `PISTON_API_URL` and, if required, `PISTON_API_KEY`.

## Health check

`GET /healthz` returns a small JSON health response.

## Data

The runtime database is PostgreSQL configured by `DATABASE_URL`; Redis is configured by `REDIS_URL`.
