# تقرير التدقيق الهندسي — Telegram Educational Bot / Replit

**النطاق:** مراجعة نسخة الأرشيف المرفقة وإصلاح عيوب تشغيلية وأمنية دون إعادة بناء المشروع أو حذف ميزات. هذه مراجعة للكود واختبارات محلية؛ لم يُنشر التطبيق ولم تُغيّر قاعدة بيانات أو webhook حقيقي.

## CRITICAL

- **تهيئة قاعدة جديدة كانت ستفشل أثناء bootstrap لمشرفي `ADMIN_IDS`.**
  - **الملف:** `alembic/versions/20260927_01_admin_rbac_audit.py`
  - **السبب:** تمرير قيم bind كوسيط ثانٍ لـ`op.execute` لا يربطها بالاستعلام، كما أن إنشاء UUID كنص لا يضمن binding متوافقًا مع عمود PostgreSQL UUID.
  - **الإصلاح:** ربط القيم بـ`.bindparams(...)` وتمرير UUID typed؛ طُبق التصحيح أيضًا على نسخ هوية المستخدمين القديمة. تم توليد SQL للترحيل offline بنجاح؛ لم يتوفر PostgreSQL لاختبار upgrade online.

**لا يوجد خلل Critical معروف غير معالج ضمن ما أمكن اختباره محليًا.**

## HIGH

- **مخزن الرفع المحلي يفقد الملفات عند إعادة نشر Replit.**
  - **الملفات:** `app/webapp/admin_api.py`, `config.py`, `requirements.txt`, `pyproject.toml`, `.replit`, `.env.example`, `REPLIT_SETUP.md`
  - **السبب:** كان الرفع والتنزيل يعتمدان على القرص المحلي المؤقت.
  - **الإصلاح:** أضيف backend يستخدم SDK الرسمي لـReplit App Storage افتراضيًا، مع إبقاء `local` للتطوير والاختبارات، ونقل عمليات SDK المتزامنة خارج event loop. اختير Python 3.12 لأن الحزمة الرسمية الحالية تتطلب Python أقل من 3.13. **يلزم إنشاء bucket وربطه في مشروع Replit قبل استخدام الرفع**؛ لم يكن ذلك متاحًا من ملف ZIP.

- **حلقة التذكيرات كانت تشير إلى متغير `store` غير معرّف، وclaim التذكير معرضًا للسباق بين instances.**
  - **الملفات:** `main.py`, `app/storage/postgres.py`
  - **السبب:** المتجر كان محليًا داخل startup، بينما الحلقة تبحث عنه كاسم عالمي؛ كما كان منع التكرار عبارة عن SELECT ثم UPDATE منفصلين.
  - **الإصلاح:** تمرير المتجر صراحةً، نقل استدعاءاته المتزامنة إلى thread pool، واستبدال القراءة/التحديث بعملية PostgreSQL ذرية `UPDATE … WHERE … RETURNING`.

- **بقيت استدعاءات `AcademyStore` المتزامنة في handlers البوت تحجب asyncio.**
  - **الملف:** خصوصًا `app/bot/routers/start.py`, `dashboard.py`, `ai_tutor.py`.
  - **السبب:** طبقة AcademyStore القديمة تستخدم `psycopg` المتزامن؛ فحص الشجرة وجد 71 موضع استدعاء من routers.
  - **الإجراء:** عُزلت إلى thread pool مسارات التذكير ومزامنة Admin Panel التي عُدلت هنا، لكن نقل جميع handlers يتطلب تغييرًا واسعًا لعقد استدعاء التخزين. بقي هذا الخطر عاليًا ولم أجرِ refactor شاملًا تجنبًا لتغيير architecture أو كسر ميزات.

- **حفظ الدرس الإداري يسبق نسخ الدرس إلى مخزن البوت المنفصل.**
  - **الملف:** `app/webapp/admin_api.py`
  - **السبب:** نجاح معاملة SQLAlchemy لا يعني نجاح المزامنة اللاحقة إلى AcademyStore؛ إذا فشلت الخدمة الثانية فقد يحفظ الدرس في اللوحة بينما لا يظهر في البوت، وقد يرى المستخدم خطأً بعد حفظ التغيير.
  - **الإجراء:** جُمعت المزامنة والحذف في adapter قابل للاختبار ونُقلت إلى thread pool؛ لم أضف outbox/إعادة محاولة دائمة لأن ذلك تغيير معماري يحتاج تخزينًا وسياسة استرداد. يلزم اختبار هذه المزامنة على PostgreSQL فعليًا.

## MEDIUM

- **التحقق السابق من بعض ملفات Office كان يقبل أي محتوى غير فارغ.**
  - **الملف:** `app/webapp/admin_api.py`
  - **الإصلاح:** صار DOCX/PPTX/XLSX يتطلب حاوية ZIP وأجزاء OOXML المتوقعة، ويُتحقق من UTF-8 للملفات النصية؛ أضيف اختبار لرفض DOCX مزيف.

- **مراجعة كود AI كانت تستهلك الحصة قبل فحص طول الكود، ولا تعيدها إذا فشل Piston قبل المراجعة.**
  - **الملف:** `app/ai/service.py`
  - **الإصلاح:** نقل فحص الطول قبل حجز الحصة وإرجاعها عند فشل تنفيذ Piston.

