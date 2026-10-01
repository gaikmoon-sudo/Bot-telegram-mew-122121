# Backup and Rollback Notes

## SESSION 01 — Baseline & Safety

**Date:** 2026-09-27  
**Scope:** Baseline checks فقط. لم يتم تعديل Database أو Redis أو Webhook أو AI/Piston/Payments أو أي feature.

## Current state

تم إجراء إصلاح baseline واحد فقط في SESSION 01: تصحيح import `Bot` من `aiogram.types` إلى `aiogram` في `app/bot/routers/start.py`. هذا إصلاح توافق ضروري يمنع import الكامل، ولا يغير منطق أي feature أو إعداد اتصال.

الملفات الجديدة/المعدلة في هذه الجلسة:

- `app/bot/routers/start.py` — baseline import fix.
- `BACKUP_AND_ROLLBACK.md`.
- `V7_PROGRESS.md`.

تم حذف `__pycache__` المولدة بعد compile checks حتى لا تدخل ضمن حالة المشروع أو أي حزمة لاحقة.

## Critical-file checksums after baseline fix

```text
292fd4ee6cacbbe8db64fc64ae1e847ae5cdc59ffcfd9d2b72830c92d461678b  main.py
f9dedddb6067c2c94e5c17ec0e84f77ad83d816d781d0b6e79fef40d1c35a3fa  config.py
1073b53d787f1c228895e320bc31ce9cd01cb5f0c271b35788f53b1e06b365d4  app/storage/postgres.py
f42184ef45f35ef2ae4bdb106e46f285d8ff44db17954a3931bf9d22bb6e36f4  app/bot/fsm.py
f2e5fbdd59250b6098d70f5f63e0d60e21bdc5caa5c9ed1f75400378025c2b5f  app/webapp/piston.py
a561d29d7936eadb4122034f9c56f91609663c67b55b73fbcf239dbd013127c4  app/ai/service.py
a3252929c50afdc5afe0e494ac63e5ef4818c7cc5c5f8fe971f335a3e4c19cf8  app/bot/routers/start.py
980663bf65b9e8d2328c83e3333ae272fb90a2c6363c9433866c5e95502bf343  docker-compose.yml
c37ad37295842a4fd34b50aa826f0f5adc1ddd15c690e6510f792345de81c2d8  .env.example
```

## Rollback procedure

إذا كان المطلوب إزالة إصلاح baseline فقط، أعد import `Bot` إلى حالة ما قبل الجلسة، مع العلم أن ذلك سيعيد خطأ `ImportError` مع aiogram الحالي. الأفضل الاحتفاظ بالإصلاح لأنه ضروري للتشغيل.

لإزالة مخرجات التوثيق فقط:

```bash
rm -f BACKUP_AND_ROLLBACK.md V7_PROGRESS.md
```

لا تحذف `data/academy.sqlite3`، ولا تعكس أي جداول PostgreSQL أو Redis يدوياً؛ لم يتم لمسها في هذه الجلسة.

## Before future sessions

قبل أي جلسة تعديلية لاحقة:

1. خذ نسخة PostgreSQL عبر أداة المزود أو `pg_dump`.
2. خذ نسخة Redis وفق سياسة المزود إذا كانت بيانات FSM/cache مهمة.
3. احفظ نسخة من `.env` خارج المستودع بطريقة آمنة، ولا تضعها في Git.
4. خزّن checksums أو commit واضحاً قبل التعديل.
5. نفّذ migrations في بيئة staging أولاً.

## Baseline limitations

- pytest الرسمي نجح بعد تثبيت dependencies في venv مؤقت خارج المشروع.
- compileall نجح.
- startup الكامل لم يُشغّل لأن probe الآمن لا يحتوي `DATABASE_URL` ولا يجب أن يتصل بProduction.
- لا يوجد حالياً اختبار اتصال فعلي بـPostgreSQL أو Redis أو Telegram Webhook.

## SESSION 02 changes

تم توحيد environment configuration في `config.py`، مع إبقاء كل قيم الاتصال والأسرار خارج الكود. استُبدلت القراءات المباشرة في الوحدات التشغيلية باستخدام `settings`، ولم يتغير schema أو سلوك الاتصال نفسه.

للتراجع عن SESSION 02، أعد الملفات التالية إلى نسخها السابقة من commit/backup قبل الجلسة:

```text
config.py
main.py
app/webapp/api.py
app/webapp/piston.py
app/ai/service.py
app/ai/provider.py
app/storage/postgres.py
infrastructure/redis/connection.py
app/bot/routers/start.py
```

بصمات SESSION 02 الحالية محفوظة في سجل الجلسة، ويمكن إعادة حسابها عبر:

```bash
sha256sum config.py main.py app/webapp/api.py app/webapp/piston.py \
  app/ai/service.py app/ai/provider.py app/storage/postgres.py \
  infrastructure/redis/connection.py app/bot/routers/start.py
```

قبل SESSION 03 يجب أخذ backup فعلي لـPostgreSQL وRedis في بيئة staging، لأن SESSION 03 ستراجع migrations/schema فقط.
