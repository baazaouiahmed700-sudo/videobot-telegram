FROM python:3.11-slim

# Install system deps: ffmpeg + git (for yt-dlp updates)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (cache layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Create download temp dir
RUN mkdir -p /tmp/videobot_downloads

# Keep yt-dlp updated on build
RUN pip install -U yt-dlp

ENV PYTHONUNBUFFERED=1
ENV DOWNLOAD_DIR=/tmp/videobot_downloads

CMD ["python", "main.py"]
