import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers.health import router as health_router
from routers import backups, exports, processing, projects, settings, uploads

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="RVTool Genesis API",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api")
app.include_router(projects.router, prefix="/api")
app.include_router(uploads.router, prefix="/api")
app.include_router(processing.router, prefix="/api")
app.include_router(exports.router, prefix="/api")
app.include_router(settings.router, prefix="/api")
app.include_router(backups.router, prefix="/api")


@app.on_event("startup")
async def startup_event() -> None:
    logger.info("RVTool Genesis API starting...")
