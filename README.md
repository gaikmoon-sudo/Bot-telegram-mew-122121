# Telegram Academy V6 Pro

# Telegram Academy V5 — AI Academy

نسخة إنتاجية مطوّرة من Telegram Academy مع الحفاظ على أساس المشروع السابق و13 درس C++ الأصلية، وإضافة طبقة AI تعليمية اختيارية وTelegram Web App للمختبر البرمجي.

## أبرز الميزات

- تقدم دائم عبر PostgreSQL باستخدام `DATABASE_URL`.
- Redis FSM والتخزين المؤقت باستخدام `REDIS_URL`.
- عدم إسقاط التحديثات المعلقة عند إعادة التشغيل.
- Telegram Quiz Polls أصلية مع explanation ونتيجة نهائية.
- BotCommands و`▶️ أكمل من حيث توقفت` والتنقل السابق/التالي.
- تسجيل مرن مع `تخطي` وموافقة خصوصية.
- `/privacy` و`/delete_my_data`.
- حماية Ethical Hacking بإقرار الاستخدام المصرح.
- throttling + logging + global error handler + Sentry hooks.
- Streak + reminders + badges + leaderboard + certificates.
- لوحة Admin للإحصائيات والبث وإضافة الدروس.
- Telegram Web App IDE باستخدام Monaco Editor وحفظ المسودات.
- AI Tutor + ذاكرة محادثة + RAG خفيف من محتوى الأكاديمية.
- AI Code Reviewer لـ C++/Python.
- حصص يومية للـAI وتقييم الإجابات.
- Docker/Redis/Webhook جاهزة للإنتاج عندما تكون البيئة المناسبة متوفرة.

## تشغيل محلي

```bash
cp .env.example .env
# ضع BOT_TOKEN وADMIN_IDS
pip install -r requirements.txt
python main.py
```

`DATABASE_URL` و`REDIS_URL` مطلوبان للتشغيل.

## تشغيل على Replit

النسخة الحالية مجهزة للتشغيل على Replit.

1. استورد المشروع إلى Replit.
2. افتح **Secrets** وأضف `BOT_TOKEN`, `ADMIN_IDS`, `DATABASE_URL`, `REDIS_URL`, `WEBHOOK_SECRET` و`WEBHOOK_URL`.
3. اترك `AI_ENABLED=false` حتى تنتهي من اختبار البوت الأساسي.
4. اضغط **Run**؛ سيشغّل `main.py` migrations تلقائيًا قبل البوت.
5. الخادم يستمع على المنفذ 8080 ويستقبل تحديثات Telegram عبر Webhook مضبوط في `WEBHOOK_URL`.
7. لفتح Web IDE من Telegram، اضبط `WEB_APP_URL` على عنوان HTTPS العام للتطبيق، أو اتركه فارغًا إذا كانت بيئة Replit توفر `REPLIT_APP_DOMAIN` أو `REPLIT_DEV_DOMAIN`.

راجع `REPLIT_SETUP.md` للخطوات التفصيلية.

### Secrets التي يمكن استخدامها على Replit

```text
BOT_TOKEN
ADMIN_IDS
OPENAI_API_KEY
AI_ENABLED
AI_PROVIDER
AI_MODEL
AI_TUTOR_DAILY_LIMIT
AI_REVIEW_DAILY_LIMIT
AI_QUIZ_DAILY_LIMIT
WEB_APP_URL
WEBHOOK_URL
WEBHOOK_PATH
WEBHOOK_SECRET
REDIS_URL
SENTRY_DSN
```

**لا تضع الأسرار داخل GitHub أو `.env` المرفوع إلى المستودع. استخدم Replit Secrets.**

