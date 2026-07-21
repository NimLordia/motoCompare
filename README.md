# motoCompare

A personalized motorcycle platform with a self-filling, source-aware specification database. Keep a garage and a dream-bike list, browse every manufacturer and model, compare bikes side by side, and ask an assistant that never invents numbers.

## What makes it interesting

- **Self-filling catalog.** Open a model nobody has viewed before and an AI research agent populates its spec sheet live — researched once, stored for every future user.
- **No ungrounded claims.** Quantitative specs come from the database, never from LLM memory. Subjective topics — engine heat, comfort, maintenance — come from researched real-owner experience, stored with source links.
- **Provenance everywhere.** Every fact is tiered: official / independently tested / community-reported / estimated. When the manufacturer's claim and the dyno disagree, you see both.
- **Personalized.** Units, market, and riding style shape every answer; compare anything against your own bike.

## Stack

React (Vite + TypeScript) · FastAPI · LangGraph · PostgreSQL · Claude API

## Running locally

Backend (Python ≥ 3.12, Docker):

```bash
docker compose up -d                 # PostgreSQL 16 on localhost:5433
cd backend
python -m venv .venv && .venv/Scripts/activate   # or: uv venv && uv sync
pip install -e ".[dev]"
alembic upgrade head                 # create the schema
python -m app.catalog.seed           # registry + demo bikes (safe to rerun)
uvicorn app.main:app --reload        # API on http://localhost:8000, docs at /docs
```

Tests run without any infrastructure: `pytest` (in-memory SQLite).

## Status

🚧 In development — catalog module implemented; architecture and module specs live in [docs/](docs/SCOPE.md).
