FROM python:3.12-slim AS builder
COPY app/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt --target /install

FROM python:3.12-slim
COPY --from=builder /install /install
ENV PYTHONPATH=/install
WORKDIR /app
COPY app/ /app/app/
RUN adduser --system --no-create-home appuser && chown -R appuser /app
USER appuser
EXPOSE 8080
CMD ["gunicorn", "app.main:app", "--bind", "0.0.0.0:8080"]
