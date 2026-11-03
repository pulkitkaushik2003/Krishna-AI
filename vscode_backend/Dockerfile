FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /app app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=app:app app_retry.py index-pro.html ./

USER app

EXPOSE 2000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:2000/health', timeout=3)"

CMD ["gunicorn", "--bind", "0.0.0.0:2000", "--worker-class", "gthread", "--workers", "1", "--threads", "8", "--timeout", "120", "app_retry:app"]
