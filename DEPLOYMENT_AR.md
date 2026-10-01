# Telegram Academy — دليل التسليم والاستضافة

هذه نسخة تسليم من بوت Telegram التعليمي مع لوحة الإدارة، محرر المحتوى، وخريطة Holographic Navigator المرتبطة ببيانات PostgreSQL الفعلية.

## 1. ما الذي تم تضمينه

- بوت Telegram التعليمي.
- PostgreSQL لحفظ المستخدمين والتقدم والمحتوى.
- Redis لحالة المحادثة FSM والتخزين المؤقت.
- Webhook عبر HTTPS.
- Telegram Web App للمختبر ولوحة الإدارة.
- لوحة إدارة المحتوى.
- الخريطة الهولوغرامية ثلاثية الأبعاد.
- وضع 2D بديل.
- إضافة/تعديل/حذف مسارات التعلم والدورات والوحدات والدروس.
- البحث والتنقل و`Ctrl+K` داخل الخريطة.
- حماية Telegram `initData` وRBAC.
- تثبيت حساب المالك الرئيسي عبر `ADMIN_IDS`.
- ملفات React المبنية موجودة بالفعل داخل `app/webapp/static/admin/holographic/`؛ لا تحتاج إلى Node.js عند تشغيل Python في الاستضافة.

## 2. متطلبات الاستضافة

الحد الأدنى:

- Python 3.11 أو أحدث.
- PostgreSQL 14 أو أحدث.
- Redis 6 أو أحدث.
- رابط HTTPS عام ثابت.
- منفذ داخلي يحدده مزود الاستضافة، غالبًا `8080`.
- إمكانية تشغيل عملية طويلة مستمرة؛ لا تستخدم خدمة تنام أو توقف Webhook إلا إذا كان المزود يدعم الاستيقاظ التلقائي.

لإعادة بناء واجهة React مستقبلًا فقط تحتاج Node.js وpnpm، أما النسخة المبنية المرفقة فتعمل بدون ذلك.

## 3. خطوات التشغيل

```bash
cp .env.example .env
# عدّل المتغيرات المطلوبة كما في القسم التالي
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

عند الإقلاع يشغّل التطبيق ترحيلات Alembic تلقائيًا ثم يضبط Webhook Telegram.

للتشغيل عبر Docker:

```bash
cp .env.example .env
docker compose up -d --build
```

للنشر الدائم على VPS أو خادم Docker مستقل مع PostgreSQL وRedis وVolumes دائمة:

```bash
cp .env.permanent.example .env
# غيّر BOT_TOKEN وADMIN_IDS والنطاق وكلمات المرور قبل التشغيل
docker compose -f docker-compose.permanent.yml up -d --build
```

ملف Compose الدائم لا ينشئ HTTPS بنفسه؛ اربط المنفذ `8080` خلف Reverse Proxy أو منصة توفر TLS، ثم اجعل `WEBHOOK_URL` و`WEB_APP_URL` يستخدمان النطاق النهائي عبر HTTPS.

## 4. المتغيرات المطلوبة

### أساسية وإلزامية

| المتغير | مثال | الوظيفة |
|---|---|---|
| `BOT_TOKEN` | `توكن من BotFather` | رمز بوت Telegram. لا تضعه في Git أو داخل المحادثات العامة. |
| `ADMIN_IDS` | `123456789` | أرقام Telegram للمالكين/المشرفين، مفصولة بفواصل. رقمك الرئيسي يجب أن يكون هنا. |
| `DATABASE_URL` | `postgresql://user:password@host:5432/academy` | اتصال PostgreSQL. |
| `REDIS_URL` | `redis://host:6379/0` | اتصال Redis لحالة FSM والكاش. |
| `WEBHOOK_URL` | `https://example.com/telegram/webhook` | الرابط العام الكامل لمسار Webhook. يجب أن يكون HTTPS. |
| `WEBHOOK_SECRET` | قيمة عشوائية طويلة | سر يرسله Telegram مع Webhook. استخدم قيمة مختلفة لكل بيئة. |

