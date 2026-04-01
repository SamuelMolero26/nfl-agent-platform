FROM python:3.12-slim

WORKDIR /app

COPY nanoclaw_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY nanoclaw_service/ ./nanoclaw_service/

RUN adduser --disabled-password --gecos "" appuser && \
    chown -R appuser /app
USER appuser

EXPOSE 8002

CMD ["uvicorn", "nanoclaw_service.main:app", "--host", "0.0.0.0", "--port", "8002"]
