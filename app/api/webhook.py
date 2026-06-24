import hmac
import hashlib
import asyncio
from fastapi import APIRouter, Request, HTTPException, Query
from datetime import datetime
from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.whatsapp import WebhookPayload
from app.services.whatsapp_sender import send_text_message, send_service_list, send_time_slots_list
from app.services.state_manager import state_manager
from app.services.intent_parser import parse_intent
from app.services.business_config import get_business_by_phone
from app.services.calendar_service import create_calendar_event, check_availability, _get_credentials
from app.core.database import SessionLocal
from app.models.db_models import Business as BusinessModel
from app.services.appointment_service import create_appointment, log_conversation_message, close_conversation
from app.services.notification_service import notify_owner_new_appointment

router = APIRouter(prefix="/webhook", tags=["webhook"])
logger = get_logger(__name__)
settings = get_settings()

DAYS_ES   = ["lunes","martes","miércoles","jueves","viernes","sábado","domingo"]
MONTHS_ES = ["enero","febrero","marzo","abril","mayo","junio","julio","agosto",
             "septiembre","octubre","noviembre","diciembre"]


def _fecha_readable(date_str: str) -> str:
    """Convierte 'YYYY-MM-DD' → 'martes 3 de junio'. Devuelve el string original si falla."""
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        return f"{DAYS_ES[d.weekday()]} {d.day} de {MONTHS_ES[d.month - 1]}"
    except Exception:
        return date_str


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

    phone_number_id = payload.get_phone_number_id()
    if not phone_number_id:
        phone_number_id = settings.phone_number_id
    logger.debug(f"phone_number_id (tenant): {phone_number_id}")

    for msg in payload.extract_messages():
        if msg.type not in ("text", "interactive"):
            logger.debug(f"Mensaje no-texto ignorado (tipo: {msg.type})")
            continue

        # Deduplicación — Meta reenvía el mismo webhook varias veces
        msg_dedup_key = f"msg_processed:{msg.id}"
        try:
            already_processed = await state_manager.redis.set(
                msg_dedup_key, "1", nx=True, ex=60
            )
            if already_processed is None:
                logger.info(f"Mensaje duplicado ignorado: {msg.id}")
                continue
        except Exception as e:
            logger.warning(f"Redis dedup falló, procesando igual: {e}")

        # Una sola sesión DB por mensaje — se cierra en el finally
        db = SessionLocal()
        try:
            business_db = db.query(BusinessModel).filter(
                BusinessModel.phone_number_id == phone_number_id
            ).first()

            # ── Respuesta interactiva ────────────────────────────────────────────
            if msg.type == "interactive":
                logger.info(
                    f"Respuesta interactiva recibida: "
                    f"id={msg.interactive_reply_id}, title={msg.interactive_reply_title}"
                )

                if msg.interactive_reply_id and msg.interactive_reply_id.startswith("hora_"):
                    # ── Slot de horario seleccionado ─────────────────────────────
                    parts = msg.interactive_reply_id.split("_")
                    if len(parts) == 3:
                        raw_fecha = parts[1]
                        fecha_del_slot = f"{raw_fecha[:4]}-{raw_fecha[4:6]}-{raw_fecha[6:]}"
                        raw_hora = parts[2]
                        hora_del_slot = f"{raw_hora[:2]}:{raw_hora[2:]}"
                    else:
                        fecha_del_slot = None
                        hora_del_slot = msg.interactive_reply_title

                    state = await state_manager.get_state(msg.from_number)

                    if fecha_del_slot:
                        state.appointment_data["fecha"] = fecha_del_slot
                        state.appointment_data.pop("fechas_candidatas", None)

                    state.appointment_data["hora"] = hora_del_slot
                    state.current_intent = "confirmar"
                    await state_manager.save_state(state)

                    appt     = state.appointment_data
                    nombre   = appt.get("nombre", "")
                    servicio = appt.get("servicio", "")
                    fecha    = appt.get("fecha", "")

                    await send_text_message(
                        to=msg.from_number,
                        message=(
                            f"¡Perfecto {nombre}! 🎉 Confirmamos tu cita:\n\n"
                            f"✂️ *Servicio:* {servicio}\n"
                            f"📅 *Fecha:* {_fecha_readable(fecha)}\n"
                            f"⏰ *Hora:* {hora_del_slot}\n\n"
                            f"¡Te esperamos! Si necesitas cambiar algo, escríbeme 😊"
                        )
                    )

                    calendar_event_id = None
                    if all(appt.get(k) for k in ["nombre", "servicio", "fecha", "hora"]):
                        calendar_event_id = await create_calendar_event(appt)
                        if calendar_event_id is None:
                            logger.warning("Cita confirmada pero el evento de Google Calendar no se creó")

                    if business_db and all(appt.get(k) for k in ["nombre", "servicio", "fecha", "hora"]):
                        await create_appointment(
                            db=db,
                            business_id=business_db.id,
                            client_name=nombre,
                            client_phone=msg.from_number,
                            service_name=servicio,
                            appointment_date=fecha,
                            appointment_time=hora_del_slot,
                            duration_min=appt.get("duration_min", 30),
                            calendar_event_id=calendar_event_id,
                        )
                        logger.info(f"Cita guardada en DB — business_id: {business_db.id}, phone_number_id: {phone_number_id}")
                        if business_db.owner_phone:
                            await notify_owner_new_appointment(
                                owner_phone=business_db.owner_phone,
                                client_name=nombre,
                                service_name=servicio,
                                appointment_date=fecha,
                                appointment_time=hora_del_slot,
                            )
                    continue

                # ── Servicio seleccionado ────────────────────────────────────────
                if msg.interactive_reply_id and msg.interactive_reply_title:
                    state = await state_manager.get_state(msg.from_number)
                    state.appointment_data["servicio"] = msg.interactive_reply_title

                    try:
                        business = await get_business_by_phone(phone_number_id)
                        for svc in business.services:
                            if svc.get("name") == msg.interactive_reply_title:
                                state.appointment_data["duration_min"] = svc.get("duration_min", 30)
                                break
                    except Exception as e:
                        logger.error(f"Error buscando duración del servicio: {e}")

                    state.current_intent = "agendar"
                    await state_manager.save_state(state)
                    logger.info(f"Servicio guardado: {state.appointment_data}")
                    await send_text_message(
                        to=msg.from_number,
                        message=f"Perfecto, seleccionaste *{msg.interactive_reply_title}*. ¿Qué día te viene mejor?"
                    )
                continue

            # ────────────────────────────────────────────────────────────────────
            # Mensajes de texto
            # ────────────────────────────────────────────────────────────────────
            phone = msg.from_number
            text  = msg.text_body
            logger.info(f"Mensaje recibido de {phone}: {text!r}")

            # ── Comando Reset ────────────────────────────────────────────────────
            if text.strip().lower() == "reset":
                await state_manager.clear_state(phone)
                await send_text_message(
                    to=phone,
                    message="¡Hola! Soy Valentina, la recepcionista virtual 😊 ¿Con quién tengo el gusto de hablar?"
                )
                logger.info(f"Estado reseteado para {phone}")
                if business_db:
                    await close_conversation(db, business_db.id, phone)
                continue

            # ── Obtener estado ───────────────────────────────────────────────────
            state   = await state_manager.get_state(phone)
            history = list(state.messages)
            state.messages.append({"role": "user", "content": text})

            # ── Llamar a Claude ──────────────────────────────────────────────────
            response_json = await parse_intent(
                phone, text, history,
                appointment_data=state.appointment_data
            )

            bot_response = response_json.get("respuesta") or "¿En qué te puedo ayudar?"
            state.messages.append({"role": "assistant", "content": bot_response})

            # Log de conversación en DB
            if business_db:
                await log_conversation_message(
                    db=db,
                    business_id=business_db.id,
                    client_phone=phone,
                    client_name=state.appointment_data.get("nombre"),
                    role="user",
                    content=text,
                    intent=response_json.get("intent"),
                )
                await log_conversation_message(
                    db=db,
                    business_id=business_db.id,
                    client_phone=phone,
                    client_name=state.appointment_data.get("nombre"),
                    role="assistant",
                    content=bot_response,
                )

            # ── Actualizar estado ────────────────────────────────────────────────
            if response_json.get("intent"):
                state.current_intent = response_json["intent"]

            for key in ["servicio", "fecha", "hora", "nombre"]:
                if response_json.get(key) is not None:
                    state.appointment_data[key] = response_json[key]

            if response_json.get("fechas_candidatas"):
                state.appointment_data["fechas_candidatas"] = response_json["fechas_candidatas"]
                state.appointment_data["fecha"] = None
            elif response_json.get("fecha"):
                state.appointment_data.pop("fechas_candidatas", None)

            await state_manager.save_state(state)

            # ── Google Calendar + DB — confirmar cita por texto libre ────────────
            if response_json.get("intent") == "confirmar":
                appt = state.appointment_data
                if all(appt.get(k) for k in ["nombre", "servicio", "fecha", "hora"]):
                    calendar_event_id = await create_calendar_event(appt)
                    if calendar_event_id is None:
                        logger.warning("Cita confirmada (texto) pero el evento de Google Calendar no se creó")
                    if business_db:
                        await create_appointment(
                            db=db,
                            business_id=business_db.id,
                            client_name=appt.get("nombre", ""),
                            client_phone=phone,
                            service_name=appt.get("servicio", ""),
                            appointment_date=appt.get("fecha", ""),
                            appointment_time=appt.get("hora", ""),
                            duration_min=appt.get("duration_min", 30),
                            calendar_event_id=calendar_event_id,
                        )
                        logger.info(f"Cita guardada en DB (text-confirm) — business_id: {business_db.id}")
                        if business_db.owner_phone:
                            await notify_owner_new_appointment(
                                owner_phone=business_db.owner_phone,
                                client_name=appt.get("nombre", ""),
                                service_name=appt.get("servicio", ""),
                                appointment_date=appt.get("fecha", ""),
                                appointment_time=appt.get("hora", ""),
                            )

            # ── Debug logs ───────────────────────────────────────────────────────
            servicio_guardado = state.appointment_data.get("servicio")
            fechas_candidatas = state.appointment_data.get("fechas_candidatas")
            logger.info(f"servicio_guardado: {servicio_guardado}")
            logger.info(f"intent: {response_json.get('intent')}")
            logger.info(f"fecha: {response_json.get('fecha')} | fechas_candidatas: {fechas_candidatas}")
            logger.info(f"appointment_data completo: {state.appointment_data}")

            # ── Lógica de respuesta ──────────────────────────────────────────────
            intent         = response_json.get("intent")
            fecha_parseada = response_json.get("fecha") or state.appointment_data.get("fecha")
            text_lower     = text.lower()

            necesita_lista_servicios = (
                intent == "agendar" and not servicio_guardado
            ) or (
                intent == "consultar" and any(
                    p in text_lower for p in
                    ["servicio", "cuál", "cuales", "qué tienen", "que tienen", "opciones"]
                )
            )

            necesita_lista_horarios = (
                intent in ("agendar", "confirmar", "consultar")
                and servicio_guardado
                and fecha_parseada
                and not state.appointment_data.get("hora")
                and not fechas_candidatas
            )

            necesita_lista_horarios_multidia = (
                intent in ("agendar", "consultar")
                and servicio_guardado
                and fechas_candidatas
                and not state.appointment_data.get("fecha")
                and not state.appointment_data.get("hora")
            )

            logger.info(f"necesita_lista_servicios: {necesita_lista_servicios}")
            logger.info(f"necesita_lista_horarios: {necesita_lista_horarios}")
            logger.info(f"necesita_lista_horarios_multidia: {necesita_lista_horarios_multidia}")
            logger.info(f"fecha_parseada: {fecha_parseada}")

            if necesita_lista_servicios:
                business = await get_business_by_phone(phone_number_id)
                nombre_c = state.appointment_data.get("nombre", "")
                saludo = (
                    f"¡Perfecto {nombre_c}! Te muestro nuestros servicios 😊"
                    if nombre_c else
                    "¡Con gusto! Te muestro nuestros servicios 😊"
                )
                await send_text_message(to=phone, message=saludo)
                await asyncio.sleep(0.5)
                await send_service_list(to=phone, services=business.services)

            elif necesita_lista_horarios:
                business     = await get_business_by_phone(phone_number_id)
                duration_min = _get_service_duration(business.services, servicio_guardado)
                creds        = _get_credentials()

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
                            "Lo siento, no hay horarios disponibles para ese día 😔 "
                            "¿Te gustaría intentar con otra fecha?"
                        )
                    )

            elif necesita_lista_horarios_multidia:
                await _send_multiday_slots(
                    phone=phone,
                    fechas=fechas_candidatas,
                    servicio=servicio_guardado,
                    phone_number_id=phone_number_id,
                    state=state,
                    bot_response=bot_response,
                )

            else:
                await send_text_message(to=phone, message=bot_response)

        except Exception as e:
            logger.error(f"Error procesando mensaje {msg.id}: {e}")
        finally:
            db.close()

    return {"status": "ok"}


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _send_multiday_slots(
    phone: str,
    fechas: list[str],
    servicio: str,
    phone_number_id: str,
    state,
    bot_response: str | None,
) -> None:
    fechas_a_procesar = list(fechas)
    state.appointment_data.pop("fechas_candidatas", None)
    state.appointment_data["fecha"] = None
    await state_manager.save_state(state)

    business     = await get_business_by_phone(phone_number_id)
    duration_min = _get_service_duration(business.services, servicio)
    creds        = _get_credentials()

    if bot_response:
        await send_text_message(to=phone, message=bot_response)
        await asyncio.sleep(0.5)

    alguno_con_slots = False

    for fecha_cand in fechas_a_procesar:
        slots = await check_availability(
            date_str=fecha_cand,
            duration_min=duration_min,
            calendar_id=settings.google_calendar_id,
            credentials=creds
        )
        fecha_label = _fecha_readable(fecha_cand)

        if slots:
            alguno_con_slots = True
            await send_text_message(
                to=phone,
                message=f"📅 *{fecha_label.capitalize()}* — horarios disponibles:"
            )
            await asyncio.sleep(0.4)
            fecha_sin_guiones = fecha_cand.replace("-", "")
            await send_time_slots_list(
                to=phone,
                slots=slots,
                date_str=fecha_cand,
                service_name=servicio,
                id_prefix=f"hora_{fecha_sin_guiones}_",
            )
            await asyncio.sleep(0.6)
        else:
            await send_text_message(
                to=phone,
                message=f"📅 *{fecha_label.capitalize()}* — sin disponibilidad ese día 😔"
            )
            await asyncio.sleep(0.4)

    if not alguno_con_slots:
        await send_text_message(
            to=phone,
            message=(
                "Lo siento, no encontré horarios disponibles para ninguno de esos días 😔 "
                "¿Te gustaría intentar con otras fechas?"
            )
        )


def _get_service_duration(services: list[dict], service_name: str, default: int = 30) -> int:
    for svc in services:
        if svc.get("name") == service_name:
            return svc.get("duration_min", default)
    return default


def _validate_signature(request: Request, body: bytes) -> None:
    signature = request.headers.get("X-Hub-Signature-256", "")
    expected  = "sha256=" + hmac.new(
        settings.app_secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(signature, expected):
        logger.warning("Firma HMAC inválida — request rechazado")
        raise HTTPException(status_code=403, detail="Firma inválida")
