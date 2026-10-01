# قائمة التسليم

## التشغيل

- `main.py`: نقطة تشغيل البوت والـWebhook.
- `Dockerfile`: صورة التشغيل.
- `docker-compose.yml`: تشغيل البوت مع Redis واستخدام PostgreSQL خارجي.
- `docker-compose.permanent.yml`: تشغيل دائم كامل مع PostgreSQL وRedis وvolumes.
- `.env.example`: متغيرات عامة.
- `.env.permanent.example`: نموذج جاهز للنشر الدائم.
- `DEPLOYMENT_AR.md`: شرح الاستضافة والمتغيرات والفحص.

## التعديلات الأمنية والوظيفية

- `app/webapp/telegram_auth.py`: التحقق من Telegram WebApp initData.
- `app/authorization/middleware.py`: حماية API وأصول الخريطة وربط الصلاحيات.
- `app/webapp/admin_api.py`: مسارات لوحة الإدارة ومسارات تعديل/حذف مسارات التعلم.
- `app/content/admin_service.py`: خدمات إنشاء وتعديل وحذف المسارات.
- `app/bot/routers/start.py`: أوامر `/admin` و`/contentadmin` و`/hologram` وأزرار WebApp.
- `main.py`: تشغيل HTTP/Webhook وتهيئة أوامر Telegram.

## الخريطة الهولوغرامية

- `artifacts/holographic-navigator/`: مصدر React + TypeScript + Vite.
- `app/webapp/static/admin/holographic/`: النسخة المبنية التي تخدمها لوحة الإدارة مباشرة.

## التحقق

- TypeScript build ناجح.
- Python compile ناجح.
- اختبارات المشروع: `28 passed` عند آخر فحص.
- `/healthz` و`/readyz` يعملان محليًا.

## غير مضمن عمدًا

- الأسرار الحقيقية.
- `.env` الحقيقي.
- `node_modules`.
- `__pycache__` و`.pytest_cache`.
- قاعدة البيانات الحية.
