# V7 Audit Report

**Session:** SESSION 00 — Audit only  
**Date:** 2026-09-27  
**Scope:** قراءة وفحص فقط؛ لم تتم إعادة هيكلة أو تغيير منطق المشروع في هذه الجلسة.

## 1. الحالة العامة

- المشروع Python Telegram bot مبني على `aiogram` مع خادم `aiohttp`.
- نقطة التشغيل الأساسية: `main.py`.
- المشروع الحالي مضبوط على Telegram Webhook عبر `WEBHOOK_URL`، وليس Polling.
- يوجد Web IDE/API، AI Tutor، Piston code runner، Sentry، شهادات مجانية، PostgreSQL runtime store وRedis FSM/cache.
- توجد ملفات legacy ومناطق تحتاج جلسات لاحقة، خصوصاً التوافق بين schema/runtime store وSQLAlchemy/Alembic.

## 2. Entry points والتشغيل

- `main.py:main()` ينشئ Bot/Dispatcher، يحمّل routers، يهيئ Sentry، يبني aiohttp server، ويسجل Webhook تلقائياً.
- Webhook endpoint يُسجّل عبر `SimpleRequestHandler`، والرابط العام يُقرأ من `WEBHOOK_URL`.
- `WEB_SERVER_HOST` و`WEB_SERVER_PORT` يحددان الاستماع المحلي.
- Docker entrypoint: `python main.py`.
- Replit entrypoint في `.replit`: `python main.py`.

## 3. قاعدة البيانات

### runtime الفعلي

- `app/storage/postgres.py` هو مخزن التشغيل الفعلي المستخدم عبر `store`.
- الاتصال يعتمد على `DATABASE_URL` فقط.
- يستخدم `psycopg` وطبقة SQL مباشرة مع مخطط يتم إنشاؤه من `_init_schema()`.
- الجداول التشغيلية تشمل المستخدمين، التقدم، الاختبارات، الشارات، الشهادات، سجل دفع الشهادات، AI history/quota، drafts وغيرها.

### SQLAlchemy/Alembic

- توجد Models منظمة في `app/*/models.py` وتستخدمها `alembic/env.py`.
- `infrastructure/database/session.py` يوفر Async SQLAlchemy engine باستخدام `DATABASE_URL`.
- `alembic/versions/` لا يحتوي حالياً على revision فعلي؛ يوجد `.gitkeep` فقط.
- توجد بذلك حالياً مساحتان منفصلتان: runtime schema في `app/storage/postgres.py` وSQLAlchemy metadata/Alembic. هذه نقطة مخاطرة يجب معالجتها في SESSION 03، دون حذف بيانات أو تنفيذ migration destructive.

### ملاحظة legacy

- يوجد ملف `data/academy.sqlite3` في الشجرة. يجب تحديد هل هو artifact قديم أم مصدر بيانات يحتاج migration قبل أي إزالة، ولا يجوز حذفه تلقائياً.

## 4. Redis وFSM/cache

- `app/bot/fsm.py` يستخدم `RedisStorage.from_url(settings.redis_url)`.
- `REDIS_URL` مطلوب؛ لا يوجد MemoryStorage fallback صامت في الكود الحالي.
- `infrastructure/redis/connection.py` يوفر client مشتركاً للـcache/عمليات Redis.
- AI cache يعتمد Redis عند توفره وفق منطق `app/ai/cache.py`.
- جلسات لاحقة مطلوبة لمراجعة distributed locks/rate limiting/حذف بيانات Redis.

## 5. WebApp

- `app/webapp/api.py` يوفر endpoints للـWeb IDE، حفظ المسودات والتنفيذ.
- `app/webapp/static/index.html` هو واجهة IDE.
- التحقق من Telegram Web App `initData` موجود في مسار API.
- التنفيذ الخارجي يتم عبر `app/webapp/piston.py`؛ لا يتم تشغيل كود المتدرب داخل عملية البوت.

## 6. AI

- `app/ai/service.py` يوفر tutor وcode review وquota وcache.
- الأخطاء تُلتقط بواسطة `infrastructure/observability/sentry.py` مع tags، مع استمرار رفع الاستثناء للـhandler المناسب.
- توجد حدود يومية للـtutor/review/quiz في environment.
- يجب مراجعة timeouts وgraceful failure واختبارات provider في SESSION 14.

## 7. Payments والشهادات

