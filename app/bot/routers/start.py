from __future__ import annotations

import asyncio
from html import escape
from pathlib import Path
from urllib.parse import urlparse

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message, PollAnswer, WebAppInfo

from app.storage.postgres import store
from config import settings

router = Router(name="academy_router")
PRIVACY_VERSION = "1.0"
WELCOME_IMAGE = Path(__file__).resolve().parents[3] / "assets" / "welcome.png"


def kb(rows):
    return InlineKeyboardMarkup(inline_keyboard=rows)


def lrm(text: str) -> str:
    return f"\u200e{text}\u200e"


def rtl(text: str) -> str:
    return f"\u200f{text}\u200f"


def profile_text(profile: dict) -> str:
    uni = profile.get("university") or "غير محددة"
    dept = profile.get("department") or "غير محدد"
    return (
        "👤 <b>مراجعة ملفك التعليمي</b>\n\n"
        f"👨‍🎓 الاسم الكامل: <b>{escape(str(profile['full_name']))}</b>\n"
        f"🎂 العمر: <b>{profile['age']}</b> سنة\n"
        f"🏛️ الجامعة: <b>{escape(str(uni))}</b>\n"
        f"📚 القسم: <b>{escape(str(dept))}</b>\n"
        f"🎓 المستوى: <b>{escape(str(profile['level']))}</b>\n\n"
        "🔐 تم حفظ البيانات بعد موافقتك على سياسة الخصوصية."
    )


def welcome_after_registration(profile: dict) -> str:
    return (
        f"🎓 <b>أهلًا بك يا {escape(str(profile['full_name']))}!</b>\n\n"
        "تم إنشاء ملفك التعليمي بنجاح. 🚀\n\n"
        "ابدأ بمسار C++ الحالي، وسيُحفظ تقدمك تلقائيًا.\n\n"
        "اختر ما تريد فعله الآن:"
    )


WELCOME_TEXT = (
    "🎓 <b>أكاديمية التقنية والأمن السيبراني</b>\n\n"
    "👋 أهلاً بك في منصتك التعليمية.\n\n"
    "🚀 تعلّم البرمجة وتقنية المعلومات\n"
    "🛡️ تعلّم الأمن السيبراني والاختبار الأخلاقي\n"
    "🧠 طبّق ما تتعلمه واختبر معرفتك\n\n"
    "اختر المجال الذي تريد البدء فيه:"
)


def get_main_menu_kb():
    return kb([
        [InlineKeyboardButton(text="▶️ أكمل من حيث توقفت", callback_data="continue_learning")],
        [ide_button(1, "💻 مختبر البرمجة — IDE + Terminal")],
        [InlineKeyboardButton(text="🤖 المعلم الذكي — AI Academy", callback_data="ai:menu")],
        [InlineKeyboardButton(text="💻 تكنولوجيا المعلومات", callback_data="it_menu")],
        [InlineKeyboardButton(text="🛡️ الأمن السيبراني", callback_data="cyber_menu")],
        [InlineKeyboardButton(text="📚 دوراتي", callback_data="my_courses"), InlineKeyboardButton(text="📊 لوحة التعلم", callback_data="dashboard")],
        [InlineKeyboardButton(text="🏆 الإنجازات", callback_data="achievements"), InlineKeyboardButton(text="👤 حسابي", callback_data="profile")],
        [InlineKeyboardButton(text="🔖 المحفوظات", callback_data="favorites"), InlineKeyboardButton(text="ℹ️ حول الأكاديمية", callback_data="about")],
        [InlineKeyboardButton(text="📞 التواصل مع المندوب", callback_data="contact:representative")],
        [InlineKeyboardButton(text="🛠️ التواصل مع المطور والأدمن", callback_data="contact:developer")],
        [InlineKeyboardButton(text="💬 اقتراحات أو شكوى", callback_data="contact:feedback")],
    ])


def get_it_menu_kb():
    return kb([
        [InlineKeyboardButton(text="⭐ مسار C++ الأساسي", callback_data="cpp_menu")],
        [InlineKeyboardButton(text="🇬🇧 اللغة الإنجليزية", callback_data="it_subject:english"), InlineKeyboardButton(text="➗ رياضيات متقطعة", callback_data="it_subject:discrete_math")],
        [InlineKeyboardButton(text="📐 رياضيات", callback_data="it_subject:math"), InlineKeyboardButton(text="💻 مهارات الحاسوب", callback_data="it_subject:computer_skills")],
        [InlineKeyboardButton(text="🐍 Python 🔔", callback_data="notify:python"), InlineKeyboardButton(text="🌐 تطوير الويب 🔔", callback_data="notify:web")],
        [InlineKeyboardButton(text="🗄️ قواعد البيانات 🔔", callback_data="notify:database"), InlineKeyboardButton(text="🐧 أنظمة التشغيل 🔔", callback_data="notify:os")],
        [InlineKeyboardButton(text="🌐 الشبكات 🔔", callback_data="notify:networking"), InlineKeyboardButton(text="🔧 أدوات المطورين 🔔", callback_data="notify:devtools")],
        [InlineKeyboardButton(text="🧩 المشاريع العملية 🔔", callback_data="notify:projects")],
        [InlineKeyboardButton(text="🔙 القائمة الرئيسية", callback_data="main_menu")],
    ])


def get_cyber_menu_kb():
    return kb([
        [InlineKeyboardButton(text="🔰 أساسيات الأمن السيبراني 🔔", callback_data="notify:cyber_fundamentals")],
        [InlineKeyboardButton(text="🎯 الاختبار الأخلاقي Ethical Hacking", callback_data="ethical_hacking")],
        [InlineKeyboardButton(text="🌐 أمن الشبكات 🔔", callback_data="notify:network_security"), InlineKeyboardButton(text="🐧 Linux Security 🔔", callback_data="notify:linux_security")],
        [InlineKeyboardButton(text="🌍 أمن تطبيقات الويب 🔔", callback_data="notify:web_security"), InlineKeyboardButton(text="🔐 التشفير 🔔", callback_data="notify:cryptography")],
        [InlineKeyboardButton(text="🔎 التحليل الرقمي 🔔", callback_data="notify:forensics"), InlineKeyboardButton(text="🧪 المختبرات التدريبية 🔔", callback_data="notify:labs")],
        [InlineKeyboardButton(text="🏆 المسار النهائي 🔔", callback_data="notify:cyber_final")],
        [InlineKeyboardButton(text="🔙 القائمة الرئيسية", callback_data="main_menu")],
    ])


def get_cyber_placeholder_kb():
    return kb([
        [InlineKeyboardButton(text="🔔 أعلمني عند توفر الوحدات", callback_data="notify:cyber_units")],
        [InlineKeyboardButton(text="🔔 أعلمني عند توفر الفيديوهات", callback_data="notify:cyber_videos")],
        [InlineKeyboardButton(text="🔔 أعلمني عند توفر المختبر", callback_data="notify:cyber_lab")],
        [InlineKeyboardButton(text="🔔 أعلمني عند توفر الاختبار", callback_data="notify:cyber_quiz")],
        [InlineKeyboardButton(text="🔙 الأمن السيبراني", callback_data="cyber_menu")],
    ])


