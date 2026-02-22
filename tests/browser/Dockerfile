# Browser testing environment for rf-trace-report
# Not part of the package installation - only for development/verification

FROM python:3.11-slim

# Install system dependencies for Playwright and Node.js
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    curl \
    # Playwright browser dependencies
    libglib2.0-0 \
    libnss3 \
    libnspr4 \
    libdbus-1-3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxcb1 \
    libxkbcommon0 \
    libatspi2.0-0 \
    libx11-6 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir \
    robotframework==7.1.1 \
    robotframework-browser==18.8.0 \
    robotframework-pabot==2.18.0

# Initialize Browser library (downloads Playwright browsers)
RUN rfbrowser init

# Set working directory
WORKDIR /workspace

# Default command: run tests
CMD ["robot", "--outputdir", "/workspace/results", "/workspace/tests/browser/suites"]
