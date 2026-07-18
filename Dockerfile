# ─────────────────────────────────────────────
# Trilith — self-contained Docker image
# ─────────────────────────────────────────────
FROM python:3.12-slim

LABEL maintainer="Trilith Authors"
LABEL description="Trilith context management server"

WORKDIR /app

# Install system deps needed to compile protobuf (protoc is baked into grpcio-tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
 && rm -rf /var/lib/apt/lists/*

# Copy dependency manifest first (layer cache friendly)
COPY pyproject.toml ./

# Install runtime + server extras
RUN pip install --no-cache-dir hatchling && \
    pip install --no-cache-dir "grpcio>=1.60.0" "protobuf>=4.25.0" \
    "grpcio-tools>=1.60.0" "fastapi>=0.110.0" "uvicorn[standard]>=0.29.0"

# Copy source
COPY core/       ./core/
COPY proto/      ./proto/
COPY scripts/    ./scripts/

# Compile proto → Python bindings inside the image
RUN python scripts/compile_proto.py

# Data directory for persistent SQLite storage
RUN mkdir -p /data
ENV TRILITH_DB_PATH=/data/trilith.db

# REST (8080) + gRPC (50051)
EXPOSE 8080 50051

CMD ["python", "-m", "core.cli", "serve", "--host", "0.0.0.0", "--port", "8080", "--grpc-port", "50051"]
