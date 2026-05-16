import logging
from aiogram import Router, F, Bot
from aiogram.types import Message
from aiogram.filters import Command
from config.settings import settings
from services.ai_service import AIService
from utils.queue_manager import get_queue_manager

logger = logging.getLogger(__name__)
router = Router()


def is_admin(user_id: int) -> bool:
    return user_id in settings.ADMIN_IDS


@router.message(Command("admin"))
async def cmd_admin(msg: Message):
    if not is_admin(msg.from_user.id):
        return

    qm = get_queue_manager()
    queue_info = f"• الطابور: {qm.queue_size() if qm else 'N/A'} مهام معلقة"

    await msg.answer(
        f"🔧 *لوحة تحكم المشرف*\n\n"
        f"{queue_info}\n\n"
        f"**الأوامر:**\n"
        f"/broadcast - إرسال رسالة جماعية\n"
        f"/setproxy - تحديث قائمة الـ Proxies\n"
        f"/stats - إحصائيات التحميل\n"
        f"/ai\\_status - حالة مزودي الذكاء الاصطناعي",
        parse_mode="Markdown"
    )


@router.message(Command("stats"))
async def cmd_stats(msg: Message):
    if not is_admin(msg.from_user.id):
        return

    qm = get_queue_manager()
    await msg.answer(
        f"📊 *إحصائيات النظام*\n\n"
        f"• حالة الطابور: {'🟢 نشط' if qm else '⚪ معطل'}\n"
        f"• الطلبات المعلقة: {qm.queue_size() if qm else 0}\n"
        f"• الحد الأقصى المتزامن: {settings.MAX_CONCURRENT_DOWNLOADS}\n"
        f"• حجم التحميل الأقصى: {settings.MAX_FILE_SIZE_MB} MB\n"
        f"• الـ Proxies المتاحة: {len(settings.PROXY_LIST)}",
        parse_mode="Markdown"
    )


@router.message(Command("ai_status"))
async def cmd_ai_status(msg: Message):
    """Show which AI providers are configured and active."""
    if not is_admin(msg.from_user.id):
        return

    status = AIService.get_provider_status()
    priority = settings.available_llm_providers()

    icons = {True: "✅", False: "❌"}

    llm_lines = "\n".join(
        f"  {icons[configured]} {name}"
        for name, configured in status.items()
        if name not in ("deepl", "elevenlabs")
    )

    tools_lines = (
        f"  {icons[status['deepl']]} DeepL (ترجمة)\n"
        f"  {icons[status['elevenlabs']]} ElevenLabs (دبلجة)"
    )

    active = priority[0] if priority else "لا يوجد"
    priority_str = " → ".join(priority) if priority else "غير مُعيَّن"

    await msg.answer(
        f"🤖 *حالة مزودي الذكاء الاصطناعي*\n\n"
        f"**مزودات LLM:**\n{llm_lines}\n\n"
        f"**أدوات أخرى:**\n{tools_lines}\n\n"
        f"**المزود النشط:** `{active}`\n"
        f"**ترتيب الأولوية:** `{priority_str}`\n\n"
        f"_لتغيير الأولوية، عيّن متغير `LLM_PRIORITY` في البيئة._",
        parse_mode="Markdown"
    )