def get_ethical_hacking_kb():
    return kb([
        [InlineKeyboardButton(text="1️⃣ مقدمة الاختبار الأخلاقي 🔔", callback_data="notify:ethical_intro")],
        [InlineKeyboardButton(text="2️⃣ منهجية الاختبار الأمني 🔔", callback_data="notify:ethical_methodology")],
        [InlineKeyboardButton(text="3️⃣ الاستطلاع وجمع المعلومات 🔔", callback_data="notify:ethical_recon")],
        [InlineKeyboardButton(text="4️⃣ تحليل الشبكات 🔔", callback_data="notify:ethical_networks")],
        [InlineKeyboardButton(text="5️⃣ أمن تطبيقات الويب 🔔", callback_data="notify:ethical_web")],
        [InlineKeyboardButton(text="6️⃣ التقارير والمعالجة 🔔", callback_data="notify:ethical_reports")],
        [InlineKeyboardButton(text="🧪 مختبرات قانونية معزولة 🔔", callback_data="notify:ethical_labs")],
        [InlineKeyboardButton(text="🏆 اختبار المسار 🔔", callback_data="notify:ethical_final")],
        [InlineKeyboardButton(text="🔙 الأمن السيبراني", callback_data="cyber_menu")],
    ])


def get_cpp_menu_kb():
    return kb([
        [InlineKeyboardButton(text="🟢 المستوى الأول — المبتدئ", callback_data="cpp_beginner")],
        [InlineKeyboardButton(text="🟡 المستوى الثاني — المتوسط 🔔", callback_data="notify:cpp_intermediate")],
        [InlineKeyboardButton(text="🔴 المستوى الثالث — المتقدم 🔔", callback_data="notify:cpp_advanced")],
        [InlineKeyboardButton(text="🚀 المشاريع العملية 🔔", callback_data="notify:cpp_projects")],
        [InlineKeyboardButton(text="📊 تقدمي في C++", callback_data="cpp_progress"), InlineKeyboardButton(text="📝 اختبار C++", callback_data="course_cpp_quiz")],
        [InlineKeyboardButton(text="🔙 تكنولوجيا المعلومات", callback_data="it_menu")],
    ])

# V6 content catalog: editable JSON instead of hard-coded lesson definitions.
CONTENT_FILE = Path(__file__).resolve().parents[3] / "content" / "cpp_beginner.json"

