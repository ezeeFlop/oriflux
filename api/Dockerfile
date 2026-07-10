FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:0.6.3 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

# Entrypoint is selected per service in the compose/stack file:
#   uvicorn oriflux.ingest.main:app / oriflux.api.main:app / oriflux.workers.main:app
CMD ["uvicorn", "oriflux.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
