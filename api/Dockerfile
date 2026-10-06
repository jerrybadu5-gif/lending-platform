FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install "fastapi>=0.115" "uvicorn[standard]>=0.30" "pydantic>=2.8" \
    "pydantic-settings>=2.4" "httpx>=0.27" "itsdangerous>=2.2" "tzdata>=2024.1"
COPY app ./app
COPY policy.json ./policy.json
RUN useradd --system --uid 10001 mclender
USER mclender
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/health')"
# One worker: sign-in codes and rate limits are kept in memory (see app/security.py).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers"]
