import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from services.ai_service import AIService
import yt_dlp

logger = logging.getLogger(__name__)
router = Router()


class SearchState(StatesGroup):
    waiting_for_query = State()


@router.message(Command("search"))
async def cmd_search(msg: Message, state: FSMContext):
    await msg.answer(
        "🔍 *البحث الذكي*\n\n"
        "صِف ما تريد تحميله بالعربية أو الإنجليزية:\n\n"
        "مثال: _ابحث عن فيديو يشرح الكيمياء العضوية وحمله بجودة 720p_",
        parse_mode="Markdown"
    )
    await state.set_state(SearchState.waiting_for_query)


@router.message(SearchState.waiting_for_query)
async def handle_search_query(msg: Message, state: FSMContext, bot: Bot):
    await state.clear()
    status = await msg.answer("🧠 جاري تحليل طلبك وإيجاد أفضل نتائج...")

    try:
        parsed = await AIService.search_to_query(msg.text)
        query = parsed.get("query", msg.text)
        quality = parsed.get("quality", "720p")

        await status.edit_text(f"🔍 بحث عن: `{query}`", parse_mode="Markdown")

        results = await _youtube_search(query, max_results=5)

        if not results:
            await status.edit_text("❌ لم يتم العثور على نتائج.")
            return

        keyboard_rows = []
        text_lines = [f"🔍 *نتائج البحث عن:* `{query}`\n"]

        for i, r in enumerate(results, 1):
            duration = _fmt_dur(r.get("duration"))
            views = _fmt_views(r.get("view_count"))
            title = r.get("title", "?")[:50]
            url = r.get("webpage_url", "")

            text_lines.append(f"{i}. *{title}*\n⏱ {duration}  👁 {views}\n")
            keyboard_rows.append([
                InlineKeyboardButton(
                    text=f"⬇️ {i}. {title[:30]}",
                    callback_data=f"dl|{quality}|{url[:100]}"
                )
            ])

        await status.edit_text(
            "\n".join(text_lines),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
        )

    except Exception as e:
        await status.edit_text(f"❌ خطأ في البحث:\n`{str(e)[:200]}`", parse_mode="Markdown")


async def _youtube_search(query: str, max_results: int = 5):
    import asyncio
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "skip_download": True,
    }

    def _search():
        with yt_dlp.YoutubeDL(opts) as ydl:
            result = ydl.extract_info(f"ytsearch{max_results}:{query}", download=False)
            return result.get("entries", []) if result else []

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _search)


def _fmt_dur(s):
    if not s:
        return "?"
    m, sec = divmod(int(s), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def _fmt_views(n):
    if not n:
        return "?"
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.0f}K"
    return str(n)
