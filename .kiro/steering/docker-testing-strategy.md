---
inclusion: auto
---

# Docker-Only Development Environment

## Critical Rule: ALWAYS Use Docker

**NEVER install or run tools directly on the host system.** This project uses a Docker-only workflow. The host should only have Docker and Kiro — nothing else.

This applies to ALL tooling, not just Python:
- No Python, pip, or virtual environments on the host
- No installing CLI tools (kind, kubectl, helm, etc.) on the host
- No `curl | install` or `apt install` for project tooling
- If a tool is needed, run it via a Docker container (e.g. `docker run bitnami/kubectl:latest`)

## Critical Rule: Use the Pre-Built Test Image

**NEVER use `python:3.11-slim` with `pip install` at runtime.** Use the pre-built `rf-trace-test:latest` image (built from `Dockerfile.test`) or Makefile targets.

```bash
make docker-build-test  # Build once, or after Dockerfile.test changes
```

## Prerequisites

Only 2 things are required:
1. **Docker**
2. **Kiro**

## What NOT to Do

```bash
# DON'T run raw Python on host
python3 -m pytest tests/
pip install pytest

# DON'T use python:3.11-slim with pip install at runtime
docker run --rm -v $(pwd):/workspace -w /workspace python:3.11-slim bash -c "pip install ..."

# DON'T use virtual environments
python -m venv venv

# DON'T install infrastructure tools on the host
curl -Lo /tmp/kind https://kind.sigs.k8s.io/...
apt install kubectl

# DO use containerized tools instead
docker run --rm bitnami/kubectl:latest get pods
```

## Direct Docker Commands (When Makefile Isn't Enough)

```bash
docker run --rm -v $(pwd):/workspace -w /workspace rf-trace-test:latest bash -c "\
  PYTHONPATH=src pytest tests/unit/test_rf_model.py -v -n auto"
```

## Ensuring Latest Code in Running Containers

The `rf-trace-report` container uses a volume mount so Python source changes are visible immediately. However:

1. **Python bytecode cache** can serve stale code:
   ```bash
   find src/ -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
   ```

2. **JS viewer files** are cached at startup — restart after editing:
   ```bash
   docker restart rf-signoz-test-rf-trace-report-1
   ```

3. **If container was built with old code**, rebuild:
   ```bash
   docker compose -p rf-signoz-test -f tests/integration/signoz/docker-compose.yml --profile report up -d --build rf-trace-report
   ```

## Troubleshooting

- **"rf-trace-test:latest not found"** → `make docker-build-test`
- **"Module not found"** → Ensure `PYTHONPATH=src` is set
- **"unrecognized arguments: -n"** → Wrong image, use `rf-trace-test:latest`

## Kind Cluster (Integration Test Environment)

A Kind (Kubernetes in Docker) cluster runs inside Docker for integration testing and manual verification. The cluster container is named `trace-report-test-control-plane`.

**Key facts:**
- `kind` and `kubectl` are NOT installed on the host — they run inside the kind container
- All kubectl commands go through: `docker exec trace-report-test-control-plane kubectl ...`
- The cluster is created via `make itest-up` (runs `test/kind/itest-up.sh`)
- Torn down via `make itest-down`
- trace-report is accessible at `http://localhost:8077` when port-forward is active

### Deploying a New Image to the Kind Cluster

The deployment uses incrementing tags (`dev`, `dev2`, `dev3`, ...) with `imagePullPolicy: IfNotPresent`. To deploy new code:

1. **Build the image on the host:**
   ```bash
   docker build -t trace-report:dev .
   ```

2. **Tag with next increment** (check current: `docker exec trace-report-test-control-plane kubectl get deployment trace-report -o jsonpath='{.spec.template.spec.containers[0].image}'`):
   ```bash
   docker tag trace-report:dev trace-report:devN
   ```

3. **Load into kind cluster** (no `kind` CLI needed — pipe through containerd):
   ```bash
   docker save trace-report:devN | docker exec -i trace-report-test-control-plane ctr --namespace k8s.io images import -
   ```

4. **Update the deployment:**
   ```bash
   docker exec trace-report-test-control-plane kubectl set image deployment/trace-report trace-report=trace-report:devN
   ```

5. **Wait for rollout:**
   ```bash
   docker exec trace-report-test-control-plane kubectl rollout status deployment/trace-report --timeout=60s
   ```

### Useful Kind Cluster Commands

```bash
# List pods
docker exec trace-report-test-control-plane kubectl get pods

# Check which image is deployed
docker exec trace-report-test-control-plane kubectl get deployment trace-report -o jsonpath='{.spec.template.spec.containers[0].image}'

# View pod logs
docker exec trace-report-test-control-plane kubectl logs -l app.kubernetes.io/name=trace-report

# List images loaded in kind
docker exec trace-report-test-control-plane crictl images | grep trace-report

# Check if kind cluster container is running
docker ps --filter name=trace-report-test-control-plane
```