### خادم HTTP

| المتغير | القيمة المقترحة | الوظيفة |
|---|---|---|
| `WEBHOOK_PATH` | `/telegram/webhook` | مسار Webhook داخل التطبيق. يجب أن يطابق نهاية `WEBHOOK_URL`. |
| `WEB_SERVER_HOST` | `0.0.0.0` | الاستماع على جميع الواجهات داخل الحاوية/الخدمة. |
| `WEB_SERVER_PORT` | `8080` | المنفذ الداخلي. غيّره إذا كان مزودك يفرض منفذًا آخر. |
| `WEB_APP_URL` | `https://example.com` | أصل HTTPS المستخدم لفتح Web Apps ولوحة الإدارة. لا تضف `/admin`؛ التطبيق يضيف المسار تلقائيًا. |

> يجب أن يكون `WEBHOOK_URL` و`WEB_APP_URL` على نفس النطاق العام أو على نطاقات HTTPS موثوقة. لا تستخدم `localhost` أو HTTP في الإنتاج.

### التخزين

| المتغير | القيمة المقترحة | الوظيفة |
|---|---|---|
| `CONTENT_STORAGE_BACKEND` | `replit` أو `local` | `replit` للاستضافة التي توفر App Storage، و`local` للتجربة أو VM ذات قرص دائم. |
| `APP_STORAGE_BUCKET_ID` | اختياري | معرف bucket عند استخدام Replit App Storage. |
| `CONTENT_UPLOAD_DIR` | اختياري | مجلد التخزين المحلي عند استخدام `local`. يجب أن يكون على قرص دائم. |

### تشغيل الأكواد

| المتغير | القيمة المقترحة | الوظيفة |
|---|---|---|
| `PISTON_API_URL` | `https://emkc.org/api/v2/piston` | مزود تنفيذ كود IDE. |
| `PISTON_API_KEY` | اختياري | مفتاح المزود إذا كان مطلوبًا. |
| `PISTON_TIMEOUT_SECONDS` | `15` | مهلة الاتصال. |
| `PISTON_COMPILE_TIMEOUT_MS` | `5000` | مهلة الترجمة. |
| `PISTON_RUN_TIMEOUT_MS` | `3000` | مهلة التنفيذ. |

لا يتم تشغيل كود المستخدم داخل عملية البوت نفسها؛ يتم إرساله إلى حد تنفيذ خارجي مع مهلات.

### الذكاء الاصطناعي

لمنع استهلاك أي API عند أول تشغيل اتركه معطلًا:

```env
AI_ENABLED=false
```

عند تجهيز مزود الذكاء الاصطناعي:

| المتغير | مثال | الوظيفة |
|---|---|---|
| `AI_ENABLED` | `true` أو `false` | تشغيل/إيقاف ميزات AI. |
| `AI_PROVIDER` | `openai` | مزود النموذج. |
| `AI_MODEL` | اسم النموذج المتاح | النموذج المستخدم. |
| `OPENAI_API_KEY` | مفتاح سري | لا يوضع إلا في Secrets لدى مزود الاستضافة. |
| `AI_TUTOR_DAILY_LIMIT` | `10` | الحد اليومي للمعلم الذكي لكل مستخدم. |
| `AI_REVIEW_DAILY_LIMIT` | `3` | حد مراجعة الأكواد. |
| `AI_QUIZ_DAILY_LIMIT` | `1` | حد الاختبارات الذكية. |
| `AI_CACHE_TTL` | `86400` | مدة كاش Redis بالثواني؛ `0` لتعطيله. |

### الشهادات والمراقبة

