# Pharmly API

The backend for [Pharmly](../pharmly_flutter) — a mobile-first pharmaceutical delivery and prescription app for Ghana. The Flutter mobile client is fully built and clickable end-to-end against mock data; this service is the real API it will talk to.

**Start here:** [`docs/BACKEND_API_PRD.md`](docs/BACKEND_API_PRD.md) — the full spec of every endpoint this service needs to expose, with exact request/response shapes pulled directly from what the mobile client already sends and expects.

If you're an AI agent working in this repo, also read [`AGENTS.md`](AGENTS.md) (or [`CLAUDE.md`](CLAUDE.md), same content) for working conventions before making changes.

## Stack

FastAPI · Pydantic v2 · SQLAlchemy 2.0 + Alembic · PostgreSQL · JWT auth · Paystack (payments) · pytest

## Status

Pre-implementation — this repo currently holds only the PRD and agent guidance. See the PRD's §9 ("Open questions for the product owner") for decisions that need to be made before some domains (SMS provider, Paystack account, pharmacy partner data, medicine catalog management) can be fully built.
