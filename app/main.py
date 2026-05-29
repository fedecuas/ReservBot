from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.core.logging import setup_logging, get_logger
from app.core.config import get_settings
from app.api import webhook

settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger = get_logger(__name__)
    logger.info(f"ReservBot arrancando — entorno: {settings.app_env}")
    yield
    logger.info("ReservBot apagándose")

app = FastAPI(
    title="ReservBot",
    description="Agente de WhatsApp para agendar citas",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(webhook.router)

@app.get("/health")
async def health():
    return {"status": "ok", "env": settings.app_env}
