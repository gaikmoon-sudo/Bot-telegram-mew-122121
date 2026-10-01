from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, BotCommandScopeChat, ErrorEvent

from config import get_bot_token, settings
from app.authorization.middleware import AdminAuthorizationMiddleware, admin_http_middleware

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
logger = logging.getLogger(__name__)


def ensure_database_ready() -> None:
    """Run Alembic migrations before importing the runtime store/routers.

    Replit starts the service from a clean process; running migrations here prevents
    the Admin/RBAC schema from lagging behind the code deployed with the bot.
    """
    import subprocess
    import sys

    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is required before starting the bot.")
    logger.info("Running database migrations (alembic upgrade head)")
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)
    logger.info("Database migrations completed")


def setup_observability() -> None:
    """Initialize Sentry only when explicitly configured."""
    if not settings.sentry_dsn:
        return
    try:
        import sentry_sdk
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            traces_sample_rate=max(0.0, min(1.0, settings.sentry_traces_sample_rate)),
            profiles_sample_rate=max(0.0, min(1.0, settings.sentry_profiles_sample_rate)),
            environment=settings.environment,
            send_default_pii=False,
        )
        logger.info("Sentry observability enabled")
    except Exception:
        logger.exception("Could not initialize Sentry; continuing without monitoring")


async def set_commands(bot: Bot) -> None:
    commands = [
        BotCommand(command="start", description="بدء الأكاديمية"),
        BotCommand(command="learn", description="أكمل من حيث توقفت"),
        BotCommand(command="courses", description="دوراتي"),
        BotCommand(command="progress", description="تقدمي التعليمي"),
        BotCommand(command="profile", description="حسابي"),
        BotCommand(command="achievements", description="إنجازاتي"),
        BotCommand(command="favorites", description="المحفوظات"),
        BotCommand(command="reminders", description="التذكيرات اليومية"),
        BotCommand(command="certificate", description="شهادتي"),
        BotCommand(command="privacy", description="سياسة الخصوصية"),
        BotCommand(command="delete_my_data", description="حذف بياناتي"),
        BotCommand(command="help", description="المساعدة"),
        BotCommand(command="ai", description="المعلم الذكي"),
        BotCommand(command="contentadmin", description="إدارة المحتوى"),
    ]
    await bot.set_my_commands(commands)
    raw = ",".join(str(item) for item in settings.admin_ids)
    admin_commands = commands + [BotCommand(command="admin", description="لوحة الإدارة"), BotCommand(command="hologram", description="الخريطة الهولوغرامية"), BotCommand(command="broadcast", description="بث إداري")]
    for item in raw.split(","):
        if item.strip().isdigit():
            try:
                await bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(chat_id=int(item.strip())))
            except Exception:
                logger.exception("Could not set admin commands for %s", item)


async def reminder_loop(bot: Bot, runtime_store) -> None:
    while True:
        try:
            from datetime import datetime
            from zoneinfo import ZoneInfo
            tz_name = settings.timezone
            try:
                tz = ZoneInfo(tz_name)
            except Exception:
                tz = ZoneInfo("UTC")
            hour = datetime.now(tz).hour
            user_ids = await asyncio.to_thread(runtime_store.reminder_users, hour)
            for uid in user_ids:
                if not await asyncio.to_thread(runtime_store.claim_reminder, uid):
                    continue
                try:
                    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
                    stats = await asyncio.to_thread(runtime_store.snapshot, uid, 13)
                    await bot.send_message(uid, f"⏰ <b>وقت التعلم</b>\n\nلديك {stats['completed']}/13 درسًا مكتملًا.\n🔥 Streak: {stats['streak']} يوم", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="▶️ أكمل من حيث توقفت", callback_data="continue_learning")]]))
                except Exception:
                    logger.exception("Reminder failed for user %s", uid)
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("Reminder loop failed")
            await asyncio.sleep(60)


