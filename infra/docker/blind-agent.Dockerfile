FROM node:22.18.0-bookworm-slim

RUN apt-get update \
    && apt-get install --yes --no-install-recommends python3 python3-pip python3-venv \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/blind-venv \
    && /opt/blind-venv/bin/pip install --no-cache-dir \
        polars==1.32.2 pydantic==2.13.4

ENV PATH="/opt/blind-venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1

USER 65532:65532
WORKDIR /workspace
