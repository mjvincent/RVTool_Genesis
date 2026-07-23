import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.auth import require_token
from core.config import settings
from routers.health import router as health_router
from routers import backups, exports, folders, pricing_template, processing, projects, settings as settings_router, uploads
from services.job_worker import requeue_stale_jobs, run_worker_loop
# schemas/pricing_template imported via the router; no top-level import needed

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_DEFAULT_SECRET_KEY = "rvtool-genesis-change-me-in-production"
_RECOMMENDATION_CHECK_INTERVAL = 7 * 24 * 3600  # 7 days in seconds


async def _recommendation_checker_loop() -> None:
    """Background task: check for model recommendations at startup and weekly.

    Runs once immediately on startup, then sleeps for 7 days and repeats.
    Only logs the result — the UI polls GET /api/settings/model-recommendation
    on the Settings page load; there is no push mechanism.
    """
    from db.database import AsyncSessionLocal
    from services.model_catalog import get_recommendation
    from routers.settings import _get_or_create_row, _active_model

    while True:
        try:
            async with AsyncSessionLocal() as db:
                row = await _get_or_create_row(db)
                rec = get_recommendation(row.provider, _active_model(row))
                if rec:
                    logger.info(
                        "Model recommendation available — provider=%s current=%s recommended=%s reason=%r",
                        rec.provider, rec.current_model, rec.recommended_model, rec.reason,
                    )
                else:
                    logger.info(
                        "Model recommendation check complete — no upgrade available for provider=%s",
                        row.provider,
                    )
        except Exception:  # noqa: BLE001
            logger.exception("Model recommendation check failed — will retry in 7 days")

        await asyncio.sleep(_RECOMMENDATION_CHECK_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup actions run before yield, shutdown after."""
    logger.info("RVTool Genesis API starting...")
    if settings.secret_key == _DEFAULT_SECRET_KEY:
        raise RuntimeError(
            "\n\n"
            "  ╔══════════════════════════════════════════════════════════════╗\n"
            "  ║  STARTUP BLOCKED — insecure SECRET_KEY detected             ║\n"
            "  ║                                                              ║\n"
            "  ║  The SECRET_KEY is still set to the known default value.    ║\n"
            "  ║  All stored cloud LLM API keys are encrypted with this key  ║\n"
            "  ║  and can be decrypted by anyone who knows the default.      ║\n"
            "  ║                                                              ║\n"
            "  ║  Generate a strong key and add it to your .env file:        ║\n"
            "  ║    make generate-secret                                     ║\n"
            "  ║  or:                                                         ║\n"
            "  ║    openssl rand -hex 32                                      ║\n"
            "  ╚══════════════════════════════════════════════════════════════╝\n"
        )
    if len(settings.secret_key) < 32:
        raise RuntimeError(
            "SECRET_KEY must be at least 32 characters. "
            "Generate one with: openssl rand -hex 32"
        )

    # Re-queue any processing jobs that were in_progress when the API last stopped.
    # The job worker uses a durable PostgreSQL-backed queue, so jobs survive restarts.
    await requeue_stale_jobs()

    recommendation_task = asyncio.create_task(_recommendation_checker_loop())
    worker_task = asyncio.create_task(run_worker_loop())
    yield
    worker_task.cancel()
    recommendation_task.cancel()
    for task in (worker_task, recommendation_task):
        try:
            await task
        except asyncio.CancelledError:
            pass
    logger.info("RVTool Genesis API shutting down.")


app = FastAPI(
    title="RVTool Genesis API",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health check is always open — used by Docker and monitoring without auth.
app.include_router(health_router, prefix="/api")

# All other routers are protected by the optional bearer-token dependency.
# When API_TOKEN is not set (the default), require_token is a no-op.
_auth = [Depends(require_token)]
app.include_router(folders.router,           prefix="/api", dependencies=_auth)
app.include_router(projects.router,          prefix="/api", dependencies=_auth)
app.include_router(uploads.router,           prefix="/api", dependencies=_auth)
app.include_router(processing.router,        prefix="/api", dependencies=_auth)
app.include_router(exports.router,           prefix="/api", dependencies=_auth)
app.include_router(settings_router.router,   prefix="/api", dependencies=_auth)
app.include_router(backups.router,           prefix="/api", dependencies=_auth)
app.include_router(pricing_template.router,  prefix="/api", dependencies=_auth)
