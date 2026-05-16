import asyncio
import logging
from pathlib import Path

from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton

from services.downloader import DownloadService
from services.ai_service import AIService
from services.ffmpeg_service import FFmpegService
from utils.helpers import cleanup, make_job_id, send_file_smart
from utils.queue_manager import get_queue_manager, Job

logger = logging.getLogger(__name__)
router = Router()

LANGUAGE_KEYBOARD = InlineKeyboardMarkup(inline_keyboard=[
    [
        InlineKeyboardButton(text="🇸🇦 عربي", callback_data="lang|ar"),
        InlineKeyboardButton(text="🇬🇧 English", callback_data="lang|en"),
        InlineKeyboardButton(text="🇫🇷 Français", callback_data="lang|fr"),
    ],
    [
        InlineKeyboardButton(text="🇩🇪 Deutsch", callback_data="lang|de"),
        InlineKeyboardButton(text="🇪🇸 Español", callback_data="lang|es"),
        InlineKeyboardButton(text="🇹🇷 Türkçe", callback_data="lang|tr"),
    ],
])


# ── Summarize ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("ai_sum|"))
async def handle_summarize(callback: CallbackQuery, bot: Bot):
    url = callback.data.split("|", 1)[1]
    await callback.answer("🧠 جاري التحليل...")
    status = await callback.message.reply(
        "⏳ جاري التحميل والتحليل بالذكاء الاصطناعي...\nقد يستغرق هذا 1-3 دقائق."
    )

    async def _task():
        audio_path = None
        try:
            # Download audio only
            await status.edit_text("🎵 تحميل المقطع الصوتي...")
            audio_path = await DownloadService.download_video(url, audio_only=True)

            # Transcribe
            await status.edit_text("🔤 تحويل الصوت إلى نص...")
            transcript = await AIService.transcribe(audio_path)
            text = transcript["text"]

            # Summarize
            await status.edit_text("📝 توليد الملخص...")
            summary = await AIService.summarize(text)

            # Extract sources
            sources = await AIService.extract_sources(text)

            # Generate chapters
            chapters = await AIService.generate_chapters(transcript.get("segments", []))
            chapters_text = ""
            if chapters:
                chapters_text = "\n\n⏰ *الفصول:*\n" + "\n".join(
                    f"• `{_fmt_time(c['start'])}` - {c['title']}" for c in chapters
                )

            result = (
                f"📝 *الملخص الذكي*\n\n"
                f"{summary}"
                f"{chapters_text}\n\n"
                f"📚 *المصادر والمراجع:*\n{sources}"
            )

            # Send as file if too long
            if len(result) > 4000:
                summary_file = audio_path.with_suffix(".txt")
                summary_file.write_text(result, encoding="utf-8")
                await bot.send_document(
                    callback.message.chat.id,
                    document=FSInputFile(str(summary_file)),
                    caption="📄 الملخص الكامل (ملف نصي)"
                )
                cleanup(summary_file)
            else:
                await callback.message.reply(result, parse_mode="Markdown")

            await status.delete()
        except Exception as e:
            await status.edit_text(f"❌ خطأ:\n`{str(e)[:300]}`", parse_mode="Markdown")
        finally:
            cleanup(audio_path)

    qm = get_queue_manager()
    if qm:
        await qm.enqueue(Job(make_job_id(), callback.from_user.id, callback.message.chat.id, _task()))
    else:
        await _task()


# ── Subtitles ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("ai_sub|"))
async def handle_subtitles(callback: CallbackQuery, bot: Bot):
    url = callback.data.split("|", 1)[1]
    await callback.answer("🌍 اختر لغة الترجمة")
    # Store URL for language selection
    await callback.message.reply(
        "🌍 اختر لغة الترجمة المطلوبة:",
        reply_markup=_lang_keyboard_with_url(url)
    )


def _lang_keyboard_with_url(url: str) -> InlineKeyboardMarkup:
    langs = [
        ("🇸🇦 عربي", "ar"), ("🇬🇧 English", "en"), ("🇫🇷 Français", "fr"),
        ("🇩🇪 Deutsch", "de"), ("🇪🇸 Español", "es"), ("🇹🇷 Türkçe", "tr"),
    ]
    rows = []
    for i in range(0, len(langs), 3):
        row = [
            InlineKeyboardButton(text=name, callback_data=f"sub_dl|{lang}|{url[:80]}")
            for name, lang in langs[i:i+3]
        ]
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data.startswith("sub_dl|"))
async def handle_subtitle_download(callback: CallbackQuery, bot: Bot):
    parts = callback.data.split("|", 2)
    lang = parts[1]
    url = parts[2]
    await callback.answer("⏳ جاري التوليد...")
    status = await callback.message.reply("⏳ جاري توليد الترجمة...")

    async def _task():
        audio_path = None
        try:
            await status.edit_text("🎵 تحميل الصوت...")
            audio_path = await DownloadService.download_video(url, audio_only=True)

            await status.edit_text("🔤 التعرف على الكلام...")
            transcript = await AIService.transcribe(audio_path, language=None)
            segments = transcript.get("segments", [])

            if not segments:
                await status.edit_text("❌ لم يتم اكتشاف أي نص في الفيديو.")
                return

            # Translate if needed
            if lang != transcript.get("language", "?"):
                await status.edit_text("🌍 جاري الترجمة...")
                translated_segs = []
                for seg in segments:
                    t = await AIService.translate_text(seg["text"], target_lang=lang)
                    translated_segs.append({**seg, "text": t})
                segments = translated_segs

            srt = AIService.segments_to_srt(segments)
            vtt = AIService.segments_to_vtt(segments)

            srt_path = audio_path.with_suffix(".srt")
            vtt_path = audio_path.with_suffix(".vtt")
            srt_path.write_text(srt, encoding="utf-8")
            vtt_path.write_text(vtt, encoding="utf-8")

            await bot.send_document(callback.message.chat.id, FSInputFile(str(srt_path)),
                                    caption=f"📄 ترجمة SRT - {lang}")
            await bot.send_document(callback.message.chat.id, FSInputFile(str(vtt_path)),
                                    caption=f"📄 ترجمة VTT - {lang}")
            cleanup(srt_path, vtt_path)
            await status.delete()
        except Exception as e:
            await status.edit_text(f"❌ خطأ:\n`{str(e)[:200]}`", parse_mode="Markdown")
        finally:
            cleanup(audio_path)

    qm = get_queue_manager()
    if qm:
        await qm.enqueue(Job(make_job_id(), callback.from_user.id, callback.message.chat.id, _task()))
    else:
        await _task()


