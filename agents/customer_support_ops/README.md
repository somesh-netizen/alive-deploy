# customer_support_ops — ALIVE network bundle

Customer support operations network with order and billing agents.

Self-contained agent network packaged with the neuro-san runtime and a small
console UI. Configure LLM keys in the browser and talk to the network.

## Run

```bash
docker compose up --build
```

Open http://localhost:8080 — set at least one LLM provider key (OpenAI,
Anthropic, Gemini, Azure, Bedrock, NVIDIA, OpenRouter, or Ollama), save, and the
runtime starts. Then use the Talk tab.

Keys are written to `./data/.env` at runtime and are **never baked into the
image**. You can also `cp .env.example .env` and edit it by hand.

## What's inside
- `registries/` — the network (self-contained HOCON).
- `coded_tools/` — the coded tools it uses.
- `config/llm_config.hocon` — all providers with fallbacks.
- `console/` — the config + Talk UI and proxy.

## Deploy to a cloud (one-click, cloud-agnostic)
See `deploy/`. Build & push the image with `deploy/build_and_push.sh <registry>`,
then `terraform apply` in `deploy/terraform/<aws|gcp|azure>` (each provisions a
container service — ECS/Cloud Run/Container Apps — from the pushed image, with
the LLM keys wired as secrets).
