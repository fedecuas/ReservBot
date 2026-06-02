import hmac
import hashlib
import asyncio
from fastapi import APIRouter, Request, HTTPException, Query
from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.whatsapp import WebhookPayload
from app.services.whatsapp_sender import send_text_message, send_service_list, send_time_slots_list
from app.services.state_manager import state_manager
from app.services.intent_parser import parse_intent
from app.services.business_config import get_business_by_phone
from app.services.calendar_service import create_calendar_event, check_availability, _get_credentials

router = APIRouter(prefix="/webhook", tags=["webhook"])
logger = get_logger(__name__)
settings = get_settings()


@router.get("")
async def verify_webhook(
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge"),
):
    if hub_mode == "subscribe" and hub_verify_token == settings.verify_token:
        logger.info("Webhook verificado por Meta ✓")
        return int(hub_challenge)

    logger.warning(f"Intento de verificación fallido — token: {hub_verify_token!r}")
    raise HTTPException(status_code=403, detail="Verify token inválido")


@router.post("")
async def receive_message(request: Request):
    body_bytes = await request.body()

    if settings.is_production:
        _validate_signature(request, body_bytes)

    try:
        payload = WebhookPayload.model_validate(await request.json())
    except Exception as e:
        logger.error(f"Error parseando payload: {e}")
        return {"status": "ok"}

    # ── Extraer phone_number_id del payload (Tenant ID) ────────────
    phone_number_id = payload.get_phone_number_id()
    if not phone_number_id:
        phone_number_id = settings.phone_number_id
    logger.debug(f"phone_number_id (tenant): {phone_number_id}")

    for msg in payload.extract_messages():
        if msg.type not in ("text", "interactive"):
            logger.debug(f"Mensaje no-texto ignorado (tipo: {msg.type})")
            continue

        # ── Manejo de respuesta interactiva (selección de servicio) ──
        if msg.type == "interactive":
            logger.info(f"Respuesta interactiva recibida: id={msg.interactive_reply_id}, title={msg.interactive_reply_title}")
            
            if msg.interactive_reply_id.startswith("hora_"):
                # Usuario seleccionó un horario de la lista
                hora_seleccionada = msg.interactive_reply_title  # "15:00"
                state = await state_manager.get_state(msg.from_number)
                state.appointment_data["hora"] = hora_seleccionada
                state.current_intent = "confirmar"
                await state_manager.save_state(state)
                
                appt = state.appointment_data
                nombre = appt.get("nombre", "")
                servicio = appt.get("servicio", "")
                fecha = appt.get("fecha", "")
                
                # Formatear fecha legible
                try:
                    from datetime import datetime
                    date_obj = datetime.strptime(fecha, "%Y-%m-%d")
                    days_es = ["lunes","martes","miércoles","jueves","viernes","sábado","domingo"]
                    months_es = ["enero","febrero","marzo","abril","mayo","junio","julio","agosto","septiembre","octubre","noviembre","diciembre"]
                    fecha_readable = f"{days_es[date_obj.weekday()]} {date_obj.day} de {months_es[date_obj.month-1]}"
                except:
                    fecha_readable = fecha
                
                await send_text_message(
                    to=msg.from_number,
                    message=(
                        f"¡Perfecto {nombre}! 🎉 Confirmamos tu cita:\n\n"
                        f"✂️ *Servicio:* {servicio}\n"
                        f"📅 *Fecha:* {fecha_readable}\n"
                        f"⏰ *Hora:* {hora_seleccionada}\n\n"
                        f"¡Te esperamos! Si necesitas cambiar algo, escríbeme 😊"
                    )
                )
                
                # Crear evento en Google Calendar
                if all(appt.get(k) for k in ["nombre", "servicio", "fecha", "hora"]):
                    await create_calendar_event(appt)
                continue

            state = await state_manager.get_state(msg.from_number)
            state.appointment_data["servicio"] = msg.interactive_reply_title
            
            # Lookup and save duration_min
            try:
                business = await get_business_by_phone(phone_number_id)
                for svc in business.services:
                    if svc.get("name") == msg.interactive_reply_title:
                        state.appointment_data["duration_min"] = svc.get("duration_min", 30)
                        break
            except Exception as e:
                logger.error(f"Error looking up duration for service: {e}")

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

        # ── Comando Reset ──────────────────────────────────────────
        if text.strip().lower() == "reset":
            await state_manager.clear_state(phone)
            await send_text_message(
                to=phone,
                message="¡Hola! Soy Valentina, la recepcionista virtual 😊 ¿Con quién tengo el gusto de hablar?"
            )
            logger.info(f"Estado reseteado para {phone}")
            continue

        # ── Obtener estado ─────────────────────────────────────────
        state = await state_manager.get_state(phone)
        history = list(state.messages)
        state.messages.append({"role": "user", "content": text})

        # ── Llamar a Claude ────────────────────────────────────────
        response_json = await parse_intent(
            phone, text, history,
            appointment_data=state.appointment_data
        )

        bot_response = response_json.get("respuesta") or "¿En qué te puedo ayudar?"
        state.messages.append({"role": "assistant", "content": bot_response})

        # ── Actualizar estado ──────────────────────────────────────
        if response_json.get("intent"):
            state.current_intent = response_json["intent"]

        for key in ["servicio", "fecha", "hora", "nombre"]:
            if response_json.get(key) is not None:
                state.appointment_data[key] = response_json[key]

        await state_manager.save_state(state)

        # ── Google Calendar ────────────────────────────────────────
        if response_json.get("intent") == "confirmar":
            appt = state.appointment_data
            if all(appt.get(k) for k in ["nombre", "servicio", "fecha", "hora"]):
                await create_calendar_event(appt)

        # ── Debug logs ─────────────────────────────────────────────
        servicio_guardado = state.appointment_data.get("servicio")
        logger.info(f"servicio_guardado: {servicio_guardado}")
        logger.info(f"intent: {response_json.get('intent')}")
        logger.info(f"servicio en response: {response_json.get('servicio')}")

        # ── Responder ──────────────────────────────────────────────
        intent = response_json.get("intent")
        fecha_parseada = response_json.get("fecha") or state.appointment_data.get("fecha")
        servicio_guardado = state.appointment_data.get("servicio")
        text_lower = text.lower()

        necesita_lista_servicios = (
            intent == "agendar" and not servicio_guardado
        ) or (
            intent == "consultar" and any(
                palabra in text_lower for palabra in
                ["servicio", "cuál", "cuales", "qué tienen", "que tienen", "opciones"]
            )
        )

        necesita_lista_horarios = (
            intent in ("agendar", "confirmar")
            and servicio_guardado
            and fecha_parseada
            and not state.appointment_data.get("hora")
        )

        if necesita_lista_servicios:
            business = await get_business_by_phone(phone_number_id)
            nombre = state.appointment_data.get("nombre", "")
            saludo = f"¡Perfecto {nombre}! Te muestro nuestros servicios 😊" if nombre else "¡Con gusto! Te muestro nuestros servicios 😊"
            await send_text_message(to=phone, message=saludo)
            await asyncio.sleep(0.5)
            await send_service_list(to=phone, services=business.services)

        elif necesita_lista_horarios:
            business = await get_business_by_phone(phone_number_id)
            # Obtener duration_min del servicio seleccionado
            duration_min = 30
            for svc in business.services:
                if svc.get("name") == servicio_guardado:
                    duration_min = svc.get("duration_min", 30)
                    break

            creds = _get_credentials()
            slots = await check_availability(
                date_str=fecha_parseada,
                duration_min=duration_min,
                calendar_id=settings.google_calendar_id,
                credentials=creds
            )

            if slots:
                await send_text_message(to=phone, message=bot_response)
                await asyncio.sleep(0.5)
                await send_time_slots_list(
                    to=phone,
                    slots=slots,
                    date_str=fecha_parseada,
                    service_name=servicio_guardado
                )
            else:
                await send_text_message(
                    to=phone,
                    message=(
                        f"Lo siento, no hay horarios disponibles para ese día 😔 "
                        f"¿Te gustaría intentar con otra fecha?"
                    )
                )

        else:
            await send_text_message(to=phone, message=bot_response)

    return {"status": "ok"}


# ── Helpers ────────────────────────────────────────────────────────

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