| المتغير | القيمة المقترحة | الوظيفة |
|---|---|---|
| | `SENTRY_DSN` | اختياري | رابط مشروع Sentry. |
| `SENTRY_TRACES_SAMPLE_RATE` | `0.10` | نسبة تتبع الأداء. |
| `SENTRY_PROFILES_SAMPLE_RATE` | `0.0` | نسبة profiling. |
| `SENTRY_ENVIRONMENT` | `production` | اسم البيئة في Sentry. |
| `APP_TIMEZONE` | `UTC` أو `Asia/Baghdad` | المنطقة الزمنية للتذكيرات والـstreak. |

### بيانات التواصل

| المتغير | الوظيفة |
|---|---|
| `REPRESENTATIVE_USERNAME` | اسم مستخدم المندوب بدون `@`. |
| `DEVELOPER_USERNAME` | اسم المطور بدون `@`. |
| `ADMIN_USERNAME` | اسم حساب الإدارة بدون `@`. |

## 5. فتح لوحة الإدارة والخريطة

بعد التشغيل من داخل Telegram:

```text
/contentadmin
```

سيظهر زران:

- فتح لوحة إدارة المحتوى.
- فتح الخريطة الهولوغرامية.

كما يمكن للمالك استخدام:

```text
/admin
/hologram
```

فتح رابط `/admin/holographic/` من متصفح عادي لن يرسل Telegram `initData`؛ لذلك لن تظهر البيانات وهذا سلوك أمني مقصود. افتحها من زر WebApp داخل Telegram.

## 6. الملكية والصلاحيات

- ضع رقم حساب المالك في أول قيمة داخل `ADMIN_IDS`.
- لا تضع رقمًا غير موثوق في `ADMIN_IDS`.
- الصلاحيات تعتمد على Telegram ID وليس اسم المستخدم.
- لا يوجد حساب أعلى من المالك الرئيسي في طبقة RBAC.
- لا تشارك `BOT_TOKEN` أو `WEBHOOK_SECRET` أو `OPENAI_API_KEY`.

## 7. الفحص بعد النشر

نفّذ:

```bash
curl https://YOUR_DOMAIN/healthz
curl -i https://YOUR_DOMAIN/readyz
```

المتوقع:

```json
{"status":"ok","service":"telegram-academy","transport":"webhook"}
```

ثم افحص Webhook من جهازك أو من Telegram Bot API:

```bash
curl "https://api.telegram.org/bot$BOT_TOKEN/getWebhookInfo"
```

تحقق من:

- `url` يطابق `WEBHOOK_URL`.
- `pending_update_count` لا يرتفع باستمرار.
- لا يوجد `last_error_message` حديث.

## 8. ما يجب عدم رفعه أو مشاركته

لا ترفع أو تشارك:

- `.env` الحقيقي.
- `BOT_TOKEN`.
- `WEBHOOK_SECRET`.
- `OPENAI_API_KEY`.
- كلمات مرور PostgreSQL وRedis.
- `node_modules`.
- `__pycache__` و`.pytest_cache`.
- نسخة قاعدة البيانات الحية إلا كنسخة احتياطية مشفرة.

## 9. إعادة بناء الخريطة مستقبلًا

```bash
cd artifacts/holographic-navigator
pnpm install
pnpm build
rm -rf ../../app/webapp/static/admin/holographic
mkdir -p ../../app/webapp/static/admin/holographic
cp -R dist/. ../../app/webapp/static/admin/holographic/
```

ثم أعد تشغيل `main.py`.

## 10. ملاحظات الاستضافة المجانية

- الخدمات المجانية التي تنام قد توقف Webhook أو تؤخره.
- PostgreSQL وRedis يجب أن يكونا دائمين، لا مؤقتين.
- استخدم نطاق HTTPS ثابتًا وليس رابط Sandbox مؤقتًا في الإنتاج.
- احفظ نسخة احتياطية من PostgreSQL قبل أي ترقية.
- ابدأ بـ `AI_ENABLED=false` ثم فعّل AI فقط بعد وضع المفتاح والحدود.
