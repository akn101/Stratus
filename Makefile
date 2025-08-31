# Makefile for Stratus ERP Integration Service
# Provides convenient commands for development, testing, and deployment

.PHONY: help install dev test lint format type clean docker run logs stop

# Default target
help: ## Show this help message
	@echo "Stratus ERP Integration Service"
	@echo "==============================="
	@echo ""
	@echo "Available targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# Development setup
install: ## Install dependencies with Poetry
	poetry install --with dev

dev: ## Install dependencies and setup development environment
	poetry install --with dev
	poetry run pre-commit install
	@echo "Development environment ready!"
	@echo "Run 'make run' to start the scheduler"

# Code quality
lint: ## Run linting with ruff
	poetry run ruff check src/ tests/
	poetry run ruff format --check src/ tests/

format: ## Format code with ruff and black
	poetry run ruff format src/ tests/
	poetry run black src/ tests/

type: ## Run type checking with mypy
	poetry run mypy src/

# Testing
test: ## Run tests with pytest
	poetry run pytest

test-cov: ## Run tests with coverage report
	poetry run pytest --cov=src --cov-report=html --cov-report=term-missing

test-watch: ## Run tests in watch mode
	poetry run pytest-watch -- --cov=src

# Application
validate-config: ## Validate configuration
	@if [ ! -f .env ]; then echo "Warning: .env file not found. Copy .env.example and update it."; fi
	poetry run python main.py --validate-config

run: validate-config ## Run the scheduler (development mode)
	poetry run python main.py

run-job: ## Run a single job (usage: make run-job JOB=shopify_orders)
	@if [ -z "$(JOB)" ]; then echo "Usage: make run-job JOB=shopify_orders"; exit 1; fi
	poetry run python main.py --run $(JOB)

# Database
db-upgrade: ## Run database migrations
	poetry run alembic upgrade head

db-migrate: ## Create a new migration (usage: make db-migrate MESSAGE="description")
	@if [ -z "$(MESSAGE)" ]; then echo "Usage: make db-migrate MESSAGE='description'"; exit 1; fi
	poetry run alembic revision --autogenerate -m "$(MESSAGE)"

db-reset: ## Reset database (WARNING: destructive)
	@echo "This will reset the database. Are you sure? [y/N]" && read ans && [ $${ans:-N} = y ]
	poetry run alembic downgrade base
	poetry run alembic upgrade head

# Docker
docker: ## Build Docker image
	docker build -t stratus-erp:latest .

docker-run: ## Run with Docker Compose (development)
	docker-compose up --build

docker-prod: ## Run with Docker Compose (production-like)
	docker-compose -f docker-compose.yml up --build stratus

docker-monitoring: ## Run with monitoring stack
	docker-compose --profile monitoring up --build

docker-tools: ## Run with development tools (pgAdmin)
	docker-compose --profile tools up --build

logs: ## Show application logs
	docker-compose logs -f stratus

stop: ## Stop Docker Compose services
	docker-compose down

clean-docker: ## Clean up Docker resources
	docker-compose down -v
	docker system prune -f

# Pre-commit and CI
pre-commit: ## Run pre-commit on all files
	poetry run pre-commit run --all-files

ci-check: ## Run all CI checks locally
	$(MAKE) lint
	$(MAKE) type
	$(MAKE) test-cov
	$(MAKE) validate-config

# Monitoring and observability
health: ## Check application health
	@curl -s http://localhost:8000/healthz | python -m json.tool || echo "Service not running"

metrics: ## Show Prometheus metrics
	@curl -s http://localhost:8000/metrics || echo "Metrics endpoint not available"

# Backup and data management
backup-config: ## Backup configuration files
	@mkdir -p backups
	@tar -czf backups/config-backup-$$(date +%Y%m%d-%H%M%S).tar.gz config/
	@echo "Configuration backed up to backups/"

# Clean up
clean: ## Clean up temporary files and caches
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".ruff_cache" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
	rm -rf htmlcov/
	rm -f .coverage

