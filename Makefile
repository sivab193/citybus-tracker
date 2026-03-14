.PHONY: test help load-gtfs run-api run-bot run-worker run-all

# Colors and formatting
CYAN = \033[36m
GREEN = \033[32m
RESET = \033[0m

help:
	@echo "$(CYAN)CityBus Bot Makefile$(RESET)"
	@echo "Available commands:"
	@echo "  $(GREEN)make setup$(RESET)        - Install dependencies and setup environment"
	@echo "  $(GREEN)make test$(RESET)         - Run the test suite with pytest"
	@echo "  $(GREEN)make load-gtfs$(RESET)    - Load a GTFS .zip file into MongoDB (e.g., make load-gtfs ZIP=gtfs.zip CITY=citybus)"
	@echo "  $(GREEN)make run-api$(RESET)      - Run the FastAPI REST server"
	@echo "  $(GREEN)make run-bot$(RESET)      - Run the Telegram bot"
	@echo "  $(GREEN)make run-worker$(RESET)   - Run the background polling worker"
	@echo "  $(GREEN)make mcp$(RESET)          - Run the MCP server in stdout mode for LM Studio"

setup:
	python3 -m venv venv
	./venv/bin/pip install -r requirements.txt
	@echo "Remember to copy .env.example to .env and configure it!"

test:
	PYTHONPATH=. ./venv/bin/python -m pytest tests/ -v

load-gtfs:
	@if [ -z "$(ZIP)" ]; then echo "Error: ZIP is required. Usage: make load-gtfs ZIP=path/to/gtfs.zip"; exit 1; fi
	PYTHONPATH=. ./venv/bin/python citybus/scripts/load_gtfs.py $(ZIP) $(CITY)

run-api:
	PYTHONPATH=. ./venv/bin/python main_api.py

run-bot:
	PYTHONPATH=. ./venv/bin/python main_bot.py

run-worker:
	PYTHONPATH=. ./venv/bin/python main_worker.py

mcp:
	PYTHONPATH=. ./venv/bin/python -m citybus.mcp.server

run-all:
	@echo "$(CYAN)Starting all services...$(RESET)"
	PYTHONPATH=. ./venv/bin/python main_api.py & \
	PYTHONPATH=. ./venv/bin/python main_worker.py & \
	PYTHONPATH=. ./venv/bin/python main_bot.py & \
	wait
