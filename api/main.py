import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import settings
from routers.health import router as health_router
from routers import backups, exports, folders, processing, projects, settings as settings_router, uploads

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_DEFAULT_SECRET_KEY = "rvtool-genesis-change-me-in-production"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup actions run before yield, shutdown after."""
    logger.info("RVTool Genesis API starting...")
    if settings.secret_key == _DEFAULT_SECRET_KEY:
        logger.warning(
            "SECRET_KEY is set to the insecure default value. "
            "Cloud LLM provider API keys stored in the database are encrypted with a "
            "known key. Set a strong SECRET_KEY in your .env file before using "
            "watsonx.ai, OpenAI, or Anthropic providers."
        )
    yield
    logger.info("RVTool Genesis API shutting down.")


app = FastAPI(
    title="RVTool Genesis API",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api")
app.include_router(folders.router, prefix="/api")
app.include_router(projects.router, prefix="/api")
app.include_router(uploads.router, prefix="/api")
app.include_router(processing.router, prefix="/api")
app.include_router(exports.router, prefix="/api")
app.include_router(settings_router.router, prefix="/api")
app.include_router(backups.router, prefix="/api")
