# Makefile for robotframework-trace-report
# All commands use Docker to ensure consistent environment

.PHONY: help test test-unit test-browser test-properties format lint check clean

help: ## Show this help message
	@echo "robotframework-trace-report - Docker-based development commands"
	@echo ""
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

test: test-unit ## Run all tests (unit + browser)

test-unit: ## Run Python unit tests with coverage
	@echo "Running unit tests in Docker..."
	@docker run --rm -v $$(pwd):/workspace -w /workspace python:3.11-slim bash -c "\
		pip install -q pytest pytest-cov hypothesis && \
		PYTHONPATH=src pytest tests/unit/ -v --cov=src/rf_trace_viewer --cov-report=term-missing"

test-properties: ## Run property-based tests only
	@echo "Running property-based tests in Docker..."
	@docker run --rm -v $$(pwd):/workspace -w /workspace python:3.11-slim bash -c "\
		pip install -q pytest hypothesis && \
		PYTHONPATH=src pytest tests/unit/test_*_properties.py -v -o addopts=''"

test-browser: ## Run browser tests with Robot Framework
	@echo "Running browser tests in Docker..."
	@cd tests/browser && docker compose up --build

format: ## Format code with Black
	@echo "Formatting code in Docker..."
	@docker run --rm -v $$(pwd):/workspace -w /workspace python:3.11-slim bash -c "\
		pip install -q black && \
		black src/ tests/"

lint: ## Lint code with Ruff
	@echo "Linting code in Docker..."
	@docker run --rm -v $$(pwd):/workspace -w /workspace python:3.11-slim bash -c "\
		pip install -q ruff && \
		ruff check src/"

check: ## Check code formatting and linting (CI-style)
	@echo "Checking code quality in Docker..."
	@docker run --rm -v $$(pwd):/workspace -w /workspace python:3.11-slim bash -c "\
		pip install -q black ruff && \
		black --check src/ tests/ && \
		ruff check src/"

report: ## Generate HTML report from test fixture
	@echo "Generating test report in Docker..."
	@docker run --rm -v $$(pwd):/workspace -w /workspace python:3.11-slim bash -c "\
		PYTHONPATH=src python3 -m rf_trace_viewer.cli tests/fixtures/pabot_trace.json -o report.html"
	@echo "Report generated: report.html"

clean: ## Clean up generated files
	@echo "Cleaning up..."
	@rm -rf htmlcov/ .coverage .pytest_cache/ report.html
	@rm -rf tests/browser/results/
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@echo "Clean complete"

# Development helpers
dev-test: ## Quick test run (unit tests only, no coverage)
	@echo "Running quick unit tests in Docker..."
	@docker run --rm -v $$(pwd):/workspace -w /workspace python:3.11-slim bash -c "\
		pip install -q pytest hypothesis && \
		PYTHONPATH=src pytest tests/unit/ -v"

dev-test-file: ## Run specific test file (usage: make dev-test-file FILE=test_rf_model_properties.py)
	@echo "Running $(FILE) in Docker..."
	@docker run --rm -v $$(pwd):/workspace -w /workspace python:3.11-slim bash -c "\
		pip install -q pytest hypothesis && \
		PYTHONPATH=src pytest tests/unit/$(FILE) -v"

# CI targets
ci-test: check test-unit ## Run all CI checks (format, lint, unit tests)

# Docker image management
docker-pull: ## Pull latest Python image
	@docker pull python:3.11-slim

docker-clean: ## Remove Docker images and containers
	@docker system prune -f
