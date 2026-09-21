import logging

from fastapi import FastAPI
from scalar_fastapi import get_scalar_api_reference
from starlette.responses import HTMLResponse
from starlette.staticfiles import StaticFiles

from app.admin import setup_admin
from app.api.v1 import auth, catalog, me, orders, payments, prescriptions
from app.core.config import settings
from app.core.exceptions import install_exception_handlers
from app.db.session import engine

# Minimal baseline so INFO-level app logs (e.g. the console SMS sender)
# aren't silently dropped -- root logger otherwise defaults to WARNING.
# Revisit for real structured logging (PRD §7) before production.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

# docs_url disabled -- /docs is reclaimed below for Scalar instead of
# FastAPI's default Swagger UI (nicer UI, and unlike Swagger's own
# built-in "Try it out", Scalar's request console works out of the box
# against endpoints requiring the Bearer auth this API uses throughout).
app = FastAPI(title="Pharmly API", docs_url=None)

install_exception_handlers(app)


@app.get("/docs", include_in_schema=False)
async def api_docs() -> HTMLResponse:
    return get_scalar_api_reference(
        openapi_url=app.openapi_url, title=app.title, telemetry=False
    )

# Matches the client's base URL, which already bakes /v1 in (PRD §4.1:
# API_BASE_URL defaults to "https://api-dev.pharmly.app/v1") -- every path
# documented in the PRD is relative to that, so this was always meant to
# be here rather than a new deviation. /health, /docs, /admin, /uploads
# are infra/tooling, not versioned API surface, so they stay unprefixed.
API_V1_PREFIX = "/v1"

app.include_router(auth.router, prefix=API_V1_PREFIX)
app.include_router(me.router, prefix=API_V1_PREFIX)
app.include_router(prescriptions.router, prefix=API_V1_PREFIX)
app.include_router(orders.router, prefix=API_V1_PREFIX)
app.include_router(payments.router, prefix=API_V1_PREFIX)
app.include_router(catalog.router, prefix=API_V1_PREFIX)

app.mount(
    "/uploads", StaticFiles(directory=settings.local_storage_dir, check_dir=False), name="uploads"
)

setup_admin(app, engine)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
