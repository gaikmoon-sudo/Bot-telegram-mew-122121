# نشر Telegram Educational Bot على Replit

## 1. إعداد المشروع

استورد المشروع إلى Replit. يشغّل `.replit` التطبيق بواسطة `python main.py` على المنفذ `8080` وبـPython 3.12؛ إصدار 3.12 مقصود لأن حزمة Replit App Storage الرسمية تتطلب Python أصغر من 3.13.

## 2. إعداد App Storage للملفات

ملفات Deployment المحلية ليست تخزينًا دائمًا، لذا يعتمد رفع الملفات في لوحة الإدارة على **Replit App Storage** افتراضيًا:

1. من أدوات المشروع افتح **App Storage** وأنشئ bucket للمشروع.
2. اجعله bucket الافتراضي، أو انسخ Bucket ID وضعه في `APP_STORAGE_BUCKET_ID`.
3. أضف Secret `CONTENT_STORAGE_BACKEND=replit`.
4. لا تضبط `CONTENT_STORAGE_BACKEND=local` في Production؛ هذا الخيار للتطوير والاختبارات فقط.

يعتمد التطبيق SDK الرسمي `replit.object-storage`. يعمل الرفع والتنزيل إلى App Storage عبر thread pool حتى لا يحجبا حلقة asyncio. إنشاء bucket وربطه بحساب Replit خطوة خارج هذا الأرشيف ويجب إكمالها قبل استخدام ميزة رفع الملفات.

## 3. Secrets وخدمات التشغيل الإلزامية

أضف القيم التالية من **Secrets** في Replit؛ لا تضع أسرارًا داخل الكود أو Git:

```text
BOT_TOKEN=<Telegram bot token>
ADMIN_IDS=<comma-separated numeric Telegram user IDs>
DATABASE_URL=<PostgreSQL connection URL>
REDIS_URL=<Redis connection URL>
WEBHOOK_SECRET=<1-256 chars: A-Z a-z 0-9 _ ->
WEBHOOK_URL=https://<public-deployment-host>/telegram/webhook
CONTENT_STORAGE_BACKEND=replit
```

يمكن ترك `APP_STORAGE_BUCKET_ID` فارغًا عند استخدام bucket الافتراضي. `WEBHOOK_PATH` افتراضيه `/telegram/webhook`، والمنفذ الافتراضي `8080`. يمكن تحديد `WEBHOOK_URL` يدويًا؛ يدعم التطبيق كذلك fallback إلى `REPLIT_APP_DOMAIN` عند توفره. لا تعتبر قاعدة البيانات أو Redis متصلين لمجرد وجود Secrets؛ تحقق من السجلات بعد التشغيل.

## 4. الإقلاع والترحيلات

شغّل Deployment بملف `.replit`. قبل بدء البوت، يتحقق `main.py` من إعداد Production ويشغّل `alembic upgrade head` ثم يهيّئ مخازن التشغيل وRedis وwebhook. لا تشغّل `main.py` بالتوازي مع أمر migration يدوي أثناء الإقلاع.

تحقق من السجلات بحثًا عن رسائل بدء HTTP والبوت واكتمال migration. اختبر `/healthz` ثم افتح البوت في Telegram ونفّذ `/start`. endpoint الصحي يثبت حيوية HTTP فقط، وليس نجاح الاتصال الفعلي بكل خدمة.

## 5. Web App وAI وIDE

- `WEB_APP_URL`: رابط HTTPS العام للوحة الويب/IDE إن كانت الميزة مستخدمة.
- اترك `AI_ENABLED=false` حتى تضيف `OPENAI_API_KEY` إلى Secrets؛ فعّل AI بعدها واضبط `AI_PROVIDER=openai` و`AI_MODEL` إذا لزم.
- خدمة IDE تنفّذ الشيفرة عبر Piston باستخدام `PISTON_API_URL`؛ مفتاح `PISTON_API_KEY` اختياري وفق مزود Piston.
- إصدار الشهادة مجاني ولا توجد عملية دفع أو بطاقة مطلوبة من المستخدم.

## 6. فحص ما بعد النشر

1. تحقق من migration وHTTP startup في Replit Logs.
2. أرسل `/start`، وافحص التسجيل والموافقة على الخصوصية وفتح درس.
3. اختبر FSM مع Redis، وIDE/Piston، وAI بعد تفعيله.
4. من لوحة الإدارة ارفع ملفًا، ثم أعد تنزيله بعد إعادة نشر Deployment للتأكد من بقائه في App Storage.
5. اختبر صلاحيات الأدوار، تحرير/نشر درس ومزامنته مع البوت، وTelegram webhook وcallback queries.
6. لا تختبر Telegram/PostgreSQL/Redis/OpenAI/Stars كتجارب ناجحة حتى تنفذها على خدمات Production الفعلية.
