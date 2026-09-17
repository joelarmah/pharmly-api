# Pharmly API

The backend for [Pharmly](../pharmly_flutter) — a mobile-first pharmaceutical delivery and prescription app for Ghana. The Flutter mobile client is fully built and clickable end-to-end against mock data; this service is the real API it will talk to.

**Start here:** [`docs/BACKEND_API_PRD.md`](docs/BACKEND_API_PRD.md) — the full spec of every endpoint this service needs to expose, with exact request/response shapes pulled directly from what the mobile client already sends and expects.

If you're an AI agent working in this repo, also read [`AGENTS.md`](AGENTS.md) (or [`CLAUDE.md`](CLAUDE.md), same content) for working conventions before making changes.

## Stack

FastAPI · Pydantic v2 · SQLAlchemy 2.0 + Alembic · PostgreSQL · JWT auth · Paystack (payments) · pytest

## Status

Auth (§5.1), Prescriptions (§5.2), and Pharmacy pricing (§5.3) are implemented. See the PRD's §9 ("Open questions for the product owner") for decisions that need to be made before other domains (Paystack account, real pharmacy partner data, medicine catalog management) can be fully built.

Pharmacy pricing currently runs on **seeded, synthetic data** — see "Seeding pricing data" below — since no real pharmacy/POS integration exists yet (PRD §9 #4).

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

**Seeding pricing data:**

`POST /orders/pricing` needs `medication_catalog`, `pharmacies`, and `pharmacy_products` populated. Run once per environment (idempotent — safe to re-run):

```
docker compose exec api python -m scripts.seed_pricing_data
# or, without Docker:
.venv/bin/python -m scripts.seed_pricing_data
```

This loads the real 549-entry Ghana NHIS medication list plus a handful of seeded pharmacies, and generates **synthetic** per-pharmacy prices — there's no real partner pricing data yet. See `scripts/seed_pricing_data.py` for details.

**Admin panel:**

`/admin` (e.g. `http://localhost:8000/admin`) is a browsable admin UI (via [sqladmin](https://github.com/aminalaee/sqladmin)) for viewing and editing pharmacy/medication data. Pharmacies, the medication catalog, and pharmacy products are fully editable; Users, Prescriptions, and Admin Accounts are read-only (support/debugging visibility only — PIN hashes and password hashes are never shown, and export is disabled for User data since it's PII).

Login is per-person, not a shared password — there's no self-signup, so create the first account via the CLI:

```
docker compose exec api python -m scripts.manage_admin_users create <your-username>
# or, without Docker:
.venv/bin/python -m scripts.manage_admin_users create <your-username>
```

You'll be prompted for a password (never passed as a CLI argument, so it doesn't end up in shell history). Other subcommands: `list`, `disable <username>`, `enable <username>`, `set-password <username>`. See `scripts/manage_admin_users.py` for details.
