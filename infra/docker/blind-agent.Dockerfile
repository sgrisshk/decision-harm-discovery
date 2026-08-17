# Pinned by digest, not just the mutable "22.18.0-bookworm-slim" tag: Docker Hub can repoint a
# tag to a rebuilt/repatched image under the same name, which would silently change the resolved
# base layer (and therefore this image's digest) between rebuilds. Re-resolve deliberately with
# `docker pull node:22.18.0-bookworm-slim && docker inspect --format='{{index .RepoDigests 0}}' \
# node:22.18.0-bookworm-slim` and update both the digest below and BLIND_AGENT_IMAGE if this ever
# needs to move.
FROM node:22.18.0-bookworm-slim@sha256:752ea8a2f758c34002a0461bd9f1cee4f9a3c36d48494586f60ffce1fc708e0e

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
