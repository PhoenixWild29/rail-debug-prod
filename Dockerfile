# Multi-stage Dockerfile for Rail Debug (analyzer + server)
# Python 3.12 slim, optimized for prod

FROM python:3.12-slim AS builder

WORKDIR /app

# Copy only requirements first for caching
COPY requirements.txt .

# Install deps as non-root, no cache
RUN pip install --no-cache-dir --user -r requirements.txt

# Runtime image
FROM python:3.12-slim

WORKDIR /app

# Copy installed deps
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Copy app
COPY . .

# Create non-root user
RUN useradd --create-home appuser && chown -R appuser:appuser /app && chmod -R a+rX /root/.local
USER appuser

EXPOSE 8000

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]