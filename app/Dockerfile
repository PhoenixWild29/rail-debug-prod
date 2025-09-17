# Multi-stage Dockerfile for Rail Debugging Assistant (production-ready)
FROM python:3.12-slim AS builder
WORKDIR /app

# System deps (optional, keep minimal)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --user --no-cache-dir -r requirements.txt \
    && python - <<'PY'
from sentence_transformers import SentenceTransformer
SentenceTransformer('all-MiniLM-L6-v2')
print('Model cached')
PY

FROM python:3.12-slim
WORKDIR /app

# Create non-root user
RUN useradd -m appuser

# Copy Python deps
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Copy application code
COPY . .

USER appuser
EXPOSE 8000

# Use a robust ASGI server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