def webhook_endpoint() -> tuple[str, str, str | None]:
    """Return the public webhook URL, local route and optional secret."""
    from urllib.parse import urlparse
    raw_url = settings.webhook_url
    if not raw_url:
        raise RuntimeError("WEBHOOK_URL is required; polling is not supported.")
    parsed = urlparse(raw_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise RuntimeError("WEBHOOK_URL must be a complete HTTPS URL.")
    path = parsed.path.rstrip("/") or settings.webhook_path
    if not path.startswith("/"):
        path = f"/{path}"
    public_url = f"{parsed.scheme}://{parsed.netloc}{path}"
    secret = settings.webhook_secret or None
    return public_url, path, secret


async def set_webhook(bot: Bot, dp: Dispatcher) -> str:
    """Register Telegram updates on the configured public HTTPS endpoint."""
    public_url, _path, secret = webhook_endpoint()
    await bot.set_webhook(
        public_url,
        secret_token=secret,
        drop_pending_updates=False,
        allowed_updates=dp.resolve_used_update_types(),
    )
    logger.info("Telegram webhook configured at %s", public_url)
    return public_url


async def build_web_server(dp: Dispatcher, bot: Bot):
    """Build the aiohttp server and register the Telegram webhook endpoint."""
    from aiohttp import web
    from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
    from app.webapp.api import setup_webapp_routes
    from app.webapp.admin_api import setup_admin_routes, telegram_admin_identity_middleware
    host = settings.web_server_host
    port = settings.web_server_port
    _public_url, path, secret = webhook_endpoint()

    @web.middleware
    async def security_headers(request, handler):
        response = await handler(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault("X-Frame-Options", "DENY")
        return response

    app = web.Application(
        client_max_size=22 * 1024 * 1024,
        middlewares=[security_headers, telegram_admin_identity_middleware, admin_http_middleware],
    )

    async def healthz(_request):
        return web.json_response({"status": "ok", "service": "telegram-academy", "transport": "webhook"})

    async def readyz(_request):
        """Report dependency readiness separately from process liveness."""
        checks = {"database": False, "redis": False}
        try:
            from app.storage.postgres import store
            await asyncio.to_thread(store.ping)
            checks["database"] = True
        except Exception:
            logger.exception("Readiness database check failed")
        try:
            from infrastructure.redis.connection import ping_redis
            checks["redis"] = await ping_redis()
        except Exception:
            logger.exception("Readiness Redis check failed")
        ready = all(checks.values())
        return web.json_response(
            {"status": "ready" if ready else "not_ready", "checks": checks},
            status=200 if ready else 503,
        )

    app.router.add_get("/healthz", healthz)
    app.router.add_get("/readyz", readyz)
    setup_webapp_routes(app)
    setup_admin_routes(app)
    SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=secret).register(app, path=path)
    setup_application(app, dp, bot=bot)
    await set_webhook(bot, dp)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    logger.info("HTTP server listening on %s:%s; webhook path=%s", host, port, path)
    return runner


async def run_webhook(http_runner) -> None:
    try:
        await asyncio.Event().wait()
    finally:
        await http_runner.cleanup()

async def main() -> None:
    settings.validate_production()
    ensure_database_ready()

    # Import the runtime store only after Alembic has materialized the normalized schema.
    from app.bot.fsm import build_fsm_storage
    from app.bot.middlewares.core import LoggingMiddleware, ThrottlingMiddleware
    from app.bot.routers.start import router as start_router
    from app.bot.routers.dashboard import router as dashboard_router
    from app.bot.routers.ai_tutor import router as ai_router
    from app.storage.postgres import store
    from app.webapp.api import setup_webapp_routes
    from app.webapp.admin_api import setup_admin_routes, telegram_admin_identity_middleware

    setup_observability()

    token = get_bot_token()
    bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    storage, storage_name = build_fsm_storage()
    dp = Dispatcher(storage=storage)
    # One centralized boundary covers all admin commands, callbacks and FSM steps.
    dp.message.outer_middleware(AdminAuthorizationMiddleware())
    dp.callback_query.outer_middleware(AdminAuthorizationMiddleware())
    dp.include_router(start_router)
    dp.include_router(dashboard_router)
    dp.include_router(ai_router)
    dp.message.middleware(LoggingMiddleware())
    dp.callback_query.middleware(LoggingMiddleware())
    dp.poll_answer.middleware(LoggingMiddleware())
    dp.message.middleware(ThrottlingMiddleware())
    dp.callback_query.middleware(ThrottlingMiddleware())

    @dp.errors()
    async def global_error_handler(event: ErrorEvent):
        exc = event.exception
        logger.error("Unhandled Telegram error: %s", exc, exc_info=(type(exc), exc, exc.__traceback__))
        try:
            import sentry_sdk
            sentry_sdk.capture_exception(exc)
        except Exception:
            pass
        try:
            if event.update.message:
                await event.update.message.answer("⚠️ حدث خطأ غير متوقع. تم تسجيل المشكلة، يرجى المحاولة مرة أخرى.")
            elif event.update.callback_query:
                await event.update.callback_query.answer("⚠️ حدث خطأ غير متوقع. حاول مرة أخرى.")
        except Exception:
            logger.exception("Could not notify user about error")

    await set_commands(bot)
    http_runner = await build_web_server(dp, bot)
    reminder_task = asyncio.create_task(reminder_loop(bot, store))
    logger.info("Academy bot starting; FSM=%s", storage_name)
    try:
        await run_webhook(http_runner)
    finally:
        reminder_task.cancel()
        await asyncio.gather(reminder_task, return_exceptions=True)
        store.close()
        try:
            from infrastructure.database.session import close_database
            await close_database()
        except Exception:
            logger.exception("Could not close PostgreSQL SQLAlchemy pool cleanly")
        try:
            from infrastructure.redis.connection import close_redis
            await close_redis()
        except Exception:
            logger.exception("Could not close Redis connection cleanly")
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("تم إيقاف البوت بنجاح.")
