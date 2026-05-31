FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV PATH="/app/.venv/bin:${PATH}"
ENV SHINKAI_ENV=production
ENV SHINKAI_AUTH_REQUIRED=true
ENV SHINKAI_STATE_PATH=/tmp/shinkai-state.json

COPY services/api/pyproject.toml services/api/uv.lock ./
RUN uv sync --frozen --no-dev

COPY services/api/src ./src

EXPOSE 8080

CMD ["uvicorn", "shinkai_api.main:app", "--host", "0.0.0.0", "--port", "8080"]