- مسار الشهادة موجود في `app/bot/routers/start.py`.
- إصدار الشهادة مجاني ولا يستخدم Telegram Stars أو Invoice.
- `pre_checkout_query` يتحقق من payload والمستخدم والمبلغ وإكمال المسار.
- لا توجد معالجة دفع لإصدار الشهادة في الإصدار الحالي.
- `certificate_payments` في runtime schema يضيف idempotency عبر payload/charge IDs والمفتاح المركب للمستخدم والمسار.
- يلزم في SESSION 12 اختبار حالات duplicate/retry/partial failure بشكل فعلي.

## 8. Code Runner

- Piston URL وkey وtimeouts في `.env.example`.
- Piston يكتشف runtimes ويعيد نتيجة موحدة للـWeb IDE وAI review.
- توجد معالجة timeout/network/protocol/runtime errors، مع Sentry capture للأخطاء.
- يلزم لاحقاً مراجعة output-size/concurrency/per-user limits في SESSION 10.

## 9. Notifications وreminders

- توجد `reminder_loop()` داخل `main.py` تعتمد على `while True` و`sleep(3600)`.
- يوجد تخزين reminder state في runtime store.
- تحتاج هذه المنطقة SESSION 11 لمراجعة retries/idempotency/rate limiting وعدم الاعتماد على loop هش عند التوسع.

## 10. Admin

- Admin handlers موجودة داخل `app/bot/routers/start.py` و`dashboard.py`.
- authorization يعتمد حالياً على `ADMIN_IDS` وفحوصات يدوية في handlers.
- يحتاج SESSION 15 إلى centralized authorization وaudit log للعمليات الحساسة.

## 11. Configuration وSecrets

- `.env.example` يحتوي `BOT_TOKEN`, `DATABASE_URL`, `REDIS_URL`, `WEBHOOK_URL`, `SENTRY_DSN`, AI/Piston/Stars settings.
- `config.py` يحتوي Settings جزئية، بينما بعض المتغيرات تقرأ مباشرة من `os.getenv` في ملفات مختلفة.
- هذه ازدواجية configuration معروفة وتندرج تحت SESSION 02.
- لا توجد أسرار فعلية ضمن التقرير أو الملفات التي تم إنشاؤها.

## 12. Replit/Deployment

- `.replit` يشغل `python main.py` ويعرض المنفذ 8080.
- `Dockerfile` يستخدم Python 3.12 ويشغل `python main.py`.
- `docker-compose.yml` يشغل bot وRedis؛ PostgreSQL خارجي عبر `DATABASE_URL`.
- `HEALTHCHECK.md` يوثق `/healthz` وWebhook وSentry، لكن `/health/live` و`/health/ready` غير موجودين بعد.

## 13. Testing baseline — لم تُنفذ في SESSION 00

- يوجد ملف اختبار واحد: `tests/test_v6_core.py`.
- توجد اختبارات للمحتوى وrate limiter وcontent limits فقط.
- لا توجد حالياً اختبارات واضحة لـPostgreSQL/Redis/Webhook/payments/AI failures/Piston/WebApp auth/deletion.
- يجب تنفيذ baseline في SESSION 01، ثم توسيع الاختبارات في SESSION 16.

## 14. الملفات الحرجة للجلسات التالية

- `main.py`
- `config.py`
- `app/storage/postgres.py`
- `infrastructure/database/session.py`
- `alembic/env.py`
- `app/bot/fsm.py`
- `infrastructure/redis/connection.py`
- `app/bot/routers/start.py`
- `app/ai/service.py`
- `app/webapp/api.py`
- `app/webapp/piston.py`
- `.env.example`, `Dockerfile`, `docker-compose.yml`, `.replit`

## 15. الخلاصة

المشروع يحتوي معظم features المطلوبة من الجلسات السابقة، لكنه **ليس Production Ready وفق معيار V7 بعد**. أكبر المخاطر الظاهرة من الفحص فقط:

1. عدم وجود Alembic revisions فعلية رغم وجود Models وAlembic environment.
2. وجود runtime SQL schema مستقل عن SQLAlchemy metadata.
3. وجود SQLite artifact يحتاج قراراً موثقاً قبل الإزالة.
4. تغطية الاختبارات محدودة جداً.
5. configuration موزعة بين Settings و`os.getenv`.
6. health readiness وعمليات التوسع/التوزيع تحتاج جلسات مخصصة.

لم تُجرَ أي تغييرات على منطق التطبيق في SESSION 00.
