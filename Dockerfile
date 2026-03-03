# ---- Build stage ----
FROM python:3.11-slim AS builder

WORKDIR /build
COPY pyproject.toml README.md ./
COPY src/ src/

# Ensure latest pip, then install the package (no dev deps, no cache)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --prefix=/install .

# ---- Runtime stage ----
FROM python:3.11-slim

ARG GIT_SHA=dev

# Create non-root user (UID 10001)
RUN groupadd --gid 10001 appuser && \
    useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin appuser

# Copy only the installed package from builder
COPY --from=builder /install /usr/local

# Environment defaults
ENV SIGNOZ_ENDPOINT="" \
    SIGNOZ_API_KEY="" \
    EXECUTION_ATTRIBUTE="execution_id" \
    POLL_INTERVAL="7" \
    MAX_SPANS_PER_PAGE="10000" \
    PORT="8077" \
    LOG_FORMAT="json" \
    GIT_SHA="${GIT_SHA}" \
    PYTHONDONTWRITEBYTECODE="1" \
    PYTHONUNBUFFERED="1"

EXPOSE 8077

# Switch to non-root user
USER 10001

# No filesystem writes at runtime — compatible with readOnlyRootFilesystem: true
CMD ["rf-trace-report", "serve", "--provider", "signoz", "--port", "8077", "--no-open"]
