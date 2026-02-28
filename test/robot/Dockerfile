# Robot Framework API integration test runner for trace-report.
# Lightweight image — only needs HTTP client libraries, no browser.
FROM python:3.11-slim

RUN pip install --no-cache-dir \
    robotframework==7.1.1 \
    robotframework-requests==0.9.7

WORKDIR /tests

COPY tests/ tests/
COPY resources/ resources/

CMD ["robot", "--outputdir", "/results", "tests/"]
