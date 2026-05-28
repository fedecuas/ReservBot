from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.core.logging import setup_logging, get_logger
from app.core.config import get_settings
from app.routers import webhook

logger = get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info(f"BarberBot arrancando — entorno: {settings.app_env}")
    yield
    logger.info("BarberBot apagándose")


app = FastAPI(
    title="BarberBot",
    description="Agente de WhatsApp para agendar citas en barberías",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(webhook.router)


@app.get("/health")
async def health():
    return {"status": "ok", "env": settings.app_env}