- **قد يفقد المستخدم تذكير ذلك اليوم عند فشل الإرسال بعد claim ناجح.**
  - **الملفات:** `main.py`, `app/storage/postgres.py`
  - **الحالة:** بقي سلوك at-most-once لتجنب التكرار إذا قبل Telegram الرسالة ثم انقطع الرد؛ معالجة إعادة التسليم بأمان تحتاج سياسة lease/outbox.

- **إعداد Production لم يكن يرفض بعض القيم المعيبة قبل الاتصال.**
  - **الملف:** `config.py`
  - **الإصلاح:** صار التحقق fail-fast لصيغة `ADMIN_IDS`، وقيود Telegram webhook secret، ومخططات PostgreSQL/Redis، وإعداد OpenAI عند تفعيله. لم تتغير أسماء المتغيرات الحالية.

- **اكتُشف اعتماد اختبارات Admin API على مخزن PostgreSQL الحقيقي رغم استخدامها قاعدة SQLite اختبارية.**
  - **الملفات:** `tests/test_admin_api.py`, `app/webapp/admin_api.py`, `tests/test_runtime_reliability.py`
  - **الإصلاح:** عُزل adapter في الاختبارات وأضيف اختبار مستقل لنداءات مزامنة/حذف الدروس وتحديث الكتالوج؛ لم تعد الاختبارات تحتاج اتصالًا بقاعدة إنتاج.

- **سجلات فشل الدفع كانت تتضمن `invoice_payload` الذي يحمل Telegram user ID.**
  - **الملف:** `app/bot/routers/start.py`
  - **الإصلاح:** حذف payload الخام من extras المرسلة إلى Sentry.

## VERIFIED

- `python -m compileall -q .`: نجح.
- `pytest -q -W error`: **25 passed** بلا تحذيرات.
- `node --check app/webapp/static/admin/assets/admin.js`: نجح.
- `pip check`: لا توجد اعتماديات مكسورة.
- استيراد الوحدات الأساسية، بما فيها `config`, `main`, `admin_api`, نماذج المحتوى/RBAC وOpenAI provider: نجح دون اتصال بالخدمات. حزمة Replit App Storage ثبتت واستوردت في بيئة Python 3.12.
- `.replit` صالح كـTOML، ويحدد Python 3.12 و`python main.py` وDeployment من نوع Cloud Run على المنفذ 8080.
- سلسلة Alembic تصل إلى head `20260927_03`؛ `alembic upgrade head --sql` أنتج SQL PostgreSQL offline بنجاح مع bootstrap لـ`ADMIN_IDS`.
- اختبارات App Storage تستخدم mock محليًا لتأكيد upload/download وعدم اعتماد التنزيل على ملف محلي؛ لم تتصل بـbucket فعلي.
- لم يُعثر على ملف `.env` أو ملف مفتاح خاص أو نمط token صريح ضمن ملفات المصدر التي فُحصت.
- فحوص RBAC وAPI وإعدادات webhook/uploads والتخزين الذري للتذكير اختُبرت محليًا ضمن suite.

## UNVERIFIED

- لم تتوفر `BOT_TOKEN`, `DATABASE_URL`, `REDIS_URL`, `WEBHOOK_SECRET`, `WEBHOOK_URL`, أو `ADMIN_IDS` خاصة بالمشروع؛ لم يُشغّل startup على Telegram أو خدمات Production.
- **PostgreSQL:** توليد SQL فقط؛ لم يُنفّذ migration online أو `SELECT 1` على قاعدة جديدة/قديمة.
- **Redis:** لم يُختبر ping أو FSM فعليًا.
- **Telegram:** لم يُختبر `getMe` أو استقبال webhook أو callbacks/Stars، ولم يُضبط webhook خارجي.
- **Replit App Storage:** يلزم bucket في مشروع Replit؛ اختبارات SDK كانت mocks، فلا أؤكد استمرار الملفات حتى إتمام اختبار upload ثم redeploy في حساب Replit.
- **OpenAI/Piston:** لم يُجرَ طلب حي من مفاتيح المشروع. AI معطل افتراضيًا؛ وجود نموذج افتراضي في الكود لا يثبت سماح حساب Replit باستعماله.
- **واجهة Admin في متصفح Replit:** فحص syntax وAPI اختباري، لا يوجد اختبار بصري/e2e بعد النشر.
- **الشهادة مجانية؛ لا توجد فحوص دفع أو بطاقة لإصدارها. يحتاج الاختبار الفعلي فقط إلى Telegram وBot Token.

## إعدادات النشر المطلوبة

اتبع `REPLIT_SETUP.md`: أضف Secrets للخدمات المذكورة، وأنشئ App Storage bucket، واجعل `CONTENT_STORAGE_BACKEND=replit`. endpoint `/healthz` الحالي فحص حيوية HTTP فقط؛ لا يثبت جاهزية PostgreSQL أو Redis.

مرجع التخزين الرسمي: [Replit App Storage](https://docs.replit.com/features/data-and-storage/object-storage) و[Python SDK](https://docs.replit.com/features/sdks/object-storage-python-sdk).
