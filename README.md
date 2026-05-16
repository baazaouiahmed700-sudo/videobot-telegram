# 🚀 Advanced Video Downloader Bot

بوت تيليغرام متقدم لتحميل الفيديوهات مع ذكاء اصطناعي.

## الميزات

- ⬇️ تحميل من +1000 موقع (YouTube, TikTok, Instagram, X, Facebook...)
- 🎬 دعم جودة حتى 8K مع دمج صوت/فيديو تلقائي
- 📝 تلخيص ذكي بالذكاء الاصطناعي + فصول زمنية
- 🌍 ترجمة وتوليد ملفات SRT/VTT
- ✂️ استخراج الكليبات الفيروسية تلقائياً
- 🎚️ فصل الصوت (صوت المتحدث / موسيقى خلفية)
- ☁️ رفع مباشر إلى Google Drive / Dropbox / Mega
- 🔍 بحث ذكي بالوصف الطبيعي
- ⚡ نظام طابور لمعالجة مئات الطلبات

---

## النشر على Railway

### 1. إنشاء البوت

1. افتح [@BotFather](https://t.me/BotFather) في تيليغرام
2. أرسل `/newbot` واتبع التعليمات
3. احفظ الـ **Token**

### 2. رفع الكود

```bash
git init
git add .
git commit -m "initial commit"
# ارفع على GitHub
```

### 3. النشر على Railway

1. اذهب إلى [railway.app](https://railway.app)
2. اضغط **New Project → Deploy from GitHub Repo**
3. اختر المستودع
4. أضف **Redis** من قائمة الـ Add-ons

### 4. إعداد المتغيرات

في Railway → Variables، أضف:

```
BOT_TOKEN=your_token_here
ADMIN_IDS=your_telegram_id

# أضف على الأقل واحد من هذه:
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GROQ_API_KEY=gsk_...

# Redis (يُضاف تلقائياً عند إضافة Redis Add-on):
REDIS_URL=${{Redis.REDIS_URL}}
```

### 5. النشر

Railway سيبني الـ Docker image تلقائياً وينشر البوت.

---

## الاستخدام

| الأمر | الوظيفة |
|-------|---------|
| أرسل رابط | تحليل وعرض خيارات التحميل |
| `/search` | بحث ذكي بالوصف |
| `/cloud` | رفع إلى السحابة مباشرة |
| `/status` | حالة الطابور |
| `/admin` | لوحة تحكم (للمشرفين) |

---

## البنية التقنية

```
videobot/
├── main.py                 # نقطة الدخول
├── config/
│   └── settings.py         # الإعدادات من env vars
├── handlers/
│   ├── download.py         # التحميل الأساسي
│   ├── ai_features.py      # الذكاء الاصطناعي
│   ├── search.py           # البحث الذكي
│   ├── cloud.py            # الرفع السحابي
│   └── admin.py            # إدارة البوت
├── services/
│   ├── downloader.py       # محرك yt-dlp
│   ├── ai_service.py       # Whisper + LLM
│   ├── ffmpeg_service.py   # معالجة الفيديو
│   └── cloud_service.py    # Google Drive, Dropbox, Mega
└── utils/
    ├── helpers.py          # أدوات مساعدة
    └── queue_manager.py    # نظام الطابور
```

## متطلبات النظام

- Python 3.11+
- FFmpeg (مثبت في Docker)
- Redis (اختياري لكن موصى به)
