FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project

COPY src ./src
RUN uv sync --locked --no-dev

RUN mkdir -p /data && chown -R nobody:nogroup /data
USER nobody

EXPOSE 8000
CMD ["uvicorn", "faultweaver.app:app", "--host", "0.0.0.0", "--port", "8000"]
