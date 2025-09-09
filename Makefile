.PHONY: help up down logs format test migrate alembic clean install-deps check

# Variables
DOCKER_COMPOSE_FILE = docker-compose.dev.yml
API_SERVICE = api
WORKER_SERVICE = worker
WEB_SERVICE = web

# Help
help: ## Mostrar este mensaje de ayuda
	@echo "Comandos disponibles para Axonote:"
	@echo ""
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# Docker commands
up: ## Levantar todos los servicios en modo desarrollo
	docker-compose -f $(DOCKER_COMPOSE_FILE) up -d
	@echo "🚀 Servicios iniciados. Web: http://localhost:3000, API: http://localhost:8000"

down: ## Parar todos los servicios
	docker-compose -f $(DOCKER_COMPOSE_FILE) down

logs: ## Mostrar logs de todos los servicios
	docker-compose -f $(DOCKER_COMPOSE_FILE) logs -f

logs-api: ## Mostrar logs del API
	docker-compose -f $(DOCKER_COMPOSE_FILE) logs -f $(API_SERVICE)

logs-worker: ## Mostrar logs del worker
	docker-compose -f $(DOCKER_COMPOSE_FILE) logs -f $(WORKER_SERVICE)

logs-web: ## Mostrar logs del frontend
	docker-compose -f $(DOCKER_COMPOSE_FILE) logs -f $(WEB_SERVICE)

restart: ## Reiniciar todos los servicios
	docker-compose -f $(DOCKER_COMPOSE_FILE) restart

restart-api: ## Reiniciar solo el API
	docker-compose -f $(DOCKER_COMPOSE_FILE) restart $(API_SERVICE)

restart-worker: ## Reiniciar solo el worker
	docker-compose -f $(DOCKER_COMPOSE_FILE) restart $(WORKER_SERVICE)

restart-web: ## Reiniciar solo el frontend
	docker-compose -f $(DOCKER_COMPOSE_FILE) restart $(WEB_SERVICE)

# Development commands
format: ## Formatear código Python (ruff + black) y TypeScript (prettier)
	@echo "🎨 Formateando código Python..."
	cd apps/api && poetry run ruff --fix .
	cd apps/api && poetry run black .
	@echo "🎨 Formateando código TypeScript..."
	cd apps/web && npm run lint:fix

lint: ## Verificar estilo de código
	@echo "🔍 Verificando código Python..."
	cd apps/api && poetry run ruff .
	cd apps/api && poetry run black --check .
	cd apps/api && poetry run mypy .
	@echo "🔍 Verificando código TypeScript..."
	cd apps/web && npm run lint
	cd apps/web && npm run type-check

test: ## Ejecutar tests del backend y frontend
	@echo "🧪 Ejecutando tests del backend..."
	cd apps/api && poetry run pytest
	@echo "🧪 Ejecutando tests del frontend..."
	cd apps/web && npm run test

test-api: ## Ejecutar solo tests del backend
	cd apps/api && poetry run pytest

test-web: ## Ejecutar solo tests del frontend
	cd apps/web && npm run test

test-e2e: ## Ejecutar tests end-to-end
	cd apps/web && npm run test:e2e

# Database commands
migrate: ## Ejecutar migraciones de base de datos
	docker-compose -f $(DOCKER_COMPOSE_FILE) exec $(API_SERVICE) alembic upgrade head

migration: ## Crear nueva migración (uso: make migration MESSAGE="descripcion")
	docker-compose -f $(DOCKER_COMPOSE_FILE) exec $(API_SERVICE) alembic revision --autogenerate -m "$(MESSAGE)"

alembic: ## Ejecutar comando de alembic (uso: make alembic CMD="history")
	docker-compose -f $(DOCKER_COMPOSE_FILE) exec $(API_SERVICE) alembic $(CMD)

db-reset: ## Resetear base de datos (CUIDADO: elimina todos los datos)
	docker-compose -f $(DOCKER_COMPOSE_FILE) down -v
	docker-compose -f $(DOCKER_COMPOSE_FILE) up -d db
	sleep 5
	$(MAKE) migrate

# Installation commands
install-deps: ## Instalar dependencias de desarrollo
	@echo "📦 Instalando dependencias del backend..."
	cd apps/api && poetry install
	@echo "📦 Instalando dependencias del frontend..."
	cd apps/web && npm install

# Utility commands
shell-api: ## Abrir shell en el contenedor del API
	docker-compose -f $(DOCKER_COMPOSE_FILE) exec $(API_SERVICE) bash

shell-worker: ## Abrir shell en el contenedor del worker
	docker-compose -f $(DOCKER_COMPOSE_FILE) exec $(WORKER_SERVICE) bash

shell-db: ## Abrir shell en la base de datos
	docker-compose -f $(DOCKER_COMPOSE_FILE) exec db psql -U postgres -d medclass

# Monitoring commands
status: ## Mostrar estado de los servicios
	docker-compose -f $(DOCKER_COMPOSE_FILE) ps

health: ## Verificar salud de los servicios
	@echo "🏥 Verificando salud de los servicios..."
	@curl -s http://localhost:8000/health || echo "❌ API no disponible"
	@curl -s http://localhost:3000 > /dev/null && echo "✅ Frontend disponible" || echo "❌ Frontend no disponible"

# Cleanup commands
clean: ## Limpiar contenedores, imágenes y volúmenes no utilizados
	docker system prune -f
	docker volume prune -f

clean-all: ## Limpiar todo, incluyendo volúmenes con datos
	docker-compose -f $(DOCKER_COMPOSE_FILE) down -v
	docker system prune -af
	docker volume prune -f

# Production commands (para GPU compose)
up-gpu: ## Levantar servicios con soporte GPU
	docker-compose -f deploy/docker-compose.gpu.yml up -d

down-gpu: ## Parar servicios GPU
	docker-compose -f deploy/docker-compose.gpu.yml down

# Development workflow
dev-setup: ## Setup completo para desarrollo
	$(MAKE) install-deps
	$(MAKE) up
	sleep 10
	$(MAKE) migrate
	@echo "🎉 Setup completo! Servicios disponibles en:"
	@echo "   - Frontend: http://localhost:3000"
	@echo "   - API: http://localhost:8000"
	@echo "   - MinIO Console: http://localhost:9001"

check: ## Verificar que todo funciona correctamente
	$(MAKE) lint
	$(MAKE) test
	$(MAKE) health
