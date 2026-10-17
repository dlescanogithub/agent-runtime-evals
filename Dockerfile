# Local demo image. The default command uses the fake provider and no secrets.
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN pip install --no-cache-dir . \
    && useradd --create-home --uid 10001 appuser

USER appuser

ENV LLM_PROVIDER=fake \
    DATABASE_PATH=/tmp/runtime.sqlite \
    TRACE_DIR=/tmp/traces \
    PYTHONUNBUFFERED=1

CMD ["python", "-m", "agent_runtime.cli", "demo"]
