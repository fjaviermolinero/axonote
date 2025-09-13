FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    libgstreamer1.0-0 \
    tesseract-ocr \
    tesseract-ocr-ita \
    tesseract-ocr-eng \
    tesseract-ocr-spa \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY apps/api/pyproject.toml apps/api/poetry.lock* ./
RUN pip install poetry && \
    poetry config virtualenvs.create false && \
    poetry install --only main --no-root

# Copy application code
COPY apps/api/ .

# Create non-root user and set up directories
RUN useradd --create-home --shell /bin/bash app && \
    mkdir -p /app/logs && \
    chown -R app:app /app
USER app

# Expose port
EXPOSE 8000

# Default command
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
