#!/bin/bash
# Quick test runner script

echo "Building Docker image..."
docker-compose build

echo ""
echo "Running browser tests..."
docker-compose run --rm browser-tests

echo ""
echo "Test results available in: tests/browser/results/"
echo "Open tests/browser/results/log.html to see detailed results with console logs"
