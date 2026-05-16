import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.fsm.storage.memory import MemoryStorage
from config.settings import settings
from handlers import download, ai_features, admin, search, cloud
from utils.queue_manager import QueueManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def main():
    bot = Bot(token=settings.BOT_TOKEN)

    if settings.REDIS_URL:
        storage = RedisStorage.from_url(settings.REDIS_URL)
        logger.info("Using Redis storage")
    else:
        storage = MemoryStorage()
        logger.info("Using Memory storage")

    dp = Dispatcher(storage=storage)

    # Register all routers
    dp.include_router(download.router)
    dp.include_router(ai_features.router)
    dp.include_router(search.router)
    dp.include_router(cloud.router)
    dp.include_router(admin.router)

    # Start queue manager
    queue_manager = QueueManager(bot)
    asyncio.create_task(queue_manager.start())

    logger.info("🤖 Advanced Video Downloader Bot is starting...")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
