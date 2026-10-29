FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/home/codex
WORKDIR /opt/worker
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates nodejs npm \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g @openai/codex
COPY worker/codex_worker.py /opt/worker/codex_worker.py
RUN groupadd -g 10002 codex && useradd -m -u 10002 -g 10002 codex \
    && mkdir -p /home/codex/.codex && chown -R codex:codex /home/codex
USER 10002:10002
EXPOSE 8765
CMD ["python", "/opt/worker/codex_worker.py"]
