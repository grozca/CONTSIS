FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    STREAMLIT_SERVER_HEADLESS=true \
    CONTSIS_HOME=/app/runtime \
    CONTSIS_SERVER_HOST=0.0.0.0 \
    CONTSIS_SERVER_PORT=8501 \
    CONTSIS_OPEN_BROWSER=0

WORKDIR /app

COPY requirements.txt ./

RUN apt-get update && \
    apt-get install -y --no-install-recommends fonts-dejavu-core && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --upgrade pip && \
    pip install -r requirements.txt

COPY . .

RUN mkdir -p /app/runtime/data/config /app/runtime/alertas/config /app/logs

EXPOSE 8501

CMD ["python", "docker_entrypoint.py"]
