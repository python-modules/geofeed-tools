# syntax=docker/dockerfile:1.7

ARG BUILDER_IMAGE=python:3.13-slim
ARG RUNTIME_IMAGE=gcr.io/distroless/python3-debian13:nonroot

FROM ${BUILDER_IMAGE} AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

# hadolint ignore=DL3013
RUN python -m pip install --upgrade pip \
    && python -m pip install --target=/opt/site-packages ".[cli]"

FROM ${RUNTIME_IMAGE}

ENV PYTHONPATH=/opt/site-packages \
    PYTHONUNBUFFERED=1

WORKDIR /work

COPY --from=builder /opt/site-packages /opt/site-packages

ENTRYPOINT ["/usr/bin/python3", "-m", "geofeed_tools.cli"]
CMD ["--help"]