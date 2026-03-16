.PHONY: test help load-gtfs run-api run-bot run-worker run-all setup stop-all test-docker

# Colors and formatting
CYAN = \033[36m
GREEN = \033[32m
RESET = \033[0m

help:
	@echo "$(CYAN)CityBus Bot Makefile (Dockerized)$(RESET)"
	@echo "Available commands:"
	@echo "  $(GREEN)make run-all$(RESET)       - Start all services with Docker Compose"
	@echo "  $(GREEN)make stop-all$(RESET)      - Stop all services and containers"
	@echo "  $(GREEN)make run-api$(RESET)       - Start only the API service"
	@echo "  $(GREEN)make run-bot$(RESET)       - Start only the Bot service"
	@echo "  $(GREEN)make load-gtfs$(RESET)     - Load GTFS into Docker Mongo (e.g., make load-gtfs ZIP=gtfs.zip CITY=citybus)"
	@echo "  $(GREEN)make test-docker$(RESET)   - Run all tests in a dedicated container (CI-like)"
	@echo "  $(GREEN)make test$(RESET)          - Run unit tests (local environment)"

setup:
	python3 -m venv venv
	./venv/bin/pip install -r requirements.txt
	@echo "Remember to copy .env.example to .env and configure it!"

clear-test-db:
	@echo "Clearing test database..."
	MONGO_DB_NAME=citybus_test PYTHONPATH=. ./venv/bin/python -c "import asyncio; from citybus.db.mongo import get_db, init_db; async def clear(): await init_db(); db=get_db(); await db.client.drop_database('citybus_test'); asyncio.run(clear())"

load-gtfs:
	@if [ -z "$(ZIP)" ]; then echo "Error: ZIP is required. Usage: make load-gtfs ZIP=path/to/gtfs.zip"; exit 1; fi
	docker-compose run --rm api python citybus/scripts/load_gtfs.py $(ZIP) $(CITY)

run-api:
	docker-compose up -d api

run-bot:
	docker-compose up -d bot

run-worker:
	docker-compose up -d worker

run-all:
	docker-compose up -d

stop-all:
	docker-compose down

test-docker:
	@echo "Running all tests in isolated Docker containers..."
	docker-compose -f docker-compose.test.yml up --build --exit-code-from tests
	docker-compose -f docker-compose.test.yml down

test:
	@echo "Running unit tests locally..."
	PYTHONPATH=. ./venv/bin/python -m pytest tests/test_api.py tests/test_commands.py tests/test_mcp.py -v

test-integration:
	@echo "Running integration tests locally..."
	PYTHONPATH=. ./venv/bin/python -m pytest tests/test_integration.py -v
