import os
from dotenv import load_dotenv
from dataclasses import dataclass, field

load_dotenv()
from typing import Optional, List


@dataclass
class Settings:
    # ── Telegram ──────────────────────────────────────────────
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    ADMIN_IDS: List[int] = field(default_factory=lambda: [
        int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()
    ])

    # ── Redis / Queue ─────────────────────────────────────────
    REDIS_URL: Optional[str] = os.getenv("REDIS_URL")

    # ── AI APIs ───────────────────────────────────────────────
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
    ANTHROPIC_API_KEY: Optional[str] = os.getenv("ANTHROPIC_API_KEY")
    GROQ_API_KEY: Optional[str] = os.getenv("GROQ_API_KEY")          # fast Whisper + LLM
    ELEVENLABS_API_KEY: Optional[str] = os.getenv("ELEVENLABS_API_KEY")  # dubbing
    DEEPL_API_KEY: Optional[str] = os.getenv("DEEPL_API_KEY")        # translation

    # ── Additional AI Providers ───────────────────────────────
    OPENROUTER_API_KEY: Optional[str] = os.getenv("OPENROUTER_API_KEY")
    OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "mistralai/mixtral-8x7b-instruct")

    GEMINI_API_KEY: Optional[str] = os.getenv("GEMINI_API_KEY")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

    DEEPSEEK_API_KEY: Optional[str] = os.getenv("DEEPSEEK_API_KEY")
    DEEPSEEK_MODEL: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

    HUGGINGFACE_API_KEY: Optional[str] = os.getenv("HUGGINGFACE_API_KEY")
    HUGGINGFACE_MODEL: str = os.getenv("HUGGINGFACE_MODEL", "mistralai/Mistral-7B-Instruct-v0.3")

    # ── LLM Provider Priority ─────────────────────────────────
    # Comma-separated; first provider with a configured key wins.
    # Allowed: anthropic, openai, groq, openrouter, gemini, deepseek, huggingface
    LLM_PRIORITY: List[str] = field(default_factory=lambda: [
        p.strip() for p in os.getenv(
            "LLM_PRIORITY",
            "anthropic,openai,groq,openrouter,gemini,deepseek,huggingface"
        ).split(",") if p.strip()
    ])

    # ── Cloud Storage ─────────────────────────────────────────
    GDRIVE_CREDENTIALS_JSON: Optional[str] = os.getenv("GDRIVE_CREDENTIALS_JSON")
    DROPBOX_APP_KEY: Optional[str] = os.getenv("DROPBOX_APP_KEY")
    DROPBOX_APP_SECRET: Optional[str] = os.getenv("DROPBOX_APP_SECRET")

    # ── Download Engine ───────────────────────────────────────
    PROXY_LIST: List[str] = field(default_factory=lambda: [
        p for p in os.getenv("PROXY_LIST", "").split(",") if p.strip()
    ])
    MAX_FILE_SIZE_MB: int = int(os.getenv("MAX_FILE_SIZE_MB", "2000"))
    DOWNLOAD_DIR: str = os.getenv("DOWNLOAD_DIR", "/tmp/videobot_downloads")
    MAX_CONCURRENT_DOWNLOADS: int = int(os.getenv("MAX_CONCURRENT_DOWNLOADS", "5"))

    # ── Limits ────────────────────────────────────────────────
    MAX_VIDEO_DURATION_SECS: int = int(os.getenv("MAX_VIDEO_DURATION_SECS", "7200"))
    RATE_LIMIT_PER_USER: int = int(os.getenv("RATE_LIMIT_PER_USER", "10"))

    def __post_init__(self):
        import os as _os
        _os.makedirs(self.DOWNLOAD_DIR, exist_ok=True)
        if not self.BOT_TOKEN:
            raise ValueError("BOT_TOKEN environment variable is required!")

    def available_llm_providers(self) -> List[str]:
        """Return providers that have an API key set, in priority order."""
        key_map = {
            "anthropic": self.ANTHROPIC_API_KEY,
            "openai": self.OPENAI_API_KEY,
            "groq": self.GROQ_API_KEY,
            "openrouter": self.OPENROUTER_API_KEY,
            "gemini": self.GEMINI_API_KEY,
            "deepseek": self.DEEPSEEK_API_KEY,
            "huggingface": self.HUGGINGFACE_API_KEY,
        }
        return [p for p in self.LLM_PRIORITY if key_map.get(p)]


settings = Settings()
