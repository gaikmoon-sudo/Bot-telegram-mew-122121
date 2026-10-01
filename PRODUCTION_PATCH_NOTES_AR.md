# ملاحظات الإصدار المحسّن — Telegram Academy

## ما تم إصلاحه

- إصلاح تعارض `CONTENT_STORAGE_BACKEND=local` مع إعداد Docker الإنتاجي عبر اعتماد بيئة `production_docker`.
- إضافة صلاحيات لجميع مسارات لوحة الإدارة، مع اختبار آلي يمنع رجوع المشكلة.
- إضافة `AcademyStore.ping()` واستخدامه في readiness بدل الوصول إلى `_conn` مباشرة.
- إزالة كلمات المرور الافتراضية الخطرة من Compose الإنتاجي واستخدام متغيرات مطلوبة.
- حماية Redis في Compose الإنتاجي بكلمة مرور، وعدم نشره خارج الشبكة الداخلية.
- إضافة شبكة Docker داخلية للخدمات وقفل اتصال PostgreSQL/Redis على الشبكة الخاصة.
- تشغيل التطبيق داخل Docker كمستخدم غير root.
- إضافة Docker healthcheck إلى `/healthz`.
- إضافة `requirements-dev.txt` وتهيئة pytest واعتماد `aiosqlite` المفقود.
- تحديث README بخطوات التشغيل الآمن والتحقق من Compose.

## التحسينات التشغيلية المقترحة المطبقة

- منع التشغيل الصامت بإعدادات أسرار ناقصة في Compose.
- فصل بروفايل Docker الدائم عن بروفايل Replit بوضوح.
- جعل اختبار توافق أسماء مسارات الإدارة والصلاحيات جزءًا من الاختبارات.
- إبقاء AI معطلًا افتراضيًا وعدم تثبيت model ID غير موثق في قالب Docker.

## التحقق

- `python -m compileall`: ناجح.
- استيراد `main`: ناجح.
- اختبارات المشروع: **29 passed**.
- فحص route/permission: لا توجد مسارات ناقصة.
- فحص سياسة إعدادات Docker: ناجح.

## ملاحظات نشر مهمة

1. انسخ `.env.permanent.example` إلى `.env`.
2. استبدل جميع القيم التي تبدأ بـ `replace_with_` بقيم حقيقية قوية.
3. اجعل `REDIS_URL` متوافقًا مع `REDIS_PASSWORD`، مع URL-encoding لأي رموز خاصة.
4. شغّل `docker compose -f docker-compose.permanent.yml config` قبل التشغيل.
5. شغّل النسخة خلف reverse proxy يدعم HTTPS؛ Telegram Webhook وWeb App يتطلبان HTTPS عامًا.
6. نفّذ backup/restore لقاعدة PostgreSQL قبل فتح البوت للعامة.
7. اختبر Telegram Webhook وRedis/PostgreSQL الحقيقيين في staging؛ الاختبارات الآلية لا تستبدل اختبار التكامل الخارجي.
