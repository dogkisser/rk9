FROM ghcr.io/astral-sh/uv:python3.13-alpine AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

ENV UV_PYTHON_INSTALL_DIR=/python
ENV UV_PYTHON_PREFERENCE=only-managed

RUN uv python install 3.13

WORKDIR /app
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

FROM alpine:latest

LABEL org.opencontainers.image.description="Discord bot for subscribing to e621 tags"

COPY --from=builder --chown=python:python /python /python
COPY --from=builder --chown=app:app /app /app

RUN addgroup -S rk9
RUN adduser -G rk9 -D -S rk9

RUN mkdir -p /data

RUN chown rk9:rk9 /data /app
RUN chmod 700 /data /app

ENV RK9_DATA_DIR=/data
RUN chmod +x /app/scripts/*
ENV PATH="$PATH:/app/scripts"

USER rk9
CMD ["/app/.venv/bin/python3.13", "/app/main.py"]