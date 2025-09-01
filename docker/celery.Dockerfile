FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv pip install --system --no-cache .

COPY . .

# Le module celery_app est bien dans config/
CMD ["celery", "-A", "config.celery_app", "worker", "-l", "info"]
