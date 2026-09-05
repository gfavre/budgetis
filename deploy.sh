#!/bin/bash
set -e

# Run this on the prod server, from the repo root, to ship the latest master:
#   ./scripts/deploy.sh
# Migrations, collectstatic, compilemessages and compress already happen
# automatically (build time / container entrypoint) - see docker/web.Dockerfile
# and docker/entrypoint.sh.

COMPOSE_FILE="docker-compose.prod.yml"

echo "🚀 Budgetis deploy starting..."

# 1. Refuse to deploy from a dirty working tree - a local edit made
#    directly on the server would otherwise get silently overwritten or
#    tangled up with the pull below.
if [ -n "$(git status --porcelain)" ]; then
  echo "❌ Working tree has uncommitted changes, aborting:"
  git status --short
  exit 1
fi

# 2. Deploys only ever come from master.
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ "$CURRENT_BRANCH" != "master" ]; then
  echo "❌ Expected to be on 'master', but on '$CURRENT_BRANCH', aborting."
  exit 1
fi

# 3. Pull the latest commits - fast-forward only, never merge on the server.
echo "⚙️  Pulling latest master..."
git pull --ff-only

# 4. Rebuild images (bakes in the new code, static files and translations).
echo "⚙️  Building Docker images..."
docker compose -f "$COMPOSE_FILE" build

# 5. Recreate any service whose image/config changed. Migrations run
#    automatically as part of the web container's entrypoint.
echo "⚙️  Starting services..."
docker compose -f "$COMPOSE_FILE" up -d

# 6. Housekeeping - drop images left behind by the rebuild.
echo "⚙️  Pruning dangling images..."
docker image prune -f

echo "⚙️  Current status:"
docker compose -f "$COMPOSE_FILE" ps

echo "✅ Deploy complete!"
