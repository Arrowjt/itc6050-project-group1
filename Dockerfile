FROM python:3.12-slim

# System dependencies for psycopg2 and general build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Working directory
WORKDIR /app

# Install Python dependencies first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the rest of the project (overridden by volume mounts in dev)
COPY . .

# Default command overridden by docker-compose per service
CMD ["python", "--version"]
