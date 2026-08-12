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

# Data directory for persistent SQLite storage. This one file holds both the
# context items and the API keys, so a single volume is the whole backup.
RUN mkdir -p /data
ENV TRILITH_DB_PATH=/data/trilith.db

# A container must bind 0.0.0.0, which is only safe with auth on. Mint a key
# into the mounted volume before serving traffic:
#
#   docker run --rm -v trilith_data:/data trilith \
#     python -m core.cli key create --tenant acme --name production
#
# ...or fail closed from the first request, before any key exists:
#
#   docker run -e TRILITH_REQUIRE_AUTH=1 -p 8080:8080 -v trilith_data:/data trilith
#
# Set TRILITH_REQUIRE_AUTH here to make that the image default instead.
# Trilith terminates no TLS — put a reverse proxy in front for public traffic.

# REST (8080) + gRPC (50051)
EXPOSE 8080 50051

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8080/healthz').read()"

CMD ["python", "-m", "core.cli", "serve", "--host", "0.0.0.0", "--port", "8080", "--grpc-port", "50051"]
