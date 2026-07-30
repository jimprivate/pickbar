FROM ghcr.io/charmbracelet/vhs:latest
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*
