from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.storage.postgres import store
from app.bot.routers.start import CORE_LESSON_IDS, LESSONS

router = Router(name="academy_dashboard")


def kb(rows):
    return InlineKeyboardMarkup(inline_keyboard=rows)


def bar(percent: int, width: int = 10) -> str:
    filled = min(width, percent * width // 100)
    return "█" * filled + "░" * (width - filled)


def dashboard_kb():
    return kb([
        [InlineKeyboardButton(text="▶️ متابعة التعلم", callback_data="continue_learning")],
        [InlineKeyboardButton(text="🤖 المعلم الذكي", callback_data="ai:menu")],
        [InlineKeyboardButton(text="📚 دوراتي", callback_data="my_courses"), InlineKeyboardButton(text="🔖 المحفوظات", callback_data="favorites")],
        [InlineKeyboardButton(text="🏆 الإنجازات", callback_data="achievements"), InlineKeyboardButton(text="⏰ التذكيرات", callback_data="reminders")],
        [InlineKeyboardButton(text="🎓 الشهادة", callback_data="issue_certificate")],
        [InlineKeyboardButton(text="🔙 القائمة الرئيسية", callback_data="main_menu")],
    ])


async def render_dashboard(message: Message, user_id: int):
    stats = store.snapshot(user_id, len(CORE_LESSON_IDS))
    name = (store.get_profile(user_id) or {}).get("full_name", "متعلم")
    last = stats.get("last_lesson")
    last_text = f"📍 آخر درس: {last:02d} — {LESSONS[last]['title']}" if last in LESSONS else "📍 لم تبدأ درسًا بعد"
    await message.edit_text(
        f"🎓 <b>لوحة التعلم</b>\n\n👋 أهلاً {escape(str(name))}\n\n"
        f"📘 <b>C++ للمبتدئين</b>\n{bar(stats['percent'])} {stats['percent']}%\n"
        f"📚 {stats['completed']}/{stats['total']} درس\n⭐ {stats['xp']} XP\n🔥 سلسلة التعلم: {stats['streak']} يوم\n{last_text}\n\n"
        "💡 تقدمك محفوظ حتى بعد إعادة تشغيل البوت.", reply_markup=dashboard_kb())


@router.callback_query(F.data == "dashboard")
async def dashboard(callback: CallbackQuery):
    await render_dashboard(callback.message, callback.from_user.id)
    await callback.answer()


@router.message(Command("progress"))
async def progress_command(message: Message):
    await message.answer("📊 افتح لوحة التعلم من القائمة الرئيسية لرؤية تقدمك بالتفصيل.", reply_markup=kb([[InlineKeyboardButton(text="📊 لوحة التعلم", callback_data="dashboard")]]))


@router.message(Command("learn"))
async def learn_command(message: Message):
    await show_continue(message, message.from_user.id)


@router.callback_query(F.data == "continue_learning")
async def continue_learning(callback: CallbackQuery):
    await show_continue(callback.message, callback.from_user.id, edit=True)
    await callback.answer()


async def show_continue(message: Message, user_id: int, *, edit: bool = False):
    completed = store.completed_lessons(user_id) & set(CORE_LESSON_IDS)
    last = store.last_lesson(user_id)
    if last in LESSONS and last not in completed:
        next_id = last
    else:
        next_id = next((i for i in CORE_LESSON_IDS if i not in completed), None)
    if next_id is None:
        text = "🏆 <b>أحسنت!</b>\n\nأكملت جميع دروس C++ للمبتدئين.\n\nيمكنك إصدار شهادة الإتمام إذا استوفيت المتطلبات."
        buttons = [[InlineKeyboardButton(text="🎓 إصدار الشهادة", callback_data="issue_certificate")], [InlineKeyboardButton(text="🔙 لوحة التعلم", callback_data="dashboard")]]
    else:
        lesson = LESSONS[next_id]
        text = f"▶️ <b>أكمل من حيث توقفت</b>\n\n📘 الدرس {next_id:02d}: {lesson['title']}\n⏱️ {lesson['duration']}\n\n🎯 {lesson['objective']}"
        buttons = [[InlineKeyboardButton(text="🚀 فتح الدرس", callback_data=f"cpp_lesson:{next_id}")], [InlineKeyboardButton(text="🔙 لوحة التعلم", callback_data="dashboard")]]
    if edit:
        await message.edit_text(text, reply_markup=kb(buttons))
    else:
        await message.answer(text, reply_markup=kb(buttons))


@router.callback_query(F.data == "my_courses")
async def my_courses(callback: CallbackQuery):
    stats = store.snapshot(callback.from_user.id, len(CORE_LESSON_IDS))
    await callback.message.edit_text("📚 <b>دوراتي</b>\n\n" f"💻 C++ — المبتدئ\n{bar(stats['percent'])} {stats['percent']}%\n{stats['completed']} من {stats['total']} درس مكتمل\n\n🛡️ المسارات الأخرى ستظهر هنا عند نشرها.", reply_markup=kb([[InlineKeyboardButton(text="▶️ متابعة C++", callback_data="continue_learning")],[InlineKeyboardButton(text="🔙 لوحة التعلم", callback_data="dashboard")]]))
    await callback.answer()


@router.message(Command("profile"))
async def profile_command(message: Message):
    profile = store.get_profile(message.from_user.id)
    if not profile:
        await message.answer("👤 لا يوجد ملف بعد. ابدأ عبر /start."); return
    uni = profile.get("university") or "غير محددة"; dept = profile.get("department") or "غير محدد"
    await message.answer(f"👤 <b>حسابي</b>\n\nالاسم: {escape(str(profile['full_name']))}\nالعمر: {profile['age']}\nالجامعة: {escape(str(uni))}\nالقسم: {escape(str(dept))}\nالمستوى: {escape(str(profile['level']))}\n\n🔐 الخصوصية: تمت الموافقة")


@router.callback_query(F.data == "profile")
async def profile(callback: CallbackQuery):
    p = store.get_profile(callback.from_user.id)
    if not p:
        await callback.message.edit_text("👤 لا يوجد ملف بعد. ابدأ عبر /start."); await callback.answer(); return
    uni = p.get("university") or "غير محددة"; dept = p.get("department") or "غير محدد"
    await callback.message.edit_text(f"👤 <b>حسابي</b>\n\nالاسم: {escape(str(p['full_name']))}\nالعمر: {p['age']}\nالجامعة: {escape(str(uni))}\nالقسم: {escape(str(dept))}\nالمستوى: {escape(str(p['level']))}", reply_markup=kb([[InlineKeyboardButton(text="🔙 القائمة الرئيسية", callback_data="main_menu")]])); await callback.answer()


@router.message(Command("courses"))
async def courses_command(message: Message):
    stats = store.snapshot(message.from_user.id, len(CORE_LESSON_IDS))
    await message.answer(f"📚 <b>دوراتي</b>\n\n💻 C++ — المبتدئ\n{bar(stats['percent'])} {stats['percent']}%\n{stats['completed']} من {stats['total']} درس مكتمل", reply_markup=kb([[InlineKeyboardButton(text="▶️ متابعة C++", callback_data="continue_learning")]]))


@router.message(Command("achievements"))
async def achievements_command(message: Message):
    await message.answer("🏆 افتح قسم الإنجازات من لوحة التعلم.", reply_markup=kb([[InlineKeyboardButton(text="🏆 الإنجازات", callback_data="achievements")]]))


@router.message(Command("favorites"))
async def favorites_command(message: Message):
    await message.answer("🔖 افتح المحفوظات من لوحة التعلم.", reply_markup=kb([[InlineKeyboardButton(text="🔖 المحفوظات", callback_data="favorites")]]))


@router.message(Command("help"))
async def help_command(message: Message):
    await message.answer("❓ <b>المساعدة</b>\n\n/start — بدء الأكاديمية\n/learn — متابعة التعلم\n/progress — تقدمك\n/profile — حسابك\n/courses — دوراتك\n/achievements — إنجازاتك\n/favorites — المحفوظات\n/reminders — التذكيرات\n/certificate — الشهادة\n/privacy — الخصوصية\n/delete_my_data — حذف بياناتك")


@router.callback_query(F.data == "achievements")
async def achievements(callback: CallbackQuery):
    stats = store.snapshot(callback.from_user.id, len(CORE_LESSON_IDS)); completed = stats["completed"]
    awarded = set(store.badges(callback.from_user.id))
    labels = {"first_lesson":"🌱 أول خطوة","five_lessons":"🔥 مستمر — 5 دروس","seven_day_streak":"⚡ أسبوع متواصل","quiz_master":"🧠 Quiz Master","cpp_graduate":"🎓 C++ Graduate"}
    lines = [labels[k] for k in awarded if k in labels]
    if not lines: lines = ["🔒 أكمل أول درس لفتح أول إنجاز"]
    leaderboard = store.leaderboard(10)
    rank = next((i for i, row in enumerate(leaderboard, 1) if row["telegram_id"] == callback.from_user.id), None)
    await callback.message.edit_text("🏆 <b>الإنجازات</b>\n\n" + "\n".join(f"• {x}" for x in lines) + f"\n\n⭐ إجمالي XP: {stats['xp']}\n🔥 Streak: {stats['streak']} يوم\n🏅 ترتيبك: {rank or '—'}", reply_markup=kb([[InlineKeyboardButton(text="🏅 لوحة الصدارة", callback_data="leaderboard")],[InlineKeyboardButton(text="🎓 الشهادة", callback_data="issue_certificate")],[InlineKeyboardButton(text="🔙 لوحة التعلم", callback_data="dashboard")]])); await callback.answer()


@router.callback_query(F.data == "leaderboard")
async def leaderboard(callback: CallbackQuery):
    rows = store.leaderboard(10)
    if not rows:
        text = "🏅 لا توجد بيانات كافية بعد."
    else:
        text = "🏅 <b>لوحة الصدارة</b>\n\n" + "\n".join(f"{i}. متعلم {i:02d} — ⭐ {r['xp']} XP" for i,r in enumerate(rows,1))
    await callback.message.edit_text(text, reply_markup=kb([[InlineKeyboardButton(text="🔙 الإنجازات", callback_data="achievements")]])); await callback.answer()


@router.callback_query(F.data == "favorites")
async def favorites(callback: CallbackQuery):
    ids = store.favorites(callback.from_user.id)
    if not ids:
        text = "🔖 <b>المحفوظات</b>\n\nلا توجد دروس محفوظة حتى الآن."
        buttons = [[InlineKeyboardButton(text="📚 دروس C++", callback_data="cpp_beginner")], [InlineKeyboardButton(text="🔙 لوحة التعلم", callback_data="dashboard")]]
    else:
        lines = ["🔖 <b>المحفوظات</b>\n"]; buttons = []
        for lesson_id in ids[:20]:
            if lesson_id in LESSONS:
                lines.append(f"• {lesson_id:02d} — {LESSONS[lesson_id]['title']}"); buttons.append([InlineKeyboardButton(text=f"📘 فتح {lesson_id:02d}", callback_data=f"cpp_lesson:{lesson_id}")])
        buttons.append([InlineKeyboardButton(text="🔙 لوحة التعلم", callback_data="dashboard")]); text = "\n".join(lines)
    await callback.message.edit_text(text, reply_markup=kb(buttons)); await callback.answer()