def _load_lessons() -> dict[int, dict]:
    import json
    try:
        payload = json.loads(CONTENT_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Unable to load course content: {CONTENT_FILE}: {exc}") from exc
    return {int(k): v for k, v in payload.items()}

LESSONS = _load_lessons()

def normalize_custom_code(raw: str) -> str:
    raw = raw or ""
    if not raw.strip():
        return ""
    if raw.lstrip().startswith("<pre><code"):
        return raw
    return f'<pre><code class="language-cpp">{escape(raw)}</code></pre>'


CORE_LESSON_IDS = list(range(1, 14))

def refresh_runtime_lessons() -> None:
    """Refresh the in-memory catalog after Admin Panel content changes.

    Core lessons always come from the versioned JSON file. Published admin lessons
    are mirrored from PostgreSQL and replace only the custom portion of the catalog.
    The dict is mutated in place so dashboard.py's imported LESSONS reference stays valid.
    """
    latest = _load_lessons()
    for custom in store.custom_lessons():
        latest[1000 + int(custom["id"])] = {
            "title": escape(str(custom["title"])),
            "duration": escape(str(custom["duration"])),
            "objective": escape(str(custom["objective"])),
            "theory": escape(custom["theory"]),
            "simple": "",
            "code": normalize_custom_code(custom["code"]),
            "examples": escape(custom["examples"]),
            "question": None,
            "answers": [],
            "explain": "",
        }
    LESSONS.clear()
    LESSONS.update(latest)


LESSONS = _load_lessons()
refresh_runtime_lessons()


class Registration(StatesGroup):
    full_name = State(); age = State(); university = State(); department = State(); level = State(); privacy = State(); confirmation = State()


class AdminStates(StatesGroup):
    broadcast = State(); lesson_title = State(); lesson_duration = State(); lesson_objective = State(); lesson_theory = State(); lesson_code = State(); lesson_examples = State()


class ContactStates(StatesGroup):
    complaint = State()


def registration_cancel_kb():
    return kb([[InlineKeyboardButton(text="❌ إلغاء التسجيل", callback_data="registration_cancel")]])


def level_kb():
    return kb([
        [InlineKeyboardButton(text="1️⃣ السنة الأولى", callback_data="reg_level:1"), InlineKeyboardButton(text="2️⃣ السنة الثانية", callback_data="reg_level:2")],
        [InlineKeyboardButton(text="3️⃣ السنة الثالثة", callback_data="reg_level:3"), InlineKeyboardButton(text="4️⃣ السنة الرابعة", callback_data="reg_level:4")],
        [InlineKeyboardButton(text="5️⃣ سنة خامسة أو أكثر", callback_data="reg_level:5+")],
        [InlineKeyboardButton(text="🎓 دراسات عليا", callback_data="reg_level:postgraduate")],
        [InlineKeyboardButton(text="❌ إلغاء التسجيل", callback_data="registration_cancel")],
    ])


def profile_confirmation_kb():
    return kb([
        [InlineKeyboardButton(text="✅ تأكيد البيانات", callback_data="registration_confirm")],
        [InlineKeyboardButton(text="✏️ إعادة التسجيل / تعديل", callback_data="registration_restart")],
        [InlineKeyboardButton(text="❌ إلغاء", callback_data="registration_cancel")],
    ])


def privacy_kb():
    return kb([
        [InlineKeyboardButton(text="🔐 قراءة سياسة الخصوصية", callback_data="privacy")],
        [InlineKeyboardButton(text="✅ أوافق وأتابع", callback_data="privacy_accept")],
        [InlineKeyboardButton(text="❌ لا أوافق", callback_data="privacy_decline")],
    ])


def is_completed(user_id: int, lesson_id: int) -> bool:
    return store.is_completed(user_id, lesson_id)


def get_cpp_beginner_kb(user_id: int | None = None):
    rows = []
    for lesson_id in CORE_LESSON_IDS:
        lesson = LESSONS[lesson_id]
        done = " ✅" if user_id is not None and is_completed(user_id, lesson_id) else ""
        rows.append([InlineKeyboardButton(text=f"{lesson_id:02d} — {lesson['title']}{done}", callback_data=f"cpp_lesson:{lesson_id}")])
    custom_ids = [i for i in LESSONS if i not in CORE_LESSON_IDS]
    if custom_ids:
        rows.append([InlineKeyboardButton(text="🆕 دروس مضافة حديثًا", callback_data="custom_lessons")])
    rows += [[InlineKeyboardButton(text="📝 اختبار المستوى", callback_data="course_cpp_quiz")], [InlineKeyboardButton(text="🔙 مسار C++", callback_data="cpp_menu")]]
    return kb(rows)




def _public_webapp_base() -> str:
    candidates = [
        settings.web_app_url,
        settings.replit_app_domain,
        settings.replit_dev_domain,
    ]
    for value in candidates:
        value = value.strip().rstrip("/")
        if not value:
            continue
        if not value.startswith(("https://", "http://")):
            value = "https://" + value
        if value.startswith("http://") and settings.environment.lower().startswith("production"):
            continue
        return value
    return ""


def ide_button(lesson_id: int, text: str = "💻 افتح IDE + Terminal"):
    base = _public_webapp_base()
    if not base:
        return InlineKeyboardButton(text="⚙️ إعداد بيئة البرمجة", callback_data="ide_setup")
    return InlineKeyboardButton(text=text, web_app=WebAppInfo(url=f"{base}/webapp?lesson={lesson_id}"))

def get_lesson_kb(lesson_id: int):
    rows = [
        [InlineKeyboardButton(text="📖 الشرح النظري", callback_data=f"cpp_theory:{lesson_id}"), InlineKeyboardButton(text="💡 شرح مبسط", callback_data=f"cpp_simple:{lesson_id}")],
        [InlineKeyboardButton(text="💻 الكود البرمجي", callback_data=f"cpp_code:{lesson_id}")],
        [ide_button(lesson_id)],
        [InlineKeyboardButton(text="🤖 اسأل المعلم عن هذا الدرس", callback_data=f"ai:lesson:{lesson_id}")],
        [InlineKeyboardButton(text="🎥 الفيديو التعليمي 🔔", callback_data="notify:lesson_video")],
        [InlineKeyboardButton(text="🧠 أمثلة عملية", callback_data=f"cpp_examples:{lesson_id}")],
    ]
    if LESSONS[lesson_id].get("answers"):
        rows.append([InlineKeyboardButton(text="📝 اختبار الدرس", callback_data=f"cpp_quiz:{lesson_id}")])
    rows += [
        [InlineKeyboardButton(text="🔖 إضافة/إزالة من المحفوظات", callback_data=f"favorite:{lesson_id}")],
        [InlineKeyboardButton(text="⬅️ السابق", callback_data=f"lesson_prev:{lesson_id}"), InlineKeyboardButton(text="التالي ➡️", callback_data=f"lesson_next:{lesson_id}")],
        [InlineKeyboardButton(text="✅ تحديد الدرس كمكتمل", callback_data=f"cpp_complete:{lesson_id}")],
        [InlineKeyboardButton(text="🔙 المستوى الأول", callback_data="cpp_beginner")],
    ]
    return kb(rows)


def get_back_lesson_kb(lesson_id: int):
    return kb([[InlineKeyboardButton(text="🔙 العودة إلى الدرس", callback_data=f"cpp_lesson:{lesson_id}")]])


def quiz_questions(lesson_id: int):
    lesson = LESSONS[lesson_id]
    original = [{"question": lesson["question"], "options": [a[1] for a in lesson["answers"]], "correct": next(i for i,a in enumerate(lesson["answers"]) if a[2]), "explanation": lesson["explain"]}]
    objective = lesson["objective"]
    title = lesson["title"]
    q2 = {"question": "ما الهدف الأساسي من هذا الدرس؟", "options": [objective, "تصميم واجهة Telegram", "إدارة قواعد بيانات المستخدمين", "إعداد خادم ويب"], "correct": 0, "explanation": f"الهدف المعلن للدرس هو: {objective}"}
    q3 = {"question": "أي موضوع يرتبط مباشرة بهذا الدرس؟", "options": [title, "إدارة الإعلانات", "تصميم الشعارات", "إدارة البريد الإلكتروني"], "correct": 0, "explanation": f"هذا الاختبار مرتبط بالدرس: {title}."}
    return original + [q2, q3]


async def send_quiz_question(bot, chat_id: int, attempt_id: str, lesson_id: int, index: int):
    questions = quiz_questions(lesson_id)
    q = questions[index]
    poll = await bot.send_poll(chat_id=chat_id, question=f"📝 السؤال {index+1}/{len(questions)}\n\n{q['question']}", options=q["options"], type="quiz", correct_option_id=q["correct"], is_anonymous=False, explanation=q["explanation"], allows_multiple_answers=False)
    store.register_poll(poll.poll.id, attempt_id, index, chat_id)


async def start_lesson_quiz(callback: CallbackQuery, lesson_id: int):
    attempt_id = store.create_quiz_attempt(callback.from_user.id, lesson_id, len(quiz_questions(lesson_id)))
    await callback.message.edit_text(
        f"📝 <b>اختبار الدرس {lesson_id:02d}</b>\n\nسيظهر الاختبار في رسائل متتالية. اختر إجابة واحدة لكل سؤال، وستظهر النتيجة النهائية بعد آخر سؤال.",
        reply_markup=kb([[ide_button(lesson_id, "💻 افتح IDE للتطبيق قبل الاختبار")]])
    )
    await send_quiz_question(callback.bot, callback.from_user.id, attempt_id, lesson_id, 0)
    await callback.answer()


@router.message(CommandStart())
async def command_start_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id
    await state.clear()
    profile = store.get_profile(user_id)
    if profile:
        store.touch_activity(user_id)
        await message.answer(welcome_after_registration(profile), reply_markup=get_main_menu_kb())
        return
    if WELCOME_IMAGE.exists():
        await message.answer_photo(FSInputFile(WELCOME_IMAGE), caption="🎓 <b>أكاديمية التقنية والأمن السيبراني</b>\n\nمنصة تعليمية للبرمجة وتقنية المعلومات والأمن السيبراني.")
    await state.set_state(Registration.full_name)
    await message.answer("🎓 <b>إنشاء ملفك التعليمي</b>\n\nسنطلب الاسم والعمر والمستوى. الجامعة والقسم اختياريان ويمكن تخطيهما.\n\n👤 <b>الخطوة 1 من 5</b>\nأرسل اسمك الكامل:", reply_markup=registration_cancel_kb())


@router.message(Registration.full_name)
async def registration_full_name(message: Message, state: FSMContext):
    name = (message.text or "").strip()
    if len(name) < 3 or len(name) > 80:
        await message.answer("⚠️ يرجى إدخال اسم كامل صحيح (من 3 إلى 80 حرفًا).", reply_markup=registration_cancel_kb()); return
    await state.update_data(full_name=name); await state.set_state(Registration.age)
    await message.answer("🎂 <b>الخطوة 2 من 5</b>\nأرسل عمرك بالأرقام فقط، مثال: <b>20</b>.", reply_markup=registration_cancel_kb())


@router.message(Registration.age)
async def registration_age(message: Message, state: FSMContext):
    raw = (message.text or "").strip()
    if not raw.isdigit() or not 13 <= int(raw) <= 100:
        await message.answer("⚠️ أدخل عمرًا بين 13 و100 سنة بالأرقام فقط.", reply_markup=registration_cancel_kb()); return
    await state.update_data(age=int(raw)); await state.set_state(Registration.university)
    await message.answer("🏛️ <b>الخطوة 3 من 5</b>\nاكتب اسم الجامعة، أو اختر تخطي:", reply_markup=kb([[InlineKeyboardButton(text="⏭️ تخطي", callback_data="reg_skip_university")],[InlineKeyboardButton(text="❌ إلغاء", callback_data="registration_cancel")]]))


@router.message(Registration.university)
async def registration_university(message: Message, state: FSMContext):
    value = (message.text or "").strip()
    if len(value) < 2 or len(value) > 120:
        await message.answer("⚠️ يرجى إدخال اسم الجامعة بشكل واضح أو اختيار تخطي.", reply_markup=registration_cancel_kb()); return
    await state.update_data(university=value); await state.set_state(Registration.department)
    await message.answer("📚 <b>الخطوة 4 من 5</b>\nاكتب القسم/التخصص، أو اختر تخطي:", reply_markup=kb([[InlineKeyboardButton(text="⏭️ تخطي", callback_data="reg_skip_department")],[InlineKeyboardButton(text="❌ إلغاء", callback_data="registration_cancel")]]))


@router.callback_query(F.data == "reg_skip_university", Registration.university)
async def skip_university(callback: CallbackQuery, state: FSMContext):
    await state.update_data(university=None); await state.set_state(Registration.department)
    await callback.message.edit_text("📚 <b>الخطوة 4 من 5</b>\nاكتب القسم/التخصص، أو اختر تخطي:", reply_markup=kb([[InlineKeyboardButton(text="⏭️ تخطي", callback_data="reg_skip_department")],[InlineKeyboardButton(text="❌ إلغاء", callback_data="registration_cancel")]])); await callback.answer()


@router.message(Registration.department)
async def registration_department(message: Message, state: FSMContext):
    value = (message.text or "").strip()
    if len(value) < 2 or len(value) > 120:
        await message.answer("⚠️ أدخل القسم بشكل واضح أو اختر تخطي.", reply_markup=registration_cancel_kb()); return
    await state.update_data(department=value); await state.set_state(Registration.level)
    await message.answer("🎓 <b>الخطوة 5 من 5</b>\nاختر مستواك الدراسي الحالي:", reply_markup=level_kb())


@router.callback_query(F.data == "reg_skip_department", Registration.department)
async def skip_department(callback: CallbackQuery, state: FSMContext):
    await state.update_data(department=None); await state.set_state(Registration.level)
    await callback.message.edit_text("🎓 <b>الخطوة 5 من 5</b>\nاختر مستواك الدراسي الحالي:", reply_markup=level_kb()); await callback.answer()


@router.callback_query(F.data.startswith("reg_level:"), Registration.level)
async def registration_level(callback: CallbackQuery, state: FSMContext):
    code = callback.data.split(":", 1)[1]
    labels = {"1":"السنة الأولى","2":"السنة الثانية","3":"السنة الثالثة","4":"السنة الرابعة","5+":"السنة الخامسة أو أكثر","postgraduate":"دراسات عليا"}
    await state.update_data(level=labels.get(code, code)); data = await state.get_data(); await state.set_state(Registration.privacy)
    await callback.message.edit_text("🔐 <b>الخصوصية والموافقة</b>\n\nسيتم حفظ الاسم والعمر والمستوى، والجامعة والقسم فقط إذا اخترتهما. ستستخدم هذه البيانات لتشغيل الحساب وتخصيص تجربة التعلم.\n\nيمكنك قراءة السياسة ثم الموافقة للمتابعة.", reply_markup=privacy_kb()); await callback.answer()


@router.callback_query(F.data == "privacy")
async def privacy_callback(callback: CallbackQuery):
    await callback.message.answer("🔐 <b>سياسة الخصوصية</b>\n\nنخزن بيانات الملف التعليمي والتقدم والاختبارات والمفضلة والإنجازات لتشغيل الخدمة وتحسين تجربة التعلم. لا تحتاج إلى تقديم الجامعة أو القسم. يمكنك طلب حذف بياناتك في أي وقت عبر /delete_my_data.\n\nالإصدار: " + PRIVACY_VERSION)
    await callback.answer()


@router.callback_query(F.data == "privacy_accept", Registration.privacy)
async def privacy_accept(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Registration.confirmation); data = await state.get_data()
    await callback.message.edit_text(profile_text(data) + "\n\nهل البيانات صحيحة؟", reply_markup=profile_confirmation_kb()); await callback.answer()


@router.callback_query(F.data == "privacy_decline", Registration.privacy)
async def privacy_decline(callback: CallbackQuery, state: FSMContext):
    await state.clear(); await callback.message.edit_text("ℹ️ لم تتم الموافقة، لذلك لم يتم حفظ ملفك. يمكنك البدء لاحقًا عبر /start."); await callback.answer()


@router.callback_query(F.data == "registration_confirm", Registration.confirmation)
async def registration_confirm(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    store.save_profile(callback.from_user.id, callback.from_user.username, {"full_name":data["full_name"],"age":data["age"],"university":data.get("university"),"department":data.get("department"),"level":data["level"]}, privacy_policy_version=PRIVACY_VERSION)
    store.touch_activity(callback.from_user.id); await state.clear()
    await callback.message.edit_text(welcome_after_registration(data), reply_markup=get_main_menu_kb()); await callback.answer("✅ تم حفظ الملف بعد الموافقة.")


@router.callback_query(F.data == "registration_restart")
async def registration_restart(callback: CallbackQuery, state: FSMContext):
    await state.clear(); await state.set_state(Registration.full_name)
    await callback.message.edit_text("✏️ <b>إعادة إنشاء الملف</b>\n\n👤 أرسل اسمك الكامل:", reply_markup=registration_cancel_kb()); await callback.answer()


@router.callback_query(F.data == "registration_cancel")
async def registration_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear(); await callback.message.edit_text("ℹ️ تم إلغاء التسجيل. يمكنك البدء لاحقًا عبر /start."); await callback.answer()


@router.message(Command("privacy"))
async def privacy_command(message: Message):
    await message.answer("🔐 <b>سياسة الخصوصية</b>\n\nنحفظ بيانات الحساب والتقدم والاختبارات والمفضلة والإنجازات لتقديم الخدمة. الجامعة والقسم اختياريان. يمكنك طلب حذف بياناتك عبر /delete_my_data.\n\nالإصدار: " + PRIVACY_VERSION)


@router.message(Command("delete_my_data"))
async def delete_my_data(message: Message):
    await message.answer("🗑 <b>حذف بياناتي</b>\n\nسيؤدي التأكيد إلى حذف ملفك التعليمي وتقدمك واختباراتك ومفضلاتك وإنجازاتك وشهاداتك. هذا الإجراء لا يمكن التراجع عنه.", reply_markup=kb([[InlineKeyboardButton(text="🗑 نعم، احذف بياناتي", callback_data="delete_confirm")],[InlineKeyboardButton(text="❌ إلغاء", callback_data="delete_cancel")]]))


@router.callback_query(F.data == "delete_confirm")
async def delete_confirm(callback: CallbackQuery, state: FSMContext):
    from app.ai.cache import delete_user_cache
    user_id = callback.from_user.id
    deleted = store.delete_user_data(user_id)
    await delete_user_cache(user_id)
    await state.clear()
    await callback.message.edit_text("✅ تم حذف بيانات الحساب التعليمية." if deleted else "ℹ️ لا توجد بيانات محفوظة لهذا الحساب."); await callback.answer()


@router.callback_query(F.data == "delete_cancel")
async def delete_cancel(callback: CallbackQuery):
    await callback.message.edit_text("ℹ️ تم إلغاء عملية الحذف.", reply_markup=get_main_menu_kb()); await callback.answer()




def _contact_url(username: str) -> str | None:
    value = (username or "").strip().lstrip("@")
    return f"https://t.me/{value}" if value else None


@router.callback_query(F.data == "contact:representative")
async def contact_representative(callback: CallbackQuery):
    url = _contact_url(settings.representative_username)
    text = "📞 <b>التواصل مع المندوب</b>\n\nاضغط على الزر أدناه لفتح محادثة المندوب." if url else "📞 لم يتم إعداد حساب المندوب بعد. يرجى التواصل مع الإدارة."
    buttons = [[InlineKeyboardButton(text="📞 فتح محادثة المندوب", url=url)]] if url else []
    buttons.append([InlineKeyboardButton(text="🔙 القائمة الرئيسية", callback_data="main_menu")])
    await callback.message.edit_text(text, reply_markup=kb(buttons)); await callback.answer()


@router.callback_query(F.data == "contact:developer")
async def contact_developer(callback: CallbackQuery):
    url = _contact_url(settings.developer_username) or _contact_url(settings.admin_username)
    text = "🛠️ <b>التواصل مع المطور والأدمن</b>\n\nاضغط على الزر أدناه لبدء التواصل." if url else "🛠️ لم يتم إعداد حساب المطور أو الأدمن بعد. يرجى التواصل مع الإدارة."
    buttons = [[InlineKeyboardButton(text="🛠️ التواصل", url=url)]] if url else []
    buttons.append([InlineKeyboardButton(text="🔙 القائمة الرئيسية", callback_data="main_menu")])
    await callback.message.edit_text(text, reply_markup=kb(buttons)); await callback.answer()


@router.callback_query(F.data == "contact:feedback")
async def contact_feedback(callback: CallbackQuery, state: FSMContext):
    # Direct contact is used here because a Telegram username is available,
    # while sending bot messages requires the numeric Telegram user ID.
    url = _contact_url(settings.admin_username) or _contact_url(settings.developer_username)
    text = (
        "💬 <b>اقتراحات أو شكوى</b>\n\n"
        "اضغط على الزر أدناه للتواصل مباشرة مع الإدارة وإرسال اقتراحك أو شكواك."
        if url else
        "💬 لم يتم إعداد حساب الإدارة بعد. يرجى التواصل مع إدارة البوت."
    )
    buttons = [[InlineKeyboardButton(text="💬 إرسال اقتراح أو شكوى", url=url)]] if url else []
    buttons.append([InlineKeyboardButton(text="🔙 القائمة الرئيسية", callback_data="main_menu")])
    await callback.message.edit_text(text, reply_markup=kb(buttons))
    await callback.answer()

@router.callback_query(F.data == "main_menu")
async def process_main_menu(callback: CallbackQuery):
    await callback.message.edit_text(WELCOME_TEXT, reply_markup=get_main_menu_kb()); await callback.answer()


@router.callback_query(F.data == "about")
async def process_about(callback: CallbackQuery):
    await callback.message.edit_text("ℹ️ <b>عن الأكاديمية</b>\n\nمنصة تعليمية منظمة لتعلم البرمجة وتقنية المعلومات والأمن السيبراني والاختبار الأخلاقي داخل بيئات تدريبية مصرح بها.", reply_markup=kb([[InlineKeyboardButton(text="🔙 القائمة الرئيسية", callback_data="main_menu")]])); await callback.answer()


@router.callback_query(F.data == "it_menu")
async def process_it_menu(callback: CallbackQuery):
    await callback.message.edit_text(
        "💻 <b>تكنولوجيا المعلومات</b>\n\nاختر المادة التي تريد الدخول إليها:",
        reply_markup=get_it_menu_kb(),
    )
    await callback.answer()


IT_SUBJECTS = {
    "english": ("🇬🇧 اللغة الإنجليزية", "ستتم إضافة محتوى اللغة الإنجليزية هنا."),
    "discrete_math": ("➗ رياضيات متقطعة", "ستتم إضافة محتوى الرياضيات المتقطعة هنا."),
    "math": ("📐 رياضيات", "ستتم إضافة محتوى الرياضيات هنا."),
    "computer_skills": ("💻 مهارات الحاسوب", "ستتم إضافة محتوى مهارات الحاسوب هنا."),
}


@router.callback_query(F.data.startswith("it_subject:"))
async def process_it_subject(callback: CallbackQuery):
    key = callback.data.split(":", 1)[1]
    title, description = IT_SUBJECTS.get(key, ("📚 المادة", "هذه المادة غير متاحة حاليًا."))
    await callback.message.edit_text(
        f"<b>{title}</b>\n\n{description}",
        reply_markup=kb([[InlineKeyboardButton(text="🔙 تكنولوجيا المعلومات", callback_data="it_menu")]]),
    )
    await callback.answer()


@router.callback_query(F.data == "cyber_menu")
async def process_cyber_menu(callback: CallbackQuery):
    await callback.message.edit_text("🛡️ <b>الأمن السيبراني</b>\n\nاختر المسار. المسارات غير الجاهزة تسمح لك بتسجيل طلب إشعار بدل عرض صفحة فارغة.", reply_markup=get_cyber_menu_kb()); await callback.answer()


@router.callback_query(F.data == "cyber_fundamentals")
async def cyber_fundamentals(callback: CallbackQuery):
    await callback.answer("⏳ هذا المسار غير جاهز بعد. يمكنك طلب إشعار عند إطلاقه.")


@router.callback_query(F.data == "ethical_hacking")
async def ethical_hacking(callback: CallbackQuery):
    if not store.get_profile(callback.from_user.id):
        await callback.answer("ابدأ بالتسجيل أولًا عبر /start.", show_alert=True); return
    if not (store.get_profile(callback.from_user.id) or {}).get("ethical_hacking_consent"):
        await callback.message.edit_text("🛡️ <b>إقرار الاستخدام المصرّح فقط</b>\n\nهذا المسار تعليمي ومخصص للاختبار الأمني داخل أنظمة تملكها أو تملك تصريحًا صريحًا لاختبارها. لا تستخدم المحتوى ضد أنظمة حقيقية دون إذن.\n\nهل توافق على هذا الشرط قبل الدخول؟", reply_markup=kb([[InlineKeyboardButton(text="✅ أوافق وأدخل المسار", callback_data="ethical_accept")],[InlineKeyboardButton(text="🔙 رجوع", callback_data="cyber_menu")]])); await callback.answer(); return
    await callback.message.edit_text(f"🎯 <b>{lrm('Ethical Hacking')}</b>\n\nالمسار التعليمي مصمم حول المنهجية، التحليل، كتابة التقارير، والمختبرات المعزولة. الوحدات ستظهر تدريجيًا عند جاهزيتها.", reply_markup=get_ethical_hacking_kb()); await callback.answer()


@router.callback_query(F.data == "ethical_accept")
async def ethical_accept(callback: CallbackQuery):
    # Consent is intentionally stored separately from privacy consent.
    store.set_ethical_hacking_consent(callback.from_user.id)
    await callback.message.edit_text(f"🎯 <b>{lrm('Ethical Hacking')}</b>\n\nتم تسجيل الإقرار. يمكنك الآن استعراض هيكل المسار.", reply_markup=get_ethical_hacking_kb()); await callback.answer("✅ تم تسجيل الإقرار.")


@router.callback_query(F.data == "cpp_menu")
async def process_cpp_menu(callback: CallbackQuery):
    await callback.message.edit_text(f"⭐ <b>مسار {lrm('C++')}</b>\n\n📚 المستوى المفعّل حاليًا: المبتدئ\n\nاختر المستوى أو راجع تقدمك.", reply_markup=get_cpp_menu_kb()); await callback.answer()


@router.callback_query(F.data == "cpp_beginner")
async def cpp_beginner(callback: CallbackQuery):
    await callback.message.edit_text("🟢 <b>C++ للمبتدئين</b>\n\n13 درسًا أساسيًا مع اختبارات Poll متتابعة وحفظ دائم للتقدم.", reply_markup=get_cpp_beginner_kb(callback.from_user.id)); await callback.answer()


@router.callback_query(F.data.startswith("cpp_lesson:"))
async def cpp_lesson(callback: CallbackQuery):
    lesson_id = int(callback.data.split(":")[1]); lesson = LESSONS.get(lesson_id)
    if not lesson: await callback.answer("الدرس غير موجود."); return
    store.set_last_lesson(callback.from_user.id, lesson_id); store.touch_activity(callback.from_user.id)
    done = "✅ مكتمل" if is_completed(callback.from_user.id, lesson_id) else "⏳ غير مكتمل"
    text = f"📘 <b>الدرس {lesson_id:02d}: {rtl(lesson['title'])}</b>\n\n⏱️ {lesson['duration']}\n📌 الحالة: {done}\n\n🎯 <b>الهدف:</b>\n{lesson['objective']}"
    await callback.message.edit_text(text, reply_markup=get_lesson_kb(lesson_id)); await callback.answer()


@router.callback_query(F.data.startswith("cpp_theory:"))
async def cpp_theory(callback: CallbackQuery):
    lesson_id = int(callback.data.split(":")[1]); await callback.message.edit_text(f"📖 <b>الشرح النظري — الدرس {lesson_id:02d}</b>\n\n{LESSONS[lesson_id]['theory']}", reply_markup=get_back_lesson_kb(lesson_id)); await callback.answer()


@router.callback_query(F.data.startswith("cpp_simple:"))
async def cpp_simple(callback: CallbackQuery):
    lesson_id = int(callback.data.split(":")[1]); await callback.message.edit_text(f"💡 <b>شرح مبسط — الدرس {lesson_id:02d}</b>\n\n{LESSONS[lesson_id]['simple']}", reply_markup=get_back_lesson_kb(lesson_id)); await callback.answer()


@router.callback_query(F.data.startswith("cpp_code:"))
async def cpp_code(callback: CallbackQuery):
    lesson_id = int(callback.data.split(":")[1]); await callback.message.edit_text(f"💻 <b>الكود البرمجي — الدرس {lesson_id:02d}</b>\n\n{LESSONS[lesson_id]['code']}\n\n🧪 جرّب كتابة المثال بنفسك.", reply_markup=get_back_lesson_kb(lesson_id)); await callback.answer()


@router.callback_query(F.data.startswith("cpp_examples:"))
async def cpp_examples(callback: CallbackQuery):
    lesson_id = int(callback.data.split(":")[1]); await callback.message.edit_text(f"🧠 <b>أمثلة وتمارين — الدرس {lesson_id:02d}</b>\n\n{LESSONS[lesson_id]['examples']}", reply_markup=get_back_lesson_kb(lesson_id)); await callback.answer()


@router.callback_query(F.data == "ide_setup")
async def ide_setup(callback: CallbackQuery):
    await callback.answer("⚙️ أضف WEB_APP_URL في ملف .env لفتح IDE داخل Telegram.", show_alert=True)


@router.callback_query(F.data.startswith("cpp_quiz:"))
async def cpp_quiz(callback: CallbackQuery):
    await start_lesson_quiz(callback, int(callback.data.split(":")[1]))


@router.callback_query(F.data == "course_cpp_quiz")
async def course_cpp_quiz(callback: CallbackQuery):
    # A short cumulative quiz starts from lesson 1 and keeps the same Poll UX.
    await start_lesson_quiz(callback, 1)


@router.poll_answer()
async def quiz_poll_answer(poll_answer: PollAnswer, bot: Bot):
    poll = store.get_poll(poll_answer.poll_id)
    if not poll or poll["telegram_id"] != poll_answer.user.id:
        return
    attempt_meta = store.quiz_attempt(poll["attempt_id"])
    if not attempt_meta:
        return
    lesson_id = int(attempt_meta["lesson_id"])
    q = quiz_questions(lesson_id)[int(poll["question_index"])]
    attempt = store.record_poll_answer(poll_answer.poll_id, poll_answer.option_ids[0] if poll_answer.option_ids else -1, q["correct"])
    if not attempt:
        return
    next_index = int(poll["question_index"]) + 1
    if next_index < int(attempt["total_questions"]):
        await send_quiz_question(bot, poll_answer.user.id, attempt["id"], lesson_id, next_index)
        return
    result = store.finish_attempt(attempt["id"]); correct = int(result["correct_answers"]); total = int(result["total_questions"]); percent = round(correct / total * 100)
    passed = percent >= 70
    if passed:
        store.add_xp(poll_answer.user.id, percent, f"quiz_attempt:{attempt['id']}")
        store.award_badge(poll_answer.user.id, "quiz_master") if percent == 100 else None
    await bot.send_message(poll_answer.user.id, f"🏁 <b>انتهى الاختبار</b>\n\n📊 النتيجة: <b>{correct}/{total} ({percent}%)</b>\n\n{'✅ تم الاجتياز' if passed else '🔁 يمكنك إعادة المحاولة'}\n⭐ {'+' + str(percent) + ' XP' if passed else '0 XP'}", reply_markup=kb([[InlineKeyboardButton(text="📘 العودة إلى الدرس", callback_data=f"cpp_lesson:{lesson_id}")],[InlineKeyboardButton(text="🔄 إعادة الاختبار", callback_data=f"cpp_quiz:{lesson_id}")]]))


@router.callback_query(F.data.startswith("cpp_complete:"))
async def cpp_complete(callback: CallbackQuery):
    lesson_id = int(callback.data.split(":")[1]); user_id = callback.from_user.id
    if lesson_id not in LESSONS:
        await callback.answer("❌ هذا الدرس غير موجود.", show_alert=True)
        return
    first = store.complete_lesson(user_id, lesson_id); store.touch_activity(user_id); store.set_last_lesson(user_id, lesson_id)
    completed = len(store.completed_lessons(user_id) & set(CORE_LESSON_IDS)); percent = round(completed / len(CORE_LESSON_IDS) * 100)
    if completed >= 1: store.award_badge(user_id, "first_lesson")
    if store.streak(user_id) >= 7: store.award_badge(user_id, "seven_day_streak")
    if completed >= 5: store.award_badge(user_id, "five_lessons")
    next_id = next((i for i in CORE_LESSON_IDS if i > lesson_id), None)
    buttons = []
    if next_id is not None: buttons.append([InlineKeyboardButton(text=f"➡️ الدرس التالي: {next_id:02d}", callback_data=f"cpp_lesson:{next_id}")])
    else: buttons.append([InlineKeyboardButton(text="🎓 إصدار الشهادة", callback_data="issue_certificate")])
    buttons += [[InlineKeyboardButton(text="⬅️ السابق", callback_data=f"lesson_prev:{lesson_id}")],[InlineKeyboardButton(text="📚 قائمة الدروس", callback_data="cpp_beginner")]]
    await callback.message.edit_text(f"✅ <b>تم إكمال الدرس {lesson_id:02d}</b>\n\n📊 التقدم: {completed}/{len(CORE_LESSON_IDS)} ({percent}%)\n⭐ {'+50 XP' if first else 'كان مكتملًا مسبقًا'}\n🔥 Streak: {store.streak(user_id)} يوم", reply_markup=kb(buttons)); await callback.answer()


@router.callback_query(F.data == "cpp_progress")
async def cpp_progress(callback: CallbackQuery):
    stats = store.snapshot(callback.from_user.id, len(CORE_LESSON_IDS)); filled = min(10, stats["percent"] // 10); bar = "█"*filled + "░"*(10-filled)
    await callback.message.edit_text(f"📊 <b>تقدمك في C++</b>\n\n{bar} {stats['percent']}%\n\n📚 {stats['completed']}/{len(CORE_LESSON_IDS)} درس\n⭐ {stats['xp']} XP\n🔥 {stats['streak']} يوم\n\n💾 تقدمك محفوظ.", reply_markup=kb([[InlineKeyboardButton(text="▶️ متابعة التعلم", callback_data="continue_learning")],[InlineKeyboardButton(text="🎓 لوحة التعلم", callback_data="dashboard")],[InlineKeyboardButton(text="🔙 مسار C++", callback_data="cpp_menu")]])); await callback.answer()


@router.callback_query(F.data.startswith("lesson_prev:"))
async def lesson_prev(callback: CallbackQuery):
    current = int(callback.data.split(":")[1]); ids = CORE_LESSON_IDS; prev_id = ids[ids.index(current)-1] if current in ids and ids.index(current) > 0 else None
    if prev_id is None: await callback.answer("هذا أول درس."); return
    await callback.message.edit_text(f"📘 <b>الدرس {prev_id:02d}: {LESSONS[prev_id]['title']}</b>\n\n🎯 {LESSONS[prev_id]['objective']}", reply_markup=get_lesson_kb(prev_id)); store.set_last_lesson(callback.from_user.id, prev_id); await callback.answer()


@router.callback_query(F.data.startswith("lesson_next:"))
async def lesson_next(callback: CallbackQuery):
    current = int(callback.data.split(":")[1]); ids = CORE_LESSON_IDS; idx = ids.index(current) if current in ids else -1; next_id = ids[idx+1] if idx >= 0 and idx+1 < len(ids) else None
    if next_id is None: await callback.answer("هذا آخر درس."); return
    await callback.message.edit_text(f"📘 <b>الدرس {next_id:02d}: {LESSONS[next_id]['title']}</b>\n\n🎯 {LESSONS[next_id]['objective']}", reply_markup=get_lesson_kb(next_id)); store.set_last_lesson(callback.from_user.id, next_id); await callback.answer()


@router.callback_query(F.data.startswith("favorite:"))
async def toggle_favorite(callback: CallbackQuery):
    lesson_id = int(callback.data.split(":",1)[1]); saved = store.toggle_favorite(callback.from_user.id,"lesson",str(lesson_id)); await callback.answer("🔖 تمت الإضافة إلى المحفوظات" if saved else "🔖 تمت الإزالة من المحفوظات")


@router.callback_query(F.data.startswith("notify:"))
async def notify_me(callback: CallbackQuery):
    if not store.get_profile(callback.from_user.id):
        await callback.answer("ابدأ بالتسجيل أولًا عبر /start."); return
    key = callback.data.split(":",1)[1]
    enabled = store.toggle_launch_notification(callback.from_user.id, key)
    await callback.answer("🔔 تم تسجيل طلب الإشعار عند الإطلاق." if enabled else "🔕 أُزيل طلب الإشعار.")


@router.callback_query(F.data == "custom_lessons")
async def custom_lessons(callback: CallbackQuery):
    ids = [i for i in LESSONS if i not in CORE_LESSON_IDS]
    if not ids:
        await callback.answer("لا توجد دروس إضافية بعد."); return
    buttons = [[InlineKeyboardButton(text=f"🆕 {LESSONS[i]['title']}", callback_data=f"cpp_lesson:{i}")] for i in ids[:20]]
    buttons.append([InlineKeyboardButton(text="🔙 C++ للمبتدئين", callback_data="cpp_beginner")])
    await callback.message.edit_text("🆕 <b>دروس مضافة حديثًا</b>\n\nهذه الدروس أضافها فريق الإدارة ويمكن أن تكون خارج المسار الأساسي.", reply_markup=kb(buttons)); await callback.answer()
@router.callback_query(F.data == "reminders")
async def reminders(callback: CallbackQuery):
    profile = store.get_profile(callback.from_user.id)
    if not profile: await callback.answer("ابدأ بالتسجيل أولًا عبر /start."); return
    await callback.message.edit_text("⏰ <b>التذكير اليومي</b>\n\nسنرسل تذكيرًا واحدًا يوميًا عند الساعة 18:00 بتوقيت الخادم عندما يكون التذكير مفعّلًا.", reply_markup=kb([[InlineKeyboardButton(text="🔔 تفعيل التذكيرات", callback_data="reminder:on")],[InlineKeyboardButton(text="🔕 إيقاف التذكيرات", callback_data="reminder:off")],[InlineKeyboardButton(text="🔙 القائمة الرئيسية", callback_data="main_menu")]])); await callback.answer()


@router.callback_query(F.data.startswith("reminder:"))
async def reminder_toggle(callback: CallbackQuery):
    enabled = callback.data.endswith(":on"); store.set_reminders(callback.from_user.id, enabled)
    await callback.answer("🔔 تم تفعيل التذكيرات اليومية." if enabled else "🔕 تم إيقاف التذكيرات اليومية.")


CERTIFICATE_COURSE = "cpp_beginner"



def certificate_text(cert: dict) -> str:
    return (
        f"🎓 <b>مبروك!</b>\n\nتم إصدار شهادة إتمام C++ للمبتدئين مجانًا.\n\n"
        f"🆔 Verification Code: <code>{escape(str(cert['verification_code']))}</code>\n"
        f"📅 تاريخ الإصدار: {escape(str(cert['issued_at']))}"
    )


@router.callback_query(F.data == "issue_certificate")
async def issue_certificate(callback: CallbackQuery):
    """Issue the completion certificate at no cost; no invoice or card/payment flow is used."""
    user_id = callback.from_user.id
    if not await course_completed(user_id):
        await callback.answer("أكمل جميع الدروس أولًا.")
        return
    try:
        cert = await asyncio.to_thread(store.issue_certificate, user_id, CERTIFICATE_COURSE)
        await asyncio.to_thread(store.award_badge, user_id, "cpp_graduate")
        await callback.message.edit_text(
            certificate_text(cert),
            reply_markup=kb([[InlineKeyboardButton(text="🔙 الإنجازات", callback_data="achievements")]]),
        )
        await callback.answer("تم إصدار الشهادة مجانًا.")
    except Exception as exc:
        from infrastructure.observability.sentry import capture_exception
        capture_exception(exc, tags={"component": "certificate", "operation": "issue"}, extras={"user_id": user_id, "course_key": CERTIFICATE_COURSE})
        await callback.answer("تعذر إصدار الشهادة الآن. حاول مرة أخرى لاحقًا.", show_alert=True)


@router.message(Command("reminders"))
async def reminders_command(message: Message):
    await message.answer("⏰ <b>التذكيرات اليومية</b>\n\nاختر حالة التذكير:", reply_markup=kb([[InlineKeyboardButton(text="🔔 تفعيل", callback_data="reminder:on")],[InlineKeyboardButton(text="🔕 إيقاف", callback_data="reminder:off")]]))


@router.message(Command("certificate"))
async def certificate_command(message: Message):
    cert = await asyncio.to_thread(store.certificate, message.from_user.id)
    if not cert: await message.answer("🎓 لا توجد شهادة صادرة بعد. أكمل جميع دروس C++ ثم استخدم زر إصدار الشهادة."); return
    await message.answer(f"🎓 <b>شهادتك</b>\n\nC++ للمبتدئين\nVerification Code: <code>{cert['verification_code']}</code>\nتاريخ الإصدار: {cert['issued_at']}")


# ---------------- Admin panel ----------------
def admin_kb():
    return kb([[InlineKeyboardButton(text="📊 الإحصائيات", callback_data="admin:stats")],[InlineKeyboardButton(text="📢 بث رسالة", callback_data="admin:broadcast")],[InlineKeyboardButton(text="📚 إضافة درس", callback_data="admin:add_lesson")],[InlineKeyboardButton(text="🔙 الرئيسية", callback_data="main_menu")]])


@router.message(Command("admin"))
async def admin_command(message: Message):
    panel_url = _admin_panel_url()
    rows = []
    if panel_url:
        rows.append([InlineKeyboardButton(text="🗂️ فتح لوحة إدارة المحتوى", web_app=WebAppInfo(url=panel_url))])
        rows.append([InlineKeyboardButton(text="✦ فتح الخريطة الهولوغرامية", web_app=WebAppInfo(url=f"{panel_url}/holographic/"))])
    rows.append([InlineKeyboardButton(text="📊 الأدوات السريعة", callback_data="admin:quick_tools")])
    rows.append([InlineKeyboardButton(text="🔙 الرئيسية", callback_data="main_menu")])
    await message.answer("🔐 <b>لوحة الإدارة الرئيسية</b>\nاختر واجهة الإدارة التي تريد فتحها.", reply_markup=kb(rows))


def _admin_panel_url() -> str | None:
    base = settings.web_app_url
    if not base and settings.webhook_url:
        parsed = urlparse(settings.webhook_url)
        if parsed.scheme == "https" and parsed.netloc:
            base = f"{parsed.scheme}://{parsed.netloc}"
    parsed = urlparse(base)
    if parsed.scheme != "https" or not parsed.netloc:
        return None
    if parsed.path.rstrip("/").endswith("/admin"):
        return base.rstrip("/")
    return base.rstrip("/") + "/admin"


def _holographic_panel_url() -> str | None:
    panel = _admin_panel_url()
    return f"{panel}/holographic/" if panel else None


@router.message(Command("contentadmin"))
async def content_admin_command(message: Message):
    panel_url = _admin_panel_url()
    if not panel_url:
        await message.answer("لم يتم ضبط WEB_APP_URL أو WEBHOOK_URL صالح لفتح لوحة الإدارة.")
        return
    holographic_url = _holographic_panel_url()
    buttons = [[InlineKeyboardButton(text="🗂️ فتح لوحة إدارة المحتوى", web_app=WebAppInfo(url=panel_url))]]
    if holographic_url:
        buttons.append([InlineKeyboardButton(text="✦ فتح الخريطة الهولوغرامية", web_app=WebAppInfo(url=holographic_url))])
    await message.answer(
        "🗂️ <b>إدارة المحتوى</b>\nاختر اللوحة التي تريد استخدامها لإدارة بيانات البوت التعليمية.",
        reply_markup=kb(buttons),
    )


@router.message(Command("hologram"))
async def hologram_command(message: Message):
    await content_admin_command(message)


@router.callback_query(F.data == "admin:stats")
async def admin_stats(callback: CallbackQuery):
    await callback.message.edit_text(f"📊 <b>إحصائيات الأكاديمية</b>\n\n👥 المستخدمون: {store.user_count()}\n📚 الدروس الأصلية: 13\n📦 الدروس المضافة: {len(store.custom_lessons())}\n🎓 الشهادات: {store.certificate_count()}", reply_markup=admin_kb()); await callback.answer()


@router.callback_query(F.data == "admin:quick_tools")
async def admin_quick_tools(callback: CallbackQuery):
    await callback.message.edit_text("🔐 <b>أدوات الإدارة السريعة</b>", reply_markup=admin_kb())
    await callback.answer()


@router.message(Command("broadcast"))
async def broadcast_command(message: Message, state: FSMContext):
    await state.set_state(AdminStates.broadcast)
    await message.answer("📢 أرسل نص البث. /cancel للإلغاء.")


@router.callback_query(F.data == "admin:broadcast")
async def admin_broadcast_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.broadcast); await callback.message.edit_text("📢 أرسل نص الرسالة التي تريد بثها لكل المستخدمين.\n\n❌ /cancel للإلغاء."); await callback.answer()


@router.message(AdminStates.broadcast)
async def admin_broadcast(message: Message, state: FSMContext):
    if (message.text or "").strip() == "/cancel": await state.clear(); await message.answer("تم الإلغاء."); return
    sent = 0
    for uid in store.all_user_ids():
        try:
            await message.bot.send_message(uid, message.html_text or message.text or "")
            sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            continue
    await state.clear(); await message.answer(f"📢 تم إرسال البث إلى {sent} مستخدم.")


@router.callback_query(F.data == "admin:add_lesson")
async def admin_add_lesson_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.lesson_title); await callback.message.edit_text("📚 عنوان الدرس الجديد:"); await callback.answer()


@router.message(AdminStates.lesson_title)
async def admin_lesson_title(message: Message, state: FSMContext):
    value = (message.text or "").strip()
    if not value or len(value) > 200: await message.answer("❌ العنوان مطلوب وبحد أقصى 200 حرف."); return
    await state.update_data(title=value); await state.set_state(AdminStates.lesson_duration); await message.answer("⏱️ المدة، مثال: 30 دقيقة")

@router.message(AdminStates.lesson_duration)
async def admin_lesson_duration(message: Message, state: FSMContext):
    value = (message.text or "30 دقيقة").strip()[:100]
    await state.update_data(duration=value); await state.set_state(AdminStates.lesson_objective); await message.answer("🎯 هدف الدرس:")

@router.message(AdminStates.lesson_objective)
async def admin_lesson_objective(message: Message, state: FSMContext):
    value = (message.text or "").strip()
    if not value or len(value) > 1000: await message.answer("❌ الهدف مطلوب وبحد أقصى 1000 حرف."); return
    await state.update_data(objective=value); await state.set_state(AdminStates.lesson_theory); await message.answer("📖 المحتوى النظري:")

@router.message(AdminStates.lesson_theory)
async def admin_lesson_theory(message: Message, state: FSMContext):
    value = (message.text or "").strip()
    if not value or len(value) > 15000: await message.answer("❌ المحتوى مطلوب وبحد أقصى 15,000 حرف."); return
    await state.update_data(theory=value); await state.set_state(AdminStates.lesson_code); await message.answer("💻 كود C++ اختياري، أرسل - إذا لم يوجد:")

@router.message(AdminStates.lesson_code)
async def admin_lesson_code(message: Message, state: FSMContext):
    value = "" if (message.text or "").strip() == "-" else (message.text or "")
    if len(value) > 30000: await message.answer("❌ الكود يجب ألا يتجاوز 30,000 حرف."); return
    await state.update_data(code=value); await state.set_state(AdminStates.lesson_examples); await message.answer("🧠 أمثلة/تمارين اختيارية:")

@router.message(AdminStates.lesson_examples)
async def admin_lesson_examples(message: Message, state: FSMContext):
    examples = (message.text or "")[:10000]
    data = await state.get_data(); lesson_id = store.add_custom_lesson(data["title"],data["duration"],data["objective"],data["theory"],data["code"],examples,message.from_user.id)
    LESSONS[1000 + lesson_id] = {"title":escape(data["title"]),"duration":escape(data["duration"]),"objective":escape(data["objective"]),"theory":escape(data["theory"]),"simple":"","code":normalize_custom_code(data["code"]),"examples":escape(examples),"question":None,"answers":[],"explain":""}
    for uid in store.launch_subscribers("custom_lessons"):
        try:
            await message.bot.send_message(uid, f"🎉 <b>تم إطلاق درس جديد</b>\n\n{escape(data['title'])}\n\n[ ▶️ افتح قسم الدروس المضافة ]", reply_markup=kb([[InlineKeyboardButton(text="📚 فتح الدرس الجديد", callback_data="custom_lessons")]]))
            store.mark_launch_notified(uid, "custom_lessons")
        except Exception:
            pass
    await state.clear(); await message.answer(f"✅ تمت إضافة الدرس #{1000+lesson_id}.", reply_markup=admin_kb())
