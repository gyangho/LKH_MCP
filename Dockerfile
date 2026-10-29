FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates libaio1 libnsl2 \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt && pip install --no-cache-dir graphifyy
COPY server.py /app/server.py
COPY src /app/src
COPY web /app/web
COPY vendor /app/vendor
RUN test -f /app/vendor/ui-ux-pro-max-skill/src/ui-ux-pro-max/scripts/search.py
RUN groupadd -g 10001 mcp && useradd -m -u 10001 -g 10001 mcp \
    && mkdir -p /app/data && chown -R mcp:mcp /app/data
USER 10001:10001
EXPOSE 8000
CMD ["python","server.py"]
