FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        mtr-tiny \
        iputils-ping \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY app.py /app/app.py

RUN useradd --create-home --uid 10001 appuser
USER appuser

ENV CONFIG_PATH=/etc/prometheus-traceroute-exporter/config.yml
ENV LISTEN_ADDRESS=0.0.0.0
ENV LISTEN_PORT=9888
ENV LOG_LEVEL=INFO

EXPOSE 9888

ENTRYPOINT ["python", "/app/app.py"]
