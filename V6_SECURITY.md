# V6 Security

- Never commit Telegram or AI secrets. Use Replit Secrets.
- Web App authentication must use Telegram `initData` validation.
- Code execution is rate-limited and bounded by size/time/resource controls.
- Keep the Sandbox isolated from the public internet and never expose its internal token.
- Use PostgreSQL + worker queues before scaling to large user counts.
