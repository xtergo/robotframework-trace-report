#!/usr/bin/env bash
# Deploy the SigNoz test stack to a kind cluster.
#
# Handles ordering: ZooKeeper → ClickHouse → schema-migrator → SigNoz/OTel.
# The schema-migrator Job is always deleted and recreated so it re-runs
# after ClickHouse restarts (it's idempotent — safe to run repeatedly).
#
# Usage:
#   test/kind/signoz/deploy.sh [CONTEXT]
#   CONTEXT defaults to kind-trace-report-test

set -euo pipefail

CONTEXT="${1:-kind-trace-report-test}"
DIR="$(cd "$(dirname "$0")" && pwd)"
K="kubectl --context $CONTEXT"

echo "==> Applying base manifests..."
$K apply -f "$DIR/clickhouse-config.yaml"
$K apply -f "$DIR/zookeeper.yaml"
$K apply -f "$DIR/clickhouse.yaml"
$K apply -f "$DIR/otel-config.yaml"
$K apply -f "$DIR/otel-collector.yaml"
$K apply -f "$DIR/signoz.yaml"

echo "==> Waiting for ClickHouse to be ready..."
$K rollout status statefulset/clickhouse --timeout=180s

echo "==> (Re)running schema migrator..."
$K delete job schema-migrator-sync --ignore-not-found
$K apply -f "$DIR/schema-migrator.yaml"
$K wait --for=condition=complete job/schema-migrator-sync --timeout=120s

echo "==> Waiting for SigNoz to be ready..."
$K rollout status deployment/signoz --timeout=120s

echo "==> Stack is ready."
$K get pods
