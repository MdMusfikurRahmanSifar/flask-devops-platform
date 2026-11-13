FROM python:3.12-slim AS builder
COPY app/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt --target /install

FROM python:3.12-slim

LABEL org.opencontainers.image.title="flask-devops-platform" \
      org.opencontainers.image.description="Flask app with /, /health, /metrics" \
      org.opencontainers.image.version="1.0.0" \
      org.opencontainers.image.source="https://github.com/MdMusfikurRahmanSifar/flask-devops-platform" \
      org.opencontainers.image.licenses="MIT"

COPY --from=builder /install /install
ENV PYTHONPATH=/install:/app \
    PATH="/install/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY app/ /app/app/

RUN adduser --system --no-create-home --uid 1000 appuser && chown -R appuser /app
USER appuser
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8080/health',timeout=3).status==200 else 1)"

CMD ["gunicorn", "app.main:app", "--bind", "0.0.0.0:8080", "--workers", "2", "--graceful-timeout", "10"]