# ── Viral Clips ───────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("ai_clips|"))
async def handle_viral_clips(callback: CallbackQuery, bot: Bot):
    url = callback.data.split("|", 1)[1]
    await callback.answer("✂️ جاري التحليل...")
    status = await callback.message.reply(
        "⏳ جاري تحليل الفيديو واستخراج اللحظات الأفضل...\n"
        "قد يستغرق هذا بعض الوقت."
    )

    async def _task():
        video_path = None
        audio_path = None
        try:
            await status.edit_text("⬇️ تحميل الفيديو...")
            video_path = await DownloadService.download_video(url, quality="720p")

            await status.edit_text("🎵 تحليل الصوت...")
            audio_path = video_path.with_suffix(".mp3")
            audio_path = await FFmpegService.extract_audio(video_path, "mp3")

            await status.edit_text("🔤 تحويل الصوت لنص...")
            transcript = await AIService.transcribe(audio_path)

            await status.edit_text("🧠 الذكاء الاصطناعي يحلل أفضل اللحظات...")
            moments = await AIService.find_viral_moments(transcript.get("segments", []), count=3)

            if not moments:
                await status.edit_text("❌ لم يتم اكتشاف لحظات بارزة في هذا الفيديو.")
                return

            await status.edit_text(f"✂️ استخراج {len(moments)} كليب...")
            clips = await FFmpegService.extract_clips_batch(video_path, moments)

            for i, (clip, moment) in enumerate(zip(clips, moments), 1):
                if clip.exists():
                    await send_file_smart(
                        bot, callback.message.chat.id, clip,
                        caption=f"🎬 كليب {i}/{len(moments)}: *{moment.get('title', '')}*\n"
                                f"📌 {moment.get('reason', '')}",
                    )
                    cleanup(clip)

            await status.delete()
        except Exception as e:
            await status.edit_text(f"❌ خطأ:\n`{str(e)[:300]}`", parse_mode="Markdown")
        finally:
            cleanup(video_path, audio_path)

    qm = get_queue_manager()
    if qm:
        await qm.enqueue(Job(make_job_id(), callback.from_user.id, callback.message.chat.id, _task()))
    else:
        await _task()


# ── Audio Separation ──────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("ai_stems|"))
async def handle_stem_separation(callback: CallbackQuery, bot: Bot):
    url = callback.data.split("|", 1)[1]
    await callback.answer("🎚️ اختر نوع الصوت")
    await callback.message.reply(
        "🎚️ اختر ما تريد استخراجه:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🎤 صوت المتحدث فقط", callback_data=f"stem|vocals|{url[:80]}"),
                InlineKeyboardButton(text="🎵 موسيقى خلفية فقط", callback_data=f"stem|accompaniment|{url[:80]}"),
            ],
        ])
    )


@router.callback_query(F.data.startswith("stem|"))
async def handle_stem_download(callback: CallbackQuery, bot: Bot):
    parts = callback.data.split("|", 2)
    stem = parts[1]
    url = parts[2]
    await callback.answer("⏳")
    status = await callback.message.reply(f"⏳ جاري فصل الصوت ({stem})...")

    async def _task():
        video_path = None
        try:
            video_path = await DownloadService.download_video(url, audio_only=True)
            stem_path = await FFmpegService.separate_audio_stem(video_path, stem)
            await send_file_smart(bot, callback.message.chat.id, stem_path,
                                  caption=f"🎚️ {stem} - مفصول بالذكاء الاصطناعي")
            cleanup(stem_path)
            await status.delete()
        except Exception as e:
            await status.edit_text(f"❌ خطأ:\n`{str(e)[:200]}`", parse_mode="Markdown")
        finally:
            cleanup(video_path)

    qm = get_queue_manager()
    if qm:
        await qm.enqueue(Job(make_job_id(), callback.from_user.id, callback.message.chat.id, _task()))
    else:
        await _task()


def _fmt_time(s: int) -> str:
    m, sec = divmod(int(s), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"
