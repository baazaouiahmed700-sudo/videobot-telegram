import asyncio
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Callable, Coroutine, Any, Dict, Deque
from aiogram import Bot
from config.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class Job:
    job_id: str
    user_id: int
    chat_id: int
    coro: Coroutine
    created_at: float = field(default_factory=time.time)


class QueueManager:
    def __init__(self, bot: Bot):
        self.bot = bot
        self._queue: asyncio.Queue = asyncio.Queue()
        self._semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_DOWNLOADS)
        self._user_job_count: Dict[int, int] = defaultdict(int)
        self._rate_tracker: Dict[int, Deque[float]] = defaultdict(lambda: deque(maxlen=settings.RATE_LIMIT_PER_USER))

    async def start(self):
        """Start the queue worker loop."""
        logger.info(f"Queue manager started (max concurrent: {settings.MAX_CONCURRENT_DOWNLOADS})")
        while True:
            try:
                job: Job = await self._queue.get()
                asyncio.create_task(self._process(job))
            except Exception as e:
                logger.error(f"Queue error: {e}")

    async def _process(self, job: Job):
        async with self._semaphore:
            try:
                await job.coro
            except Exception as e:
                logger.error(f"Job {job.job_id} failed: {e}")
                try:
                    await self.bot.send_message(
                        job.chat_id,
                        f"❌ حدث خطأ أثناء معالجة طلبك:\n`{str(e)[:200]}`",
                        parse_mode="Markdown"
                    )
                except Exception:
                    pass
            finally:
                self._user_job_count[job.user_id] = max(0, self._user_job_count[job.user_id] - 1)
                self._queue.task_done()

    def is_rate_limited(self, user_id: int) -> bool:
        """Check if user exceeded hourly rate limit."""
        now = time.time()
        timestamps = self._rate_tracker[user_id]
        # Remove timestamps older than 1 hour
        while timestamps and now - timestamps[0] > 3600:
            timestamps.popleft()
        return len(timestamps) >= settings.RATE_LIMIT_PER_USER

    async def enqueue(self, job: Job) -> bool:
        """Add job to queue. Returns False if rate limited."""
        if self.is_rate_limited(job.user_id):
            return False
        self._rate_tracker[job.user_id].append(time.time())
        self._user_job_count[job.user_id] += 1
        await self._queue.put(job)
        return True

    def queue_size(self) -> int:
        return self._queue.qsize()

    def user_jobs(self, user_id: int) -> int:
        return self._user_job_count[user_id]


# Global instance
_manager: QueueManager = None


def get_queue_manager() -> QueueManager:
    return _manager


def set_queue_manager(m: QueueManager):
    global _manager
    _manager = m
