import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from services.cloud_service import CloudService
from services.downloader import DownloadService
from utils.helpers import extract_url, cleanup, make_job_id
from utils.queue_manager import get_queue_manager, Job

logger = logging.getLogger(__name__)
router = Router()


class CloudState(StatesGroup):
    waiting_for_url = State()
    waiting_for_dropbox_token = State()


@router.message(Command("cloud"))
async def cmd_cloud(msg: Message, state: FSMContext):
    await msg.answer(
        "☁️ *الرفع السحابي المباشر*\n\n"
        "أرسل رابط الفيديو وسيتم رفعه مباشرة إلى السحابة\n"
        "دون استهلاك إنترنتك!\n\n"
        "أرسل الرابط الآن:",
        parse_mode="Markdown"
    )
    await state.set_state(CloudState.waiting_for_url)


@router.message(CloudState.waiting_for_url)
async def handle_cloud_url(msg: Message, state: FSMContext):
    url = extract_url(msg.text)
    if not url:
        await msg.answer("❌ لم أتعرف على رابط. حاول مجدداً.")
        return

    await state.update_data(cloud_url=url)
    await state.clear()

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📁 Google Drive", callback_data=f"cloud|gdrive|{url[:100]}"),
            InlineKeyboardButton(text="📦 Dropbox", callback_data=f"cloud|dropbox|{url[:100]}"),
        ],
        [
            InlineKeyboardButton(text="🔷 Mega", callback_data=f"cloud|mega|{url[:100]}"),
        ]
    ])

    await msg.answer(
        "☁️ اختر وجهة الرفع:",
        reply_markup=keyboard
    )


@router.callback_query(F.data.startswith("cloud|"))
async def handle_cloud_upload(callback: CallbackQuery, bot: Bot):
    parts = callback.data.split("|", 2)
    service = parts[1]
    url = parts[2]
    await callback.answer("☁️ جاري المعالجة...")
    status = await callback.message.reply("⏳ جاري التحميل والرفع السحابي...")

    async def _task():
        file_path = None
        try:
            await status.edit_text("⬇️ تحميل الفيديو...")
            file_path = await DownloadService.download_video(url, quality="best")

            await status.edit_text(f"☁️ رفع إلى {service}...")

            link = None
            if service == "gdrive":
                link = await CloudService.upload_to_gdrive(file_path)
            elif service == "dropbox":
                await callback.message.reply(
                    "🔑 أرسل Dropbox Access Token الخاص بك:"
                )
                # Simplified: in production, use FSM to collect token
                await status.edit_text("⚠️ Dropbox يتطلب إرسال Access Token أولاً.\nاستخدم /cloud مع Dropbox Token.")
                return
            elif service == "mega":
                await status.edit_text("⚠️ MEGA يتطلب بيانات الحساب. تواصل مع المشرف.")
                return

            if link:
                await callback.message.reply(
                    f"✅ *تم الرفع بنجاح!*\n\n"
                    f"🔗 [افتح الملف]({link})",
                    parse_mode="Markdown"
                )
                await status.delete()

        except Exception as e:
            await status.edit_text(f"❌ خطأ في الرفع:\n`{str(e)[:200]}`", parse_mode="Markdown")
        finally:
            cleanup(file_path)

    qm = get_queue_manager()
    if qm:
        await qm.enqueue(Job(make_job_id(), callback.from_user.id, callback.message.chat.id, _task()))
    else:
        await _task()
