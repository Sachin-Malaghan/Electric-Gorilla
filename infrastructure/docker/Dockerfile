FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml ./
COPY shunya ./shunya
RUN pip install --no-cache-dir ".[anthropic,redis,postgres]"
COPY agents ./agents
COPY prompts ./prompts
COPY apps ./apps
COPY docs ./docs
COPY unreal ./unreal

EXPOSE 8400
CMD ["shunya", "serve", "--host", "0.0.0.0", "--port", "8400"]
