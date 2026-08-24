FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /build

COPY --from=ghcr.io/astral-sh/uv:0.11.31 /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./
COPY src ./src

RUN uv sync --frozen --no-dev --no-editable --no-cache


FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

RUN groupadd --system --gid 10001 parksmart \
    && useradd --system --uid 10001 --gid parksmart --home-dir /app parksmart

COPY --from=builder /opt/venv /opt/venv

RUN chown parksmart:parksmart /app

USER parksmart:parksmart

EXPOSE 8000

CMD ["sh", "-c", "exec uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
