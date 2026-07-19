# ITC 6050 Group 1 — Air Quality Monitor
# One-command operations for the whole stack

.PHONY: help setup up down restart logs ps clean pipeline dbt-seed dbt-run dbt-test dashboard psql

help:  ## Show this help
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-15s %s\n", $$1, $$2}'

setup:  ## First-time setup: copy .env template and build images
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "Created .env from template. Edit it to set your password."; \
	else \
		echo ".env already exists, skipping."; \
	fi
	docker compose build

up:  ## Start Postgres and dashboard in the background
	docker compose up -d postgres dashboard

down:  ## Stop all services (data persists in volume)
	docker compose down

restart:  ## Restart Postgres and dashboard
	docker compose restart postgres dashboard

logs:  ## Tail logs from all running services
	docker compose logs -f

ps:  ## Show status of all services
	docker compose ps

clean:  ## Stop everything and DELETE all data (use with caution)
	docker compose down -v

pipeline:  ## Run the ingestion pipeline
	docker compose run --rm pipeline

dbt-seed:  ## Load dbt seed files (reference data)
	docker compose run --rm dbt seed

dbt-run: dbt-seed  ## Load seeds, then run dbt models
	docker compose run --rm dbt run

dbt-test:  ## Run dbt tests
	docker compose run --rm dbt test

dashboard:  ## Open dashboard in browser (must be running)
	@echo "Dashboard: http://localhost:8501"
	@open http://localhost:8501 || xdg-open http://localhost:8501

psql:  ## Open psql shell in the Postgres container
	docker compose exec postgres psql -U postgres -d air_quality
