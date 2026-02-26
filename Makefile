# Makefile for robotframework-trace-report
# All commands use Docker to ensure consistent environment
#
# Memory limits:
#   test-unit:       6 GB  (skips slow/large-fixture tests via --skip-slow)
#   test-slow:       4 GB  (large_trace.json tests only)
#   test-properties: 4 GB  (Hypothesis can be memory-hungry)
#   dev-test:        6 GB  (quick run, no coverage)
#   dev-test-file:   3 GB  (single file, may include slow tests)

.PHONY: help test test-unit test-slow test-browser test-integration-signoz test-properties format lint check clean

help: ## Show this help message
	@echo "robotframework-trace-report - Docker-based development commands"
	@echo ""
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

test: test-unit ## Run all tests (unit, skipping slow large-fixture tests)

test-unit: ## Run Python unit tests with coverage (skips slow/large-fixture tests)
	@echo "Running unit tests in Docker..."
	@docker run --rm --memory=6g --memory-swap=6g -v $$(pwd):/workspace -w /workspace rf-trace-test:latest bash -c "\
		PYTHONPATH=src pytest tests/unit/ $(ARGS) --skip-slow --cov=src/rf_trace_viewer --cov-report=html --cov-report=term-missing -n 2"

test-slow: ## Run slow tests that use large_trace.json (requires ~4 GB RAM)
	@echo "Running slow (large-fixture) tests in Docker..."
	@docker run --rm --memory=4g --memory-swap=4g -v $$(pwd):/workspace -w /workspace rf-trace-test:latest bash -c "\
		PYTHONPATH=src pytest tests/unit/ -v -m slow -n auto"

test-properties: ## Run property-based tests only
	@echo "Running property-based tests in Docker..."
	@docker run --rm --memory=4g --memory-swap=4g -v $$(pwd):/workspace -w /workspace rf-trace-test:latest bash -c "\
		PYTHONPATH=src pytest tests/unit/test_*_properties.py -v -n auto"

test-browser: ## Run browser tests with Robot Framework
	@echo "Running browser tests in Docker..."
	@cd tests/browser && docker compose up --build

test-integration-signoz: ## Run end-to-end SigNoz integration test (requires Docker)
	@echo "Running SigNoz integration test..."
	@cd tests/integration/signoz && bash run_integration.sh

format: ## Format code with Black
	@echo "Formatting code in Docker..."
	@docker run --rm -v $$(pwd):/workspace -w /workspace rf-trace-test:latest bash -c "\
		black src/ tests/"

lint: ## Lint code with Ruff
	@echo "Linting code in Docker..."
	@docker run --rm -v $$(pwd):/workspace -w /workspace rf-trace-test:latest bash -c "\
		ruff check src/"

check: ## Check code formatting and linting (CI-style)
	@echo "Checking code quality in Docker..."
	@docker run --rm -v $$(pwd):/workspace -w /workspace rf-trace-test:latest bash -c "\
		black --check src/ tests/ && \
		ruff check src/"

report: ## Generate HTML report from test fixture
	@mkdir -p test-reports
	@echo "Generating test report in Docker..."
	@docker run --rm -v $$(pwd):/workspace -w /workspace python:3.11-slim bash -c "\
		PYTHONPATH=src python3 -m rf_trace_viewer.cli tests/fixtures/pabot_trace.json -o test-reports/report.html"
	@echo "Report generated: test-reports/report.html"

clean: ## Clean up generated files
	@echo "Cleaning up..."
	@rm -rf htmlcov/ .coverage .pytest_cache/
	@rm -rf test-reports/
	@rm -rf tests/browser/results/
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@echo "Clean complete"

# Development helpers
dev-test: ## Quick test run (unit tests only, no coverage, parallel)
	@echo "Running quick unit tests in Docker..."
	@docker run --rm --memory=6g --memory-swap=6g -v $$(pwd):/workspace -w /workspace rf-trace-test:latest bash -c "\
		PYTHONPATH=src pytest tests/unit/ --skip-slow -v -n 2"

dev-test-file: ## Run specific test file (usage: make dev-test-file FILE=tests/unit/test_generator.py)
	@echo "Running $(FILE) in Docker..."
	@docker run --rm --memory=3g --memory-swap=3g -v $$(pwd):/workspace -w /workspace rf-trace-test:latest bash -c "\
		PYTHONPATH=src pytest $(FILE) --skip-slow -v"

# CI targets
ci-test: check test-unit ## Run all CI checks (format, lint, unit tests)

# Docker image management
docker-build-test: ## Build the test Docker image with all dependencies
	@echo "Building test Docker image..."
	@docker build -f Dockerfile.test -t rf-trace-test:latest .
	@echo "Test image built successfully: rf-trace-test:latest"

docker-pull: ## Pull latest Python image
	@docker pull python:3.11-slim

docker-clean: ## Remove Docker images and containers
	@docker system prune -f
