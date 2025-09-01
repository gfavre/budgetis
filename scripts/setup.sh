#!/bin/bash
set -e

ENV_FILE=".env"

echo "🚀 Budgetis setup starting..."

# 1. Copier le fichier d'exemple si .env n'existe pas
if [ ! -f "$ENV_FILE" ]; then
  echo "⚙️  Creating $ENV_FILE from template..."
  cp .env.example .env
fi

# 2. Ajouter un DJANGO_SECRET_KEY si absent
if ! grep -q "DJANGO_SECRET_KEY" "$ENV_FILE"; then
  echo "⚠️  No DJANGO_SECRET_KEY found in $ENV_FILE, generating one..."
  SECRET=$(python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())")
  echo "DJANGO_SECRET_KEY=$SECRET" >> "$ENV_FILE"
  echo "✅ Secret key generated and stored in $ENV_FILE"
fi

# 3. Construire les images Docker
echo "⚙️  Building Docker images..."
docker compose build

# 4. Appliquer les migrations
echo "⚙️  Applying database migrations..."
docker compose run --rm web python manage.py migrate

# 5. Créer un superutilisateur (optionnel)
echo "⚙️  Do you want to create a Django superuser now? (y/n)"
read -r CREATE_SUPERUSER
if [ "$CREATE_SUPERUSER" = "y" ]; then
  docker compose run --rm web python manage.py createsuperuser
fi

echo "✅ Setup complete! You can now run: docker compose up -d"
