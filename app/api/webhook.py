import hmac
import hashlib
import asyncio
from fastapi import APIRouter, Request, HTTPException, Query
from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.whatsapp import WebhookPayload
from app.services.whatsapp_sender import send_text_message, send_service_list
from app.services.state_manager import state_manager
from app.services.intent_parser import parse_intent
from app.services.business_config import get_business_by_phone

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
        if msg.type not in ("text", "interactive"):
            logger.debug(f"Mensaje no-texto ignorado (tipo: {msg.type})")
            continue

        if msg.type == "interactive":
            logger.info(f"Respuesta interactiva recibida: id={msg.interactive_reply_id}, title={msg.interactive_reply_title}")
            state = await state_manager.get_state(msg.from_number)
            logger.info(f"Estado antes de guardar servicio: {state.appointment_data}")
            
            state.appointment_data["servicio"] = msg.interactive_reply_title
            state.current_intent = "agendar"
            await state_manager.save_state(state)
            logger.info(f"Servicio guardado: {state.appointment_data}")
            
            await send_text_message(
                to=msg.from_number,
                message=f"Perfecto, seleccionaste *{msg.interactive_reply_title}*. ¿Qué día te viene mejor?"
            )
            continue

        phone = msg.from_number
        text = msg.text_body
        logger.info(f"Mensaje recibido de {phone}: {text!r}")

        # 1. Obtener/crear estado con state_manager.get_state(phone)
        state = await state_manager.get_state(phone)

        # Guardar historial previo antes de añadir el nuevo mensaje para evitar duplicaciones
        history = list(state.messages)

        # 2. Agregar mensaje del usuario al historial
        state.messages.append({"role": "user", "content": text})

        # 3. Llamar parse_intent con el historial
        response_json = await parse_intent(
            phone, text, history,
            appointment_data=state.appointment_data
        )

        # Agregar la respuesta del bot al historial
        bot_response = response_json.get("respuesta") or "Hola"
        state.messages.append({"role": "assistant", "content": bot_response})

        # Actualizar datos del estado si se detectan
        if response_json.get("intent"):
            state.current_intent = response_json["intent"]
        
        for key in ["servicio", "fecha", "hora", "nombre"]:
            if response_json.get(key) is not None:
                state.appointment_data[key] = response_json[key]

        # 4. Guardar estado actualizado
        await state_manager.save_state(state)

        # 5. Responder con texto de Claude o Lista Interactiva
        servicio_guardado = state.appointment_data.get("servicio")

        # Después de guardar estado, antes del if necesita_lista
        logger.info(f"servicio_guardado: {servicio_guardado}")
        logger.info(f"intent: {response_json.get('intent')}")
        logger.info(f"servicio en response: {response_json.get('servicio')}")

        # Detectar si el cliente quiere agendar y no tiene servicio confirmado via lista interactiva
        necesita_lista = (
            response_json.get("intent") == "agendar" and 
            not servicio_guardado
        ) or (
            response_json.get("intent") == "consultar" and
            ("servicio" in text.lower() or "cuál" in text.lower() or "cuales" in text.lower() or "qué tienen" in text.lower())
        )

        if necesita_lista:
            nombre = state.appointment_data.get("nombre", "")
            saludo = f"¡Perfecto {nombre}! Te muestro nuestros servicios 😊" if nombre else "¡Con gusto! Te muestro nuestros servicios 😊"
            await send_text_message(to=phone, message=saludo)
            await asyncio.sleep(0.5)
            business = get_business_by_phone(settings.phone_number_id)
            await send_service_list(to=phone, services=business.services)
            # NO llamar send_text_message con bot_response aquí
            return {"status": "ok"}
        else:
            await send_text_message(to=phone, message=bot_response)

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
