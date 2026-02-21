# Browser testing environment for rf-trace-report
# Not part of the package installation - only for development/verification

FROM python:3.11-slim

# Install system dependencies for Playwright and Node.js
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    curl \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir \
    robotframework==7.1.1 \
    robotframework-browser==18.8.0

# Initialize Browser library (downloads Playwright browsers)
RUN rfbrowser init

# Set working directory
WORKDIR /workspace

# Default command: run tests
CMD ["robot", "--outputdir", "/workspace/results", "/workspace/tests/browser/suites"]
