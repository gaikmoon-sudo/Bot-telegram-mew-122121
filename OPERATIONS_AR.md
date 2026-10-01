# تشغيل أكاديمية Telegram بشكل دائم

## الوضع الموصى به

للتشغيل المستمر 24/7، استخدم خادم VPS ثابتًا مع Docker Compose، ويفضل أن يكون خلف Reverse Proxy مثل Caddy أو Nginx لتوفير HTTPS. شغّل PostgreSQL وRedis والبوت داخل Compose، واجعل البوت يتصل بالإنترنت عبر الشبكة العامة بينما تبقى قاعدة البيانات وRedis على الشبكة الداخلية.

### التشغيل

1. انسخ `.env.permanent.example` إلى `.env`.
2. ضع `BOT_TOKEN` و`ADMIN_IDS` وكلمات مرور PostgreSQL وRedis.
3. ضع `WEBHOOK_URL` كعنوان HTTPS العام مع المسار `/telegram/webhook`.
4. اجعل `WEBHOOK_SECRET` قيمة عشوائية قوية.
5. شغّل:

```bash
docker compose -f docker-compose.permanent.yml up -d --build
```

6. راقب الحالة:

```bash
docker compose -f docker-compose.permanent.yml ps
docker compose -f docker-compose.permanent.yml logs -f bot
```

7. فحص الصحة:

```bash
curl https://YOUR_DOMAIN/healthz
curl https://YOUR_DOMAIN/readyz
```

## التشغيل المستمر

`restart: unless-stopped` وDocker init وHealthcheck موجودة في الصورة. لذلك يعاد تشغيل البوت بعد الخروج أو إعادة تشغيل الخادم، مع الاحتفاظ ببيانات PostgreSQL وRedis داخل volumes.

## الشهادة مجانية

إصدار الشهادة بعد إكمال المسار مجاني بالكامل. الإصدار الحالي لا يرسل Telegram Invoice ولا يستخدم Telegram Stars ولا يطلب رقم بطاقة أو وسيلة دفع من الطالب.

جدول الدفع القديم موجود فقط للتوافق مع قواعد بيانات الإصدارات السابقة، ولا يوجد مسار تطبيق يستخدمه لإصدار الشهادة.

## النسخ الاحتياطي

خذ نسخة دورية من PostgreSQL والـvolumes. لا تعتمد على نسخة واحدة من قاعدة البيانات أو ملفات `/app/data`.

## ملاحظات مهمة

- لا تضع `.env` داخل Git.
- لا تستخدم `WEBHOOK_URL` غير HTTPS في الإنتاج.
- لا تفتح منافذ PostgreSQL أو Redis للعالم الخارجي.
- إذا كان الهدف تجربة مجانية فقط، يمكن تشغيل المشروع محليًا أو على بيئة تطوير؛ أما 24/7 الموثوق فيحتاج بيئة استضافة دائمة.
