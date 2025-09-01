# ---------------------------------------------------------
# Budgetis - Makefile
# ---------------------------------------------------------

DOCKER_COMPOSE = docker compose
MANAGE = $(DOCKER_COMPOSE) run --rm web python manage.py

# ---------------------------------------------------------
# Setup & lifecycle
# ---------------------------------------------------------

.PHONY: build
build: ## Build Docker images
	$(DOCKER_COMPOSE) build

.PHONY: up
up: ## Start all services in detached mode
	$(DOCKER_COMPOSE) up -d

.PHONY: down
down: ## Stop all services
	$(DOCKER_COMPOSE) down

.PHONY: logs
logs: ## Tail logs
	$(DOCKER_COMPOSE) logs -f

.PHONY: ps
ps: ## Show running containers
	$(DOCKER_COMPOSE) ps

# ---------------------------------------------------------
# Django management
# ---------------------------------------------------------

.PHONY: migrate
migrate: ## Apply database migrations
	$(MANAGE) migrate

.PHONY: makemigrations
makemigrations: ## Create new migrations based on changes
	$(MANAGE) makemigrations

.PHONY: shell
shell: ## Open Django shell
	$(MANAGE) shell

.PHONY: createsuperuser
createsuperuser: ## Create a Django superuser
	$(MANAGE) createsuperuser

.PHONY: collectstatic
collectstatic: ## Collect static files
	$(MANAGE) collectstatic --noinput

# ---------------------------------------------------------
# Utilities
# ---------------------------------------------------------

.PHONY: reset
reset: down ## Stop, remove volumes, rebuild from scratch
	$(DOCKER_COMPOSE) down -v
	$(DOCKER_COMPOSE) build

.PHONY: restart
restart: down up ## Restart all services

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'
