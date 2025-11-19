# Use official lightweight Python image
FROM python:3.11-slim

# Install system dependencies required for pdf2image and audio
RUN apt-get update && apt-get install -y \
    poppler-utils \
    ffmpeg \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# Set work directory
ENV APP_HOME /app
WORKDIR $APP_HOME

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . ./

# Run Gunicorn with long timeout for large files
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 3600 main:app
