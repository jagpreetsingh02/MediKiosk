FROM python:3.12-slim

# tesseract is a real dependency, not an optional extra: it is the only OCR backend that can
# read a scan or a phone photo, which is what patients actually bring. `hin` adds Devanagari.
RUN apt-get update && apt-get install -y --no-install-recommends \
      tesseract-ocr tesseract-ocr-hin tesseract-ocr-tam \
      curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
COPY config ./config
COPY data ./data

ENV PYTHONPATH=/app PYTHONUNBUFFERED=1

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD curl -fsS http://localhost:8000/health || exit 1

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
