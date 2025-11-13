# syntax=docker/dockerfile:1

FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md /app/
COPY assignment_bot /app/assignment_bot

RUN pip install --upgrade pip && \
    pip install .

ENTRYPOINT ["python", "-m", "assignment_bot"]
