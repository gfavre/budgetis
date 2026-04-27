#!/bin/sh
set -e

# Ensure media subdirectories exist (volume mount can reset them)
mkdir -p /app/media/imports/accounts

# Wait for database to be ready
echo "⏳ Waiting for database..."
until nc -z db 5432; do
  sleep 1
done
echo "⏳ Waiting for Redis..."
until nc -z redis 6379; do
  sleep 1
done
# Run migrations at runtime
echo "⚙️ Applying database migrations..."
python manage.py migrate --noinput

exec "$@"
