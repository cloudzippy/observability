FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY implementations/sdk/gateway/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 10001 appuser
COPY --chown=appuser:appuser implementations/sdk/gateway/app.py ./app.py
COPY --chown=appuser:appuser implementations/sdk/common/telemetry.py ./common/telemetry.py
ENV PYTHONPATH=/app/common
USER appuser
EXPOSE 8000
CMD ["gunicorn", "--bind=0.0.0.0:8000", "--workers=2", "--access-logfile=-", "app:app"]