# OAuth and authentication setup
freeagent-oauth: ## Set up FreeAgent OAuth authentication
	export PATH="$$HOME/.local/bin:$$PATH" && poetry run python scripts/freeagent_oauth_setup.py

# Environment setup
env-example: ## Create example environment file
	@if [ ! -f .env.example ]; then \
		echo "Creating .env.example..."; \
		echo "# Stratus ERP Integration Service Environment Variables" > .env.example; \
		echo "# Copy this file to .env and update with your values" >> .env.example; \
		echo "" >> .env.example; \
		echo "# Database (Supabase connection string)" >> .env.example; \
		echo "DATABASE_URL=postgresql://user:password@host:port/database" >> .env.example; \
		echo "" >> .env.example; \
		echo "# Shopify API" >> .env.example; \
		echo "SHOPIFY_SHOP=your-shop" >> .env.example; \
		echo "SHOPIFY_ACCESS_TOKEN=shpat_your_token" >> .env.example; \
		echo "SHOPIFY_API_VERSION=2024-07" >> .env.example; \
		echo "" >> .env.example; \
		echo "# ShipBob API" >> .env.example; \
		echo "SHIPBOB_TOKEN=your_token" >> .env.example; \
		echo "SHIPBOB_BASE=https://api.shipbob.com/2025-07" >> .env.example; \
		echo "" >> .env.example; \
		echo "# FreeAgent OAuth (get from https://dev.freeagent.com/)" >> .env.example; \
		echo "FREEAGENT_CLIENT_ID=your_client_id" >> .env.example; \
		echo "FREEAGENT_CLIENT_SECRET=your_client_secret" >> .env.example; \
		echo "FREEAGENT_REDIRECT_URI=http://localhost:8000/auth/freeagent/callback" >> .env.example; \
		echo "FREEAGENT_ACCESS_TOKEN=your_token" >> .env.example; \
		echo "FREEAGENT_REFRESH_TOKEN=your_refresh_token" >> .env.example; \
		echo "" >> .env.example; \
		echo "# Amazon SP-API (optional)" >> .env.example; \
		echo "# AMZ_ACCESS_TOKEN=" >> .env.example; \
		echo "# AMZ_REFRESH_TOKEN=" >> .env.example; \
		echo "# AMZ_CLIENT_ID=" >> .env.example; \
		echo "# AMZ_CLIENT_SECRET=" >> .env.example; \
		echo "# AMZ_MARKETPLACE_IDS=" >> .env.example; \
		echo "" >> .env.example; \
		echo "# Optional: PostgreSQL for local development" >> .env.example; \
		echo "POSTGRES_PASSWORD=stratus_dev_password" >> .env.example; \
		echo "Created .env.example - copy to .env and update with your values"; \
	else \
		echo ".env.example already exists"; \
	fi

setup: env-example install ## Complete project setup
	@echo ""
	@echo "Setup complete! Next steps:"
	@echo "1. Copy .env.example to .env and update with your API credentials"
	@echo "2. Update config/app.yaml with your desired job schedules"
	@echo "3. Run 'make db-upgrade' to setup the database"
	@echo "4. Run 'make validate-config' to check your configuration"
	@echo "5. Run 'make run' to start the scheduler"

# Documentation
docs: ## Show important documentation links
	@echo "Documentation and Resources:"
	@echo "============================"
	@echo ""
	@echo "Local URLs:"
	@echo "  Application Health: http://localhost:8000/healthz"
	@echo "  Metrics:           http://localhost:8000/metrics"
	@echo "  pgAdmin:           http://localhost:8080 (when using docker-tools)"
	@echo "  Grafana:           http://localhost:3000 (when using monitoring)"
	@echo "  Prometheus:        http://localhost:9090 (when using monitoring)"
	@echo ""
	@echo "Key Files:"
	@echo "  config/app.yaml    - Application configuration and job schedules"
	@echo "  .env              - Environment variables (API keys, database URL)"
	@echo "  README.md         - Full documentation"
	@echo "  CLAUDE.md         - Technical implementation notes"