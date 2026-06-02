import httpx
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


async def send_text_message(to: str, message: str) -> bool:
    """
    Envía un mensaje de texto usando la WhatsApp Cloud API v19.0.
    """
    # Normalizar número de teléfono de México (quitar el '1' móvil si viene como '521' y tiene 13 dígitos)
    if to.startswith("521") and len(to) == 13:
        to = "52" + to[-10:]
        logger.info(f"Número normalizado para envío: {to}")

    if not settings.phone_number_id or not settings.whatsapp_token:
        logger.error("WhatsApp credentials are not configured in settings.")
        return False


    url = f"https://graph.facebook.com/v19.0/{settings.phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {settings.whatsapp_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {
            "preview_url": False,
            "body": message,
        },
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=payload, timeout=10.0)
            
        if response.status_code in (200, 201):
            logger.info(f"Mensaje enviado con éxito a {to}")
            return True
        else:
            logger.error(
                f"Error al enviar mensaje a {to}. Estado: {response.status_code}, Respuesta: {response.text}"
            )
            return False
    except Exception as e:
        logger.exception(f"Excepción al intentar enviar mensaje a {to}: {e}")
        return False


async def send_service_list(to: str, services: list[dict]) -> bool:
    """
    Envía una lista interactiva de servicios usando la WhatsApp Cloud API v19.0.
    """
    # Normalizar número de teléfono de México (quitar el '1' móvil si viene como '521' y tiene 13 dígitos)
    if to.startswith("521") and len(to) == 13:
        to = "52" + to[-10:]
        logger.info(f"Número normalizado para envío de lista: {to}")

    if not settings.phone_number_id or not settings.whatsapp_token:
        logger.error("WhatsApp credentials are not configured in settings.")
        return False

    url = f"https://graph.facebook.com/v19.0/{settings.phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {settings.whatsapp_token}",
        "Content-Type": "application/json",
    }

    rows = []
    for svc in services:
        svc_id = str(svc.get("id", ""))
        svc_name = str(svc.get("name", ""))
        duration = svc.get("duration_min", 0)
        price = svc.get("price", 0)
        
        # WhatsApp limita el título a 24 caracteres y la descripción a 72
        title = svc_name[:24]
        description = f"Duración: {duration} min | ${price}"[:72]
        
        rows.append({
            "id": svc_id,
            "title": title,
            "description": description
        })

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "header": {
                "type": "text",
                "text": "Catálogo de Servicios"
            },
            "body": {
                "text": "Selecciona el servicio que deseas agendar:"
            },
            "footer": {
                "text": "ReservBot"
            },
            "action": {
                "button": "Ver catálogo",
                "sections": [
                    {
                        "title": "Nuestros Servicios",
                        "rows": rows
                    }
                ]
            }
        }
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=payload, timeout=10.0)
            
        if response.status_code in (200, 201):
            logger.info(f"Lista de servicios enviada con éxito a {to}")
            return True
        else:
            logger.error(
                f"Error al enviar lista a {to}. Estado: {response.status_code}, Respuesta: {response.text}"
            )
            return False
    except Exception as e:
        logger.exception(f"Excepción al intentar enviar lista a {to}: {e}")
        return False


async def _send_payload(payload: dict) -> bool:
    """
    Helper interno para enviar payloads a la API de WhatsApp Cloud.
    Normaliza el número telefónico de México (quita el '1' móvil si es de 13 dígitos).
    """
    to = payload.get("to", "")
    if to.startswith("521") and len(to) == 13:
        to = "52" + to[-10:]
        payload["to"] = to
        logger.info(f"Número normalizado para envío interno: {to}")

    if not settings.phone_number_id or not settings.whatsapp_token:
        logger.error("WhatsApp credentials are not configured in settings.")
        return False

    url = f"https://graph.facebook.com/v19.0/{settings.phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {settings.whatsapp_token}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=payload, timeout=10.0)
            
        if response.status_code in (200, 201):
            logger.info(f"Payload enviado con éxito a {to}")
            return True
        else:
            logger.error(
                f"Error al enviar payload a {to}. Estado: {response.status_code}, Respuesta: {response.text}"
            )
            return False
    except Exception as e:
        logger.exception(f"Excepción al intentar enviar payload a {to}: {e}")
        return False


async def send_time_slots_list(to: str, slots: list[str], date_str: str, service_name: str) -> None:
    """
    Envía lista interactiva de horarios disponibles.
    Máximo 10 slots por lista (límite WhatsApp).
    """
    from datetime import datetime
    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        days_es = ["Lunes","Martes","Miércoles","Jueves","Viernes","Sábado","Domingo"]
        months_es = ["enero","febrero","marzo","abril","mayo","junio","julio","agosto","septiembre","octubre","noviembre","diciembre"]
        date_readable = f"{days_es[date_obj.weekday()]} {date_obj.day} de {months_es[date_obj.month-1]}"
    except:
        date_readable = date_str

    # Agrupar slots por turno
    morning = [s for s in slots if int(s.split(":")[0]) < 12]    # 09:00 - 11:30
    afternoon = [s for s in slots if 12 <= int(s.split(":")[0]) < 16]  # 12:00 - 15:30
    evening = [s for s in slots if int(s.split(":")[0]) >= 16]   # 16:00 - 18:30

    sections = []
    if morning:
        sections.append({
            "title": "🌅 Mañana",
            "rows": [{"id": f"hora_{s.replace(':', '')}", "title": s} for s in morning]
        })
    if afternoon:
        sections.append({
            "title": "☀️ Tarde",
            "rows": [{"id": f"hora_{s.replace(':', '')}", "title": s} for s in afternoon]
        })
    if evening:
        sections.append({
            "title": "🌆 Noche",
            "rows": [{"id": f"hora_{s.replace(':', '')}", "title": s} for s in evening]
        })

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "header": {"type": "text", "text": f"📅 {date_readable}"},
            "body": {"text": f"Horarios disponibles para *{service_name}*. ¿Cuál te queda mejor?"},
            "footer": {"text": "Selecciona un horario 👇"},
            "action": {
                "button": "Ver horarios",
                "sections": sections
            }
        }
    }
    await _send_payload(payload)


