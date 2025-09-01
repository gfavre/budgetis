FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install uv + netcat
RUN apt-get update && apt-get install -y netcat-openbsd && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv


WORKDIR /app

# Copier les fichiers de dépendances
COPY pyproject.toml uv.lock ./
RUN uv pip install --system --no-cache --group prod .

# Copier le code
COPY . .

# Copy entrypoint
COPY docker/entrypoint.sh /app/docker/entrypoint.sh
RUN chmod +x /app/docker/entrypoint.sh

# Collect static and compress at build time
ENV DJANGO_SETTINGS_MODULE=config.settings.production
RUN python manage.py collectstatic --noinput && \
    python manage.py compress --force
ENTRYPOINT ["/app/docker/entrypoint.sh"]

# Commande par défaut = Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "config.wsgi:application"]
