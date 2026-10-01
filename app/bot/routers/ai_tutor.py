from __future__ import annotations

import re

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.ai.provider import AIConfigurationError
from app.ai.service import ai_service
from app.storage.postgres import store
from app.webapp.piston import execute_code

router = Router(name="ai_tutor")


def kb(rows):
    return InlineKeyboardMarkup(inline_keyboard=rows)


class AIStates(StatesGroup):
    chat = State()
    review = State()


def ai_menu_kb() -> InlineKeyboardMarkup:
    return kb([
        [InlineKeyboardButton(text="🧠 اسأل المعلم", callback_data="ai:start")],
        [InlineKeyboardButton(text="🧑‍💻 راجع كودي", callback_data="ai:review"), InlineKeyboardButton(text="📝 اختبرني", callback_data="ai:quiz_info")],
        [InlineKeyboardButton(text="🗑️ مسح ذاكرة المحادثة", callback_data="ai:clear")],
        [InlineKeyboardButton(text="📊 استهلاكي اليوم", callback_data="ai:usage")],
        [InlineKeyboardButton(text="🔙 القائمة الرئيسية", callback_data="main_menu")],
    ])


def chat_kb() -> InlineKeyboardMarkup:
    return kb([
        [InlineKeyboardButton(text="💡 بسّط لي", callback_data="ai:simplify")],
        [InlineKeyboardButton(text="🧑‍💻 راجع كودًا", callback_data="ai:review"), InlineKeyboardButton(text="🗑️ مسح المحادثة", callback_data="ai:clear")],
        [InlineKeyboardButton(text="🔙 AI Academy", callback_data="ai:menu")],
    ])


def _profile_required(user_id: int) -> bool:
    return bool(store.get_profile(user_id))



def _chunks(text: str, size: int = 3800) -> list[str]:
    text = str(text or "")
    if len(text) <= size:
        return [text] if text else []
    chunks = []
    while text:
        cut = min(size, len(text))
        if cut < len(text):
            split = text.rfind("\n", 0, cut)
            if split > size // 2:
                cut = split
        chunks.append(text[:cut].strip())
        text = text[cut:].lstrip()
    return [c for c in chunks if c]

def _extract_code(text: str) -> tuple[str, str]:
    match = re.search(r"```([A-Za-z0-9_+#-]*)\s*\n?(.*?)```", text, re.S)
    if match:
        lang = (match.group(1) or "cpp").lower()
        return match.group(2).strip(), lang
    return text.strip(), "cpp"


@router.message(Command("ai"))
async def ai_command(message: Message):
    if not _profile_required(message.from_user.id):
        await message.answer("👤 ابدأ بالتسجيل أولًا عبر /start، ثم يمكنك استخدام المعلم الذكي.")
        return
    await message.answer(
        "🤖 <b>AI Academy</b>\n\n"
        "المعلم الذكي يساعدك على الفهم والممارسة ومراجعة الأكواد، مع الاستفادة من محتوى الأكاديمية وتقدمك.",
        reply_markup=ai_menu_kb(),
    )


@router.callback_query(F.data == "ai:menu")
async def ai_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    if not _profile_required(callback.from_user.id):
        await callback.message.edit_text("👤 ابدأ بالتسجيل أولًا عبر /start.")
        await callback.answer()
        return
    await callback.message.edit_text(
        "🤖 <b>AI Academy</b>\n\nاختر ما تريد فعله:",
        reply_markup=ai_menu_kb(),
    )
    await callback.answer()




@router.callback_query(F.data.startswith("ai:lesson:"))
async def ai_lesson(callback: CallbackQuery, state: FSMContext):
    if not _profile_required(callback.from_user.id):
        await callback.answer("ابدأ بالتسجيل أولًا عبر /start.")
        return
    try:
        lesson_id = int(callback.data.rsplit(":", 1)[1])
    except ValueError:
        await callback.answer("درس غير صالح.")
        return
    await state.set_state(AIStates.chat)
    await state.update_data(lesson_id=lesson_id, last_question=None)
    await callback.message.edit_text(
        "🤖 <b>المعلم الذكي — عن هذا الدرس</b>\n\n"
        "أرسل سؤالك، وسأستخدم محتوى الدرس الحالي مع مستواك وتقدمك.\n\n"
        "مثال: لم أفهم هذا الجزء، اشرحه لي بطريقة أبسط.",
        reply_markup=chat_kb(),
    )
    await callback.answer()

