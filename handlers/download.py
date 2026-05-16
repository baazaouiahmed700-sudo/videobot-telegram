import asyncio
import logging
import os
from pathlib import Path

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from services.downloader import DownloadService
from services.ffmpeg_service import FFmpegService
from utils.helpers import (
    extract_url, format_size, format_duration, format_views,
    send_file_smart, cleanup, make_job_id, is_supported_url
)
from utils.queue_manager import get_queue_manager, Job, set_queue_manager

logger = logging.getLogger(__name__)
router = Router()


class DownloadState(StatesGroup):
    waiting_for_url = State()
    waiting_for_format = State()
    waiting_for_cookies = State()


def _quality_keyboard(url: str, formats) -> InlineKeyboardMarkup:
    buttons = []
    seen_heights = set()
    for f in formats[:8]:
        h = f.get("height")
        label = f"{h}p" if h else f["format_id"]
        if label in seen_heights:
            continue
        seen_heights.add(label)
        buttons.append(
            InlineKeyboardButton(
                text=f"📹 {label} ({f.get('ext','?')}) {format_size(f.get('filesize') or 0)}",
                callback_data=f"dl|{f['format_id']}|{url[:100]}"
            )
        )

    rows = [[b] for b in buttons]
    rows += [
        [
            InlineKeyboardButton(text="🎵 صوت MP3", callback_data=f"dl|audio|{url[:100]}"),
            InlineKeyboardButton(text="⚡ أفضل جودة", callback_data=f"dl|best|{url[:100]}"),
        ],
        [
            InlineKeyboardButton(text="📝 ملخص AI", callback_data=f"ai_sum|{url[:100]}"),
            InlineKeyboardButton(text="🌍 ترجمة", callback_data=f"ai_sub|{url[:100]}"),
        ],
        [
            InlineKeyboardButton(text="✂️ كليبات فيروسية", callback_data=f"ai_clips|{url[:100]}"),
            InlineKeyboardButton(text="🖼️ صورة مصغرة", callback_data=f"thumb|{url[:100]}"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("start"))
async def cmd_start(msg: Message):
    await msg.answer(
        "👋 *مرحباً بك في بوت التحميل المتقدم!*\n\n"
        "أرسل لي رابط أي فيديو وسأتكفل بالباقي 🚀\n\n"
        "**المنصات المدعومة:**\n"
        "YouTube • TikTok • Instagram • X • Facebook\n"
        "Twitch • Reddit • Vimeo • SoundCloud وأكثر من 1000 موقع!\n\n"
        "**الأوامر:**\n"
        "/start - البداية\n"
        "/search - بحث ذكي بالوصف\n"
        "/help - المساعدة\n"
        "/status - حالة الطابور",
        parse_mode="Markdown"
    )


@router.message(Command("help"))
async def cmd_help(msg: Message):
    await msg.answer(
        "📚 *دليل الاستخدام*\n\n"
        "**تحميل بسيط:**\n"
        "فقط أرسل الرابط وسأعرض عليك الخيارات\n\n"
        "**ميزات الذكاء الاصطناعي:**\n"
        "• 📝 **ملخص** - تلخيص تنفيذي فوري\n"
        "• 🌍 **ترجمة** - شرح نصي بأي لغة\n"
        "• ✂️ **كليبات** - استخراج أفضل لقطات\n"
        "• 🎵 **فصل الصوت** - موسيقى أو صوت منفصل\n\n"
        "**التحميل المتقدم:**\n"
        "• أرسل قائمة تشغيل لتحميلها كاملة\n"
        "• استخدم /search للبحث بالوصف\n"
        "• أرفق ملفات Cookies للمحتوى المحمي\n\n"
        "**الرفع السحابي:**\n"
        "استخدم /cloud لرفع إلى Google Drive أو Dropbox",
        parse_mode="Markdown"
    )


@router.message(Command("status"))
async def cmd_status(msg: Message):
    qm = get_queue_manager()
    if qm:
        await msg.answer(
            f"📊 *حالة النظام*\n\n"
            f"• الطابور: `{qm.queue_size()}` مهمة معلقة\n"
            f"• طلباتك الحالية: `{qm.user_jobs(msg.from_user.id)}`\n"
            f"• الحد الأقصى في الساعة: `{qm.is_rate_limited(msg.from_user.id) and 'تجاوزت الحد' or 'OK'}`",
            parse_mode="Markdown"
        )
    else:
        await msg.answer("⚙️ النظام يعمل بوضع المزامنة المباشرة.")


@router.message(F.text & ~F.text.startswith("/"))
async def handle_url_message(msg: Message, state: FSMContext, bot: Bot):
    url = extract_url(msg.text)
    if not url:
        await msg.answer(
            "❓ لم أتعرف على رابط. أرسل رابط الفيديو أو استخدم /search للبحث."
        )
        return

    status_msg = await msg.answer("🔍 جاري تحليل الرابط...")

    try:
        info = await DownloadService.get_info(url)
    except Exception as e:
        await status_msg.edit_text(f"❌ فشل تحليل الرابط:\n`{str(e)[:300]}`", parse_mode="Markdown")
        return

    title = info.get("title", "فيديو")[:60]
    duration = format_duration(info.get("duration"))
    uploader = info.get("uploader") or info.get("channel") or "غير محدد"
    views = format_views(info.get("view_count"))
    thumb = info.get("thumbnail")
    is_playlist = info.get("_type") == "playlist"

    caption = (
        f"🎬 *{title}*\n\n"
        f"👤 {uploader}\n"
        f"⏱ {duration}  •  👁 {views}\n\n"
        f"اختر خيار التحميل:"
    )

    formats = DownloadService.get_available_formats(info)
    keyboard = _quality_keyboard(url, formats)

    if thumb:
        try:
            await msg.answer_photo(photo=thumb, caption=caption, parse_mode="Markdown",
                                   reply_markup=keyboard)
            await status_msg.delete()
        except Exception:
            await status_msg.edit_text(caption, parse_mode="Markdown", reply_markup=keyboard)
    else:
        await status_msg.edit_text(caption, parse_mode="Markdown", reply_markup=keyboard)

    # Playlist hint
    if is_playlist:
        count = info.get("playlist_count", "?")
        await msg.answer(
            f"📂 تم اكتشاف قائمة تشغيل ({count} فيديو)\n"
            "للتحميل الكامل، اضغط الزر أدناه:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text=f"⬇️ تحميل القائمة كاملة ({count} فيديو)",
                    callback_data=f"playlist|{url[:100]}"
                )
            ]])
        )

    await state.update_data(last_url=url)


