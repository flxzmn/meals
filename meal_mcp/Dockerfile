# Meal MCP over HTTP for one user, e.g. a demo through a tunnel (docs/DOCKER.md).
# Claude Desktop does not need this image: it runs the MCPB bundle over stdio.
FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.9.5 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH" \
    MEAL_TRANSPORT=http \
    MEAL_HTTP_HOST=0.0.0.0 \
    MEAL_HTTP_PORT=8000 \
    MEAL_DATA_DIR=/data

WORKDIR /app

# Dependencies first, so a code change does not reinstall them.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Same runtime files as the MCPB bundle (scripts/build_mcpb.py).
COPY main.py ./
COPY config ./config
COPY db ./db
COPY repo ./repo
COPY services ./services
COPY mcp_tools ./mcp_tools
COPY data ./data

RUN useradd --create-home --uid 1000 meal && mkdir /data && chown meal /data
USER meal
VOLUME /data
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import socket; socket.create_connection(('127.0.0.1', 8000), timeout=3)"

CMD ["python", "main.py"]
