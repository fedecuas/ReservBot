import hmac
import hashlib
from fastapi import APIRouter, Request, HTTPException, Query
from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.whatsapp import WebhookPayload

router = APIRouter(prefix="/webhook", tags=["webhook"])
logger = get_logger(__name__)
settings = get_settings()


@router.get("")
async def verify_webhook(
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge"),
):
    """
    Meta llama este endpoint una vez para verificar que el servidor es tuyo.
    Responde con hub_challenge si el verify_token coincide.
    """
    if hub_mode == "subscribe" and hub_verify_token == settings.verify_token:
        logger.info("Webhook verificado por Meta ✓")
        return int(hub_challenge)

    logger.warning(f"Intento de verificación fallido — token: {hub_verify_token!r}")
    raise HTTPException(status_code=403, detail="Verify token inválido")


@router.post("")
async def receive_message(request: Request):
    """
    Meta envía aquí cada mensaje entrante.
    1. Valida la firma HMAC-SHA256
    2. Parsea el payload
    3. Despacha a handle_message por cada mensaje
    """
    body_bytes = await request.body()

    # ── Validar firma HMAC (obligatorio en producción) ─────────────
    if settings.is_production:
        _validate_signature(request, body_bytes)

    # ── Parsear payload ────────────────────────────────────────────
    try:
        payload = WebhookPayload.model_validate(await request.json())
    except Exception as e:
        logger.error(f"Error parseando payload: {e}")
        return {"status": "ok"}  # siempre 200 a Meta, aunque haya error interno

    # ── Despachar mensajes ─────────────────────────────────────────
    for msg in payload.extract_messages():
        if msg.type != "text":
            logger.debug(f"Mensaje no-texto ignorado (tipo: {msg.type})")
            continue

        logger.info(f"Mensaje recibido de {msg.from_number}: {msg.text_body!r}")

        # TODO semana 2: importar y llamar al orchestrator
        # from app.services.orchestrator import handle_message
        # await handle_message(msg.from_number, msg.text_body)

    return {"status": "ok"}


# ── Helpers ─────────────────────────────────────────────────────────

def _validate_signature(request: Request, body: bytes) -> None:
    signature = request.headers.get("X-Hub-Signature-256", "")
    expected = "sha256=" + hmac.new(
        settings.app_secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(signature, expected):
        logger.warning("Firma HMAC inválida — request rechazado")
        raise HTTPException(status_code=403, detail="Firma inválida")
