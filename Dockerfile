# ---- Stage 1: Build ----
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN pip install --no-cache-dir --upgrade pip

COPY pyproject.toml ./
COPY src ./src

RUN pip install --no-cache-dir .

COPY . .

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]