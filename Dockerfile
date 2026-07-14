FROM python:3.12.11-slim-bookworm
ARG RCLONE_VERSION=1.74.4
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl unzip \
    && arch="$(dpkg --print-architecture)" \
    && case "$arch" in amd64) rarch=amd64;; arm64) rarch=arm64;; *) exit 1;; esac \
    && curl -fsSLo /tmp/rclone.zip "https://downloads.rclone.org/v${RCLONE_VERSION}/rclone-v${RCLONE_VERSION}-linux-${rarch}.zip" \
    && unzip /tmp/rclone.zip -d /tmp \
    && install -m 0755 /tmp/rclone-*/rclone /usr/local/bin/rclone \
    && rm -rf /var/lib/apt/lists/* /tmp/rclone* \
    && groupadd --system --gid 10001 uploader && useradd --system --uid 10001 --gid uploader --home /app uploader
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY scripts ./scripts
RUN chmod 0555 scripts/*.sh && mkdir -p /data/downloads /data/state /data/session /data/logs /config/rclone \
    && chown -R uploader:uploader /app /data
USER uploader
ENTRYPOINT ["/app/scripts/entrypoint.sh"]
CMD ["python", "-m", "app.main"]
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 CMD ["/app/scripts/healthcheck.sh"]

