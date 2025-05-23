FROM ghcr.io/astral-sh/uv:python3.13-alpine
WORKDIR /app

COPY * /app

RUN addgroup -S rk9
RUN adduser -G rk9 -D -S rk9

RUN mkdir -p /data /app
RUN chown rk9:rk9 /data /app

ENV RK9_DATA_DIR=/data
ENV PATH="$PATH:/app/scripts"

USER rk9
CMD ["uv", "run", "main.py"]