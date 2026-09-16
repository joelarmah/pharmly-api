# Pharmly API

The backend for [Pharmly](../pharmly_flutter) — a mobile-first pharmaceutical delivery and prescription app for Ghana. The Flutter mobile client is fully built and clickable end-to-end against mock data; this service is the real API it will talk to.

**Start here:** [`docs/BACKEND_API_PRD.md`](docs/BACKEND_API_PRD.md) — the full spec of every endpoint this service needs to expose, with exact request/response shapes pulled directly from what the mobile client already sends and expects.

If you're an AI agent working in this repo, also read [`AGENTS.md`](AGENTS.md) (or [`CLAUDE.md`](CLAUDE.md), same content) for working conventions before making changes.

## Stack

FastAPI · Pydantic v2 · SQLAlchemy 2.0 + Alembic · PostgreSQL · JWT auth · Paystack (payments) · pytest

## Status

Auth domain (PRD §5.1) is implemented. See the PRD's §9 ("Open questions for the product owner") for decisions that need to be made before other domains (Paystack account, pharmacy partner data, medicine catalog management) can be fully built.

## Running locally

**Docker (recommended):**

```
cp .env.example .env   # then fill in JWT_SECRET and (optionally) ARKESEL_API_KEY
docker compose up --build
```

This starts Postgres and the API, running migrations automatically on startup. The API is then at `http://localhost:8000` (`/docs` for interactive OpenAPI docs).

**Without Docker:**

```
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env   # point DATABASE_URL at your own Postgres
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload
```

**Tests and linting:**

```
.venv/bin/pytest
.venv/bin/ruff check .
```
