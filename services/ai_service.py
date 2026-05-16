import asyncio
import logging
import os
from pathlib import Path
from typing import Optional, Dict, Any, List
from config.settings import settings

logger = logging.getLogger(__name__)


class AIService:
    """Unified AI processing: transcription, summarization, subtitles, dubbing."""

    # ── Transcription ─────────────────────────────────────────────────────────

    @staticmethod
    async def transcribe(audio_path: Path, language: Optional[str] = None) -> Dict[str, Any]:
        """
        Transcribe audio using Groq Whisper (fast) or OpenAI Whisper as fallback.
        Returns: { "text": str, "segments": [...], "language": str }
        """
        loop = asyncio.get_event_loop()

        if settings.GROQ_API_KEY:
            try:
                result = await loop.run_in_executor(
                    None, lambda: _transcribe_groq(audio_path, language)
                )
                return result
            except Exception as e:
                logger.warning(f"Groq transcription failed: {e}, falling back to OpenAI")

        if settings.OPENAI_API_KEY:
            result = await loop.run_in_executor(
                None, lambda: _transcribe_openai(audio_path, language)
            )
            return result

        raise RuntimeError("No transcription API configured (set GROQ_API_KEY or OPENAI_API_KEY)")

    # ── Summarization ─────────────────────────────────────────────────────────

    @staticmethod
    async def summarize(text: str, language: str = "ar") -> str:
        """Return an executive summary in bullet points."""
        prompt = f"""أنت خبير في تلخيص المحتوى. لخص النص التالي بشكل نقاط واضحة وشاملة باللغة {'العربية' if language == 'ar' else language}.

النص:
{text[:8000]}

اكتب ملخصاً تنفيذياً يتضمن:
• أهم النقاط الرئيسية
• المفاهيم الجوهرية
• التوصيات أو الخلاصة (إن وجدت)
• أي روابط أو مصادر ذكرها المتحدث"""
        return await _call_llm(prompt)

    # ── Timestamps / Chapters ─────────────────────────────────────────────────

    @staticmethod
    async def generate_chapters(segments: List[Dict]) -> List[Dict]:
        """Group transcript segments into logical chapters with timestamps."""
        if not segments:
            return []

        segments_text = "\n".join(
            f"[{int(s['start'])}s] {s['text']}" for s in segments[:200]
        )
        prompt = f"""بناءً على مقاطع النص التالية من فيديو (مع الطوابع الزمنية بالثواني)، قم بتحديد الفصول الرئيسية.

{segments_text}

أجب بتنسيق JSON فقط:
[
  {{"start": 0, "title": "المقدمة", "description": "وصف قصير"}},
  ...
]"""

        raw = await _call_llm(prompt)
        import json, re
        match = re.search(r'\[.*\]', raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
        return []

    # ── Source Extraction ─────────────────────────────────────────────────────

    @staticmethod
    async def extract_sources(text: str) -> str:
        """Extract books, websites, tools mentioned in the transcript."""
        prompt = f"""من النص التالي، استخرج أي كتب، مواقع ويب، أدوات، تطبيقات، أو مصادر ذُكرت:

{text[:6000]}

اعرض النتائج كقائمة منظمة. إذا لم يوجد شيء، قل "لم تُذكر مصادر خارجية."."""
        return await _call_llm(prompt)

    # ── Subtitle Generation ───────────────────────────────────────────────────

    @staticmethod
    def segments_to_srt(segments: List[Dict]) -> str:
        """Convert transcript segments to SRT subtitle format."""
        lines = []
        for i, seg in enumerate(segments, 1):
            start = _seconds_to_srt_time(seg["start"])
            end = _seconds_to_srt_time(seg["end"])
            lines.append(f"{i}\n{start} --> {end}\n{seg['text'].strip()}\n")
        return "\n".join(lines)

    @staticmethod
    def segments_to_vtt(segments: List[Dict]) -> str:
        """Convert transcript segments to WebVTT format."""
        lines = ["WEBVTT\n"]
        for seg in segments:
            start = _seconds_to_vtt_time(seg["start"])
            end = _seconds_to_vtt_time(seg["end"])
            lines.append(f"{start} --> {end}\n{seg['text'].strip()}\n")
        return "\n".join(lines)

    # ── Translation ───────────────────────────────────────────────────────────

    @staticmethod
    async def translate_text(text: str, target_lang: str = "ar") -> str:
        """Translate text using DeepL (preferred) or LLM fallback."""
        if settings.DEEPL_API_KEY:
            return await _translate_deepl(text, target_lang)

        prompt = f"ترجم النص التالي إلى اللغة '{target_lang}' ترجمة احترافية دقيقة:\n\n{text}"
        return await _call_llm(prompt)

    # ── Viral Clip Analysis ───────────────────────────────────────────────────

    @staticmethod
    async def find_viral_moments(segments: List[Dict], count: int = 3) -> List[Dict]:
        """Identify the most engaging/shareable moments in the video."""
        segments_text = "\n".join(
            f"[{int(s['start'])}s-{int(s['end'])}s] {s['text']}" for s in segments[:300]
        )
        prompt = f"""أنت محلل محتوى متخصص في اكتشاف اللحظات الفيروسية.

من مقاطع الفيديو التالية، حدد {count} لحظات هي الأكثر إثارة، أهمية، أو قابلية للمشاركة:

{segments_text}

أجب بـ JSON فقط:
[
  {{
    "start": 120,
    "end": 180,
    "reason": "لماذا هذه اللحظة مهمة",
    "title": "عنوان قصير جذاب للكليب"
  }}
]"""

        raw = await _call_llm(prompt)
        import json, re
        match = re.search(r'\[.*\]', raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
        return []

    # ── AI Search Helper ──────────────────────────────────────────────────────

    @staticmethod
    async def search_to_query(user_request: str) -> Dict[str, str]:
        """Convert a natural-language request to a YouTube search query + quality."""
        prompt = f"""المستخدم يريد: "{user_request}"

استخرج معلومتين:
1. استعلام بحث YouTube مثالي (بالإنجليزية للحصول على أفضل نتائج)
2. جودة التحميل المطلوبة (best/1080p/720p/480p/audio)

أجب بـ JSON فقط: {{"query": "...", "quality": "..."}}"""

        raw = await _call_llm(prompt)
        import json, re
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
        return {"query": user_request, "quality": "720p"}

    # ── Provider Status ───────────────────────────────────────────────────────

    @staticmethod
    def get_provider_status() -> Dict[str, bool]:
        """Return which AI providers are configured."""
        return {
            "anthropic": bool(settings.ANTHROPIC_API_KEY),
            "openai": bool(settings.OPENAI_API_KEY),
            "groq": bool(settings.GROQ_API_KEY),
            "openrouter": bool(settings.OPENROUTER_API_KEY),
            "gemini": bool(settings.GEMINI_API_KEY),
            "deepseek": bool(settings.DEEPSEEK_API_KEY),
            "huggingface": bool(settings.HUGGINGFACE_API_KEY),
            "deepl": bool(settings.DEEPL_API_KEY),
            "elevenlabs": bool(settings.ELEVENLABS_API_KEY),
        }


# ── Internal helpers ───────────────────────────────────────────────────────────

async def _call_llm(prompt: str) -> str:
    """
    Call the best available LLM following the priority order in settings.LLM_PRIORITY.
    Falls back to the next provider if one fails.
    """
    loop = asyncio.get_event_loop()

    provider_fn = {
        "anthropic": lambda: _call_anthropic(prompt),
        "openai":    lambda: _call_openai(prompt),
        "groq":      lambda: _call_groq_llm(prompt),
        "openrouter":lambda: _call_openrouter(prompt),
        "gemini":    lambda: _call_gemini(prompt),
        "deepseek":  lambda: _call_deepseek(prompt),
        "huggingface":lambda: _call_huggingface(prompt),
    }

    available = settings.available_llm_providers()
    if not available:
        raise RuntimeError(
            "No LLM API configured. Set at least one of: "
            "ANTHROPIC_API_KEY, OPENAI_API_KEY, GROQ_API_KEY, "
            "OPENROUTER_API_KEY, GEMINI_API_KEY, DEEPSEEK_API_KEY, HUGGINGFACE_API_KEY"
        )

    last_error = None
    for provider in available:
        fn = provider_fn.get(provider)
        if not fn:
            continue
        try:
            logger.debug(f"Trying LLM provider: {provider}")
            result = await loop.run_in_executor(None, fn)
            return result
        except Exception as e:
            logger.warning(f"LLM provider '{provider}' failed: {e}")
            last_error = e

    raise RuntimeError(f"All LLM providers failed. Last error: {last_error}")


# ── Provider implementations ───────────────────────────────────────────────────

def _call_anthropic(prompt: str) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


def _call_openai(prompt: str) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=2048,
    )
    return resp.choices[0].message.content


def _call_groq_llm(prompt: str) -> str:
    from groq import Groq
    client = Groq(api_key=settings.GROQ_API_KEY)
    resp = client.chat.completions.create(
        model="llama3-70b-8192",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=2048,
    )
    return resp.choices[0].message.content


def _call_openrouter(prompt: str) -> str:
    """
    OpenRouter: OpenAI-compatible API supporting 200+ models.
    Set OPENROUTER_MODEL to any model slug from https://openrouter.ai/models
    Examples: mistralai/mixtral-8x7b-instruct, meta-llama/llama-3-70b-instruct,
              google/gemma-2-27b-it, anthropic/claude-3-haiku
    """
    from openai import OpenAI
    client = OpenAI(
        api_key=settings.OPENROUTER_API_KEY,
        base_url="https://openrouter.ai/api/v1",
    )
    resp = client.chat.completions.create(
        model=settings.OPENROUTER_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=2048,
        extra_headers={
            "HTTP-Referer": "https://github.com/videobot",
            "X-Title": "VideoBot",
        },
    )
    return resp.choices[0].message.content


def _call_gemini(prompt: str) -> str:
    """
    Google Gemini via the official google-generativeai SDK.
    Set GEMINI_MODEL to: gemini-1.5-flash (default), gemini-1.5-pro, gemini-1.0-pro, etc.
    """
    import google.generativeai as genai
    genai.configure(api_key=settings.GEMINI_API_KEY)
    model = genai.GenerativeModel(settings.GEMINI_MODEL)
    response = model.generate_content(
        prompt,
        generation_config=genai.GenerationConfig(max_output_tokens=2048),
    )
    return response.text


def _call_deepseek(prompt: str) -> str:
    """
    DeepSeek via their OpenAI-compatible API.
    Set DEEPSEEK_MODEL to: deepseek-chat (default) or deepseek-reasoner (R1).
    """
    from openai import OpenAI
    client = OpenAI(
        api_key=settings.DEEPSEEK_API_KEY,
        base_url="https://api.deepseek.com/v1",
    )
    resp = client.chat.completions.create(
        model=settings.DEEPSEEK_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=2048,
    )
    return resp.choices[0].message.content


def _call_huggingface(prompt: str) -> str:
    """
    Hugging Face Inference API (serverless, no dedicated endpoint needed).
    Set HUGGINGFACE_MODEL to any chat/text-generation model on HF Hub.
    Examples: mistralai/Mistral-7B-Instruct-v0.3, HuggingFaceH4/zephyr-7b-beta,
              microsoft/Phi-3-mini-4k-instruct
    """
    import httpx
    headers = {
        "Authorization": f"Bearer {settings.HUGGINGFACE_API_KEY}",
        "Content-Type": "application/json",
    }
    # Use the chat completions endpoint (works for instruct models)
    url = f"https://api-inference.huggingface.co/models/{settings.HUGGINGFACE_MODEL}/v1/chat/completions"
    payload = {
        "model": settings.HUGGINGFACE_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 2048,
    }
    with httpx.Client(timeout=60) as client:
        resp = client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()

    # Handle both chat-completions and text-generation response shapes
    if "choices" in data:
        return data["choices"][0]["message"]["content"]
    if isinstance(data, list) and data:
        return data[0].get("generated_text", str(data[0]))
    raise RuntimeError(f"Unexpected Hugging Face response: {data}")


# ── Transcription ──────────────────────────────────────────────────────────────

def _transcribe_groq(audio_path: Path, language: Optional[str]) -> Dict:
    from groq import Groq
    client = Groq(api_key=settings.GROQ_API_KEY)
    with open(audio_path, "rb") as f:
        resp = client.audio.transcriptions.create(
            file=(audio_path.name, f),
            model="whisper-large-v3",
            language=language,
            response_format="verbose_json",
        )
    return {
        "text": resp.text,
        "segments": [{"start": s.start, "end": s.end, "text": s.text} for s in (resp.segments or [])],
        "language": resp.language or language or "auto",
    }


def _transcribe_openai(audio_path: Path, language: Optional[str]) -> Dict:
    from openai import OpenAI
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    with open(audio_path, "rb") as f:
        resp = client.audio.transcriptions.create(
            file=f,
            model="whisper-1",
            language=language,
            response_format="verbose_json",
        )
    return {
        "text": resp.text,
        "segments": [{"start": s.start, "end": s.end, "text": s.text} for s in (resp.segments or [])],
        "language": getattr(resp, "language", language or "auto"),
    }


# ── Translation ────────────────────────────────────────────────────────────────

async def _translate_deepl(text: str, target_lang: str) -> str:
    import httpx
    lang_map = {"ar": "AR", "en": "EN-US", "fr": "FR", "de": "DE", "es": "ES"}
    tl = lang_map.get(target_lang, target_lang.upper())
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api-free.deepl.com/v2/translate",
            headers={"Authorization": f"DeepL-Auth-Key {settings.DEEPL_API_KEY}"},
            data={"text": text, "target_lang": tl},
        )
        data = resp.json()
        return data["translations"][0]["text"]


# ── Time helpers ───────────────────────────────────────────────────────────────

def _seconds_to_srt_time(s: float) -> str:
    h, rem = divmod(int(s), 3600)
    m, sec = divmod(rem, 60)
    ms = int((s - int(s)) * 1000)
    return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"


def _seconds_to_vtt_time(s: float) -> str:
    return _seconds_to_srt_time(s).replace(",", ".")