## Sentry والشهادات المجانية
- فعّل Sentry عبر `SENTRY_DSN`. يتم التقاط أخطاء تهيئة/استدعاء AI Tutor، فشل مراجعة الأكواد، وأخطاء الشبكة أو الخدمة من Piston مع tags آمنة دون تسجيل الكود أو المفاتيح.
- يتم إصدار الشهادة مجانًا بعد إكمال المسار، ولا يطلب البوت بطاقة أو وسيلة دفع.
- اضبط الشهادة مجانية بالكامل؛ لا يطلب البوت بطاقة ائتمان ولا يفتح فاتورة أو عملية دفع.
- وجود سجل دفع وشهادة سابق يمنع إعادة إصدار الشهادة عند إعادة إرسال تحديث Telegram.

## AI Academy

AI معطل افتراضيًا حتى لا يسبب أي استهلاك API عند رفع المشروع لأول مرة.

الإعداد المقترح بعد إضافة المفتاح واختباره:

```env
AI_ENABLED=true
AI_PROVIDER=openai
AI_MODEL=gpt-5.6-luna
AI_TUTOR_DAILY_LIMIT=10
AI_REVIEW_DAILY_LIMIT=3
AI_QUIZ_DAILY_LIMIT=1
```

لا تضع قيمة حقيقية لـ`OPENAI_API_KEY` داخل Git أو ملفات المصدر. المفتاح يجب أن يبقى server-side فقط.

## Web IDE وتنفيذ الأكواد

Web IDE متاح للتحرير والحفظ. زر التشغيل يرسل كود C++/Python إلى Piston API عبر الخادم فقط. لا يتم تشغيل كود المستخدم محليًا داخل عملية البوت، وتوجد مهلات ومعالجة أخطاء للترجمة والتنفيذ والاتصال.

اضبط `PISTON_API_URL` و`PISTON_API_KEY` عند الحاجة، ويمكن لـAI Code Reviewer استخدام نتيجة Piston أو إكمال التحليل الساكن عند تعذر الخدمة.

## Docker

```bash
cp .env.permanent.example .env
# استبدل كل replace_with_*، واجعل REDIS_URL متوافقًا مع REDIS_PASSWORD
docker compose -f docker-compose.permanent.yml config
docker compose -f docker-compose.permanent.yml up -d --build
```

يستخدم ملف `docker-compose.permanent.yml` PostgreSQL وRedis على شبكة داخلية،
ويشغل التطبيق كمستخدم غير root. التخزين المحلي في هذا الملف دائم عبر volume؛
أما Replit فيجب أن يستخدم `CONTENT_STORAGE_BACKEND=replit` وApp Storage.
للوضع الإنتاجي عبر webhook، اضبط `WEBHOOK_URL` على عنوان HTTPS العام،
وتأكد من أن reverse proxy يمرر `/healthz`, `/readyz` ومسار Webhook عبر HTTPS.

لتشغيل الاختبارات محليًا:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest
```

## الأمان

- لا تضع `BOT_TOKEN` أو `OPENAI_API_KEY` داخل Git.
- `ADMIN_IDS` أرقام Telegram فقط.
- `/delete_my_data` يحذف بيانات الحساب التعليمية وبيانات AI المرتبطة به من PostgreSQL.
- Telegram Web App `initData` يتم التحقق منه على الخادم قبل الوثوق بهوية المستخدم.
- AI Code Reviewer لا يشغّل الكود عبر مزود AI.
- مسار Ethical Hacking يتطلب إقرار الاستخدام المصرح.

## AI cache and code-execution safety

AI responses use a best-effort Redis cache when `REDIS_URL` is configured. The
cache key is SHA-256 over the complete model input (mode, system prompt,
messages and model), so personalized responses are not keyed by prompt text
alone. Redis failures never prevent the AI provider from responding. Set
`AI_CACHE_TTL=0` to disable the cache.

The code runner uses Piston as an external execution boundary. Piston
responses are normalized with stdout, stderr, exit status and phase information.
Network, timeout, rejected-request and unavailable-runtime errors are returned
as safe user-facing results and do not crash the bot.

Sentry is optional. Configure `SENTRY_DSN` through Replit Secrets. The default
trace sample rate is intentionally low; increase it only when needed.