@router.callback_query(F.data == "ai:start")
async def ai_start(callback: CallbackQuery, state: FSMContext):
    if not _profile_required(callback.from_user.id):
        await callback.answer("ابدأ بالتسجيل أولًا عبر /start.")
        return
    await state.set_state(AIStates.chat)
    await state.update_data(lesson_id=None)
    await callback.message.edit_text(
        "👨‍🏫 <b>المعلم الذكي</b>\n\n"
        "اكتب سؤالك بحرية. سأحاول الشرح بطريقة تناسب مستواك، ويمكنك بعد ذلك طلب تبسيط الشرح أو الانتقال إلى مراجعة الكود.\n\n"
        "مثال: ما الفرق بين pointer وreference في C++؟\n\n"
        "/cancel لإلغاء وضع المعلم.",
        reply_markup=chat_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "ai:review")
async def ai_review_start(callback: CallbackQuery, state: FSMContext):
    if not _profile_required(callback.from_user.id):
        await callback.answer("ابدأ بالتسجيل أولًا عبر /start.")
        return
    await state.set_state(AIStates.review)
    await state.update_data(lesson_id=None)
    await callback.message.edit_text(
        "🧑‍💻 <b>مراجع الأكواد</b>\n\n"
        "أرسل الكود داخل رسالة، ويفضل بهذا الشكل:\n\n"
        "```cpp\nint main() { return 0; }\n```\n\n"
        "سأشغّل الكود عبر Piston ثم أستخدم النتيجة مع المراجعة التعليمية. إذا تعذر الاتصال، سأوضح ذلك وأكمل التحليل الساكن.\n\n"
        "/cancel للإلغاء.",
        reply_markup=kb([[InlineKeyboardButton(text="🔙 AI Academy", callback_data="ai:menu")]]),
    )
    await callback.answer()


@router.callback_query(F.data == "ai:quiz_info")
async def ai_quiz_info(callback: CallbackQuery):
    await callback.message.edit_text(
        "📝 <b>الاختبارات الذكية</b>\n\n"
        "هذه الواجهة مهيأة لربط مولد الاختبارات الذكي بالاختبارات الأصلية في الأكاديمية.\n\n"
        "في النسخة الحالية نُبقي توليد الأسئلة خارج مسار التشغيل حتى لا تصل أسئلة غير مُتحقق منها إلى الطالب. سيتم تفعيلها بعد إضافة طبقة التحقق وحفظ الأسئلة.",
        reply_markup=ai_menu_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "ai:clear")
async def ai_clear(callback: CallbackQuery, state: FSMContext):
    store.clear_ai_history(callback.from_user.id)
    await state.clear()
    await callback.message.edit_text("🗑️ تم مسح ذاكرة محادثة المعلم الذكي لهذا الحساب.", reply_markup=ai_menu_kb())
    await callback.answer("تم المسح")


@router.callback_query(F.data == "ai:usage")
async def ai_usage(callback: CallbackQuery):
    usage = ai_service.usage(callback.from_user.id)
    await callback.message.edit_text(
        "📊 <b>استهلاك AI اليوم</b>\n\n"
        f"👨‍🏫 المعلم: {usage['tutor']}/{ai_service.quota('tutor')}\n"
        f"🧑‍💻 مراجعة الكود: {usage['review']}/{ai_service.quota('review')}\n"
        f"📝 الاختبارات الذكية: {usage['quiz']}/{ai_service.quota('quiz')}",
        reply_markup=ai_menu_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "ai:simplify")