@router.callback_query(F.data.startswith("dl|"))
async def handle_download(callback: CallbackQuery, bot: Bot):
    _, fmt, url = callback.data.split("|", 2)
    await callback.answer("⬇️ جاري الإضافة للطابور...")

    status_msg = await callback.message.reply("⏳ جاري التحميل...")

    async def _download_task():
        audio_only = (fmt == "audio")
        quality = fmt if fmt not in ("audio", "best") else ("best" if fmt == "best" else None)

        try:
            file_path = await DownloadService.download_video(
                url=url,
                quality=quality or "best",
                audio_only=audio_only,
            )
        except Exception as e:
            await status_msg.edit_text(f"❌ فشل التحميل:\n`{str(e)[:300]}`", parse_mode="Markdown")
            return

        await status_msg.edit_text("📤 جاري الإرسال...")
        success = await send_file_smart(
            bot, callback.message.chat.id, file_path,
            caption=f"✅ تم التحميل بنجاح!\n🔗 {url[:50]}..."
        )
        cleanup(file_path)
        if success:
            await status_msg.delete()

    qm = get_queue_manager()
    if qm:
        job = Job(make_job_id(), callback.from_user.id, callback.message.chat.id, _download_task())
        ok = await qm.enqueue(job)
        if not ok:
            await status_msg.edit_text(
                "⚠️ لقد تجاوزت الحد المسموح به من الطلبات في الساعة. حاول لاحقاً."
            )
    else:
        await _download_task()


@router.callback_query(F.data.startswith("playlist|"))
async def handle_playlist(callback: CallbackQuery, bot: Bot):
    url = callback.data.split("|", 1)[1]
    await callback.answer("📂 جاري تحميل القائمة...")
    status = await callback.message.reply("⏳ جاري تحميل القائمة كاملة...")

    async def _playlist_task():
        try:
            paths = await DownloadService.download_playlist(url, quality="720p", max_items=30)
            await status.edit_text(f"✅ تم تحميل {len(paths)} فيديو. جاري الإرسال...")
            for i, p in enumerate(paths, 1):
                await send_file_smart(bot, callback.message.chat.id, p, caption=f"📹 {i}/{len(paths)}")
                cleanup(p)
                await asyncio.sleep(1)
            await status.delete()
        except Exception as e:
            await status.edit_text(f"❌ خطأ في تحميل القائمة:\n`{str(e)[:200]}`", parse_mode="Markdown")

    qm = get_queue_manager()
    if qm:
        await qm.enqueue(Job(make_job_id(), callback.from_user.id, callback.message.chat.id, _playlist_task()))
    else:
        await _playlist_task()


@router.callback_query(F.data.startswith("thumb|"))
async def handle_thumbnail(callback: CallbackQuery, bot: Bot):
    url = callback.data.split("|", 1)[1]
    await callback.answer("🖼️ جاري استخراج الصورة المصغرة...")
    try:
        thumb_path = await DownloadService.get_thumbnail(url)
        if thumb_path:
            await bot.send_photo(
                callback.message.chat.id,
                photo=str(thumb_path),
                caption="🖼️ الصورة المصغرة بأعلى جودة"
            )
            cleanup(thumb_path)
        else:
            await callback.message.reply("❌ لم يتم العثور على صورة مصغرة.")
    except Exception as e:
        await callback.message.reply(f"❌ خطأ: {str(e)[:200]}")
