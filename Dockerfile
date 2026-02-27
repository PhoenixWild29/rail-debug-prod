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

# Create non-root user first so we can own the deps directory
RUN useradd --create-home appuser

# Copy installed deps into appuser's home (avoids /root traversal permission issue)
COPY --from=builder /root/.local /home/appuser/.local
ENV PATH=/home/appuser/.local/bin:$PATH

# Copy app
COPY . .

# Own everything
RUN chown -R appuser:appuser /app /home/appuser/.local

USER appuser

EXPOSE 8000

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