async def ai_simplify(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if data.get("last_question"):
        question = "بسّط إجابتك السابقة أكثر، وكأنك تشرح لطالب مبتدئ جدًا، واستخدم مثالًا صغيرًا."
        await _answer_tutor(callback.message, callback.from_user.id, question, state, lesson_id=data.get("lesson_id"))
        await callback.answer()
        return
    await callback.answer("اسأل المعلم أولًا ثم يمكنك طلب التبسيط.")


@router.callback_query(F.data.startswith("ai:feedback:"))
async def ai_feedback(callback: CallbackQuery):
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer()
        return
    rating = 1 if parts[2] == "up" else -1
    try:
        message_id = int(callback.message.message_id)
    except Exception:
        message_id = None
    store.add_ai_feedback(callback.from_user.id, message_id, rating)
    await callback.answer("شكرًا على التقييم.")


@router.message(Command("cancel"))
async def cancel_ai(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("↩️ تم الخروج من وضع AI.", reply_markup=ai_menu_kb())


async def _answer_tutor(message: Message, user_id: int, question: str, state: FSMContext, lesson_id: int | None = None):
    await message.answer("⏳ أفكر في سؤالك...", parse_mode=None)
    try:
        answer, _message_id = await ai_service.tutor(user_id, question, lesson_id=lesson_id)
        await state.update_data(last_question=question, lesson_id=lesson_id)
        chunks = _chunks(answer)
        for index, chunk in enumerate(chunks):
            await message.answer(
                chunk,
                parse_mode=None,
                reply_markup=(kb([
                    [InlineKeyboardButton(text="👍 مفيد", callback_data="ai:feedback:up"), InlineKeyboardButton(text="👎 غير مفيد", callback_data="ai:feedback:down")],
                    [InlineKeyboardButton(text="💡 بسّط لي", callback_data="ai:simplify"), InlineKeyboardButton(text="🧑‍💻 راجع كودي", callback_data="ai:review")],
                    [InlineKeyboardButton(text="🗑️ مسح المحادثة", callback_data="ai:clear")],
                ]) if index == len(chunks) - 1 else None),
            )
    except AIConfigurationError as exc:
        await message.answer(f"ℹ️ {exc}", parse_mode=None, reply_markup=ai_menu_kb())
    except Exception:
        await message.answer("⚠️ تعذر الحصول على رد من المعلم الآن. لم تُحفظ رسالتك إذا فشل الطلب.", parse_mode=None)


@router.message(AIStates.chat)
async def ai_chat_message(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text:
        await message.answer("أرسل سؤالك كنص، أو استخدم /cancel.")
        return
    data = await state.get_data()
    await _answer_tutor(message, message.from_user.id, text, state, lesson_id=data.get("lesson_id"))


@router.message(AIStates.review)
async def ai_review_message(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text:
        await message.answer("أرسل الكود كنص، أو استخدم /cancel.")
        return
    code, language = _extract_code(text)
    await message.answer("⏳ أراجع الكود تعليميًا...", parse_mode=None)
    try:
        execution_result = await execute_code(language=language, code=code)
        answer, _message_id = await ai_service.review_code(
            message.from_user.id,
            code,
            language=language,
            execution_result=execution_result,
        )
        chunks = _chunks(answer)
        for index, chunk in enumerate(chunks):
            await message.answer(
                chunk,
                parse_mode=None,
                reply_markup=(kb([
                    [InlineKeyboardButton(text="👍 مفيد", callback_data="ai:feedback:up"), InlineKeyboardButton(text="👎 غير مفيد", callback_data="ai:feedback:down")],
                    [InlineKeyboardButton(text="🧑‍💻 مراجعة أخرى", callback_data="ai:review"), InlineKeyboardButton(text="🔙 AI Academy", callback_data="ai:menu")],
                ]) if index == len(chunks) - 1 else None),
            )
        await state.set_state(AIStates.review)
    except AIConfigurationError as exc:
        await message.answer(f"ℹ️ {exc}", parse_mode=None, reply_markup=ai_menu_kb())
    except ValueError as exc:
        await message.answer(f"⚠️ {exc}", parse_mode=None)
    except Exception:
        await message.answer("⚠️ تعذر تحليل الكود الآن. حاول مرة أخرى.", parse_mode=None)
