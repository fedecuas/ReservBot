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


async def send_time_slots_list(
    to: str,
    slots: list[str],
    date_str: str,
    service_name: str,
    id_prefix: str = "hora_",          # ← NUEVO PARÁMETRO
) -> None:
    """
    Envía una lista interactiva de WhatsApp con los slots disponibles.

    id_prefix controla el formato del ID de cada opción:
      - Flujo normal (día único):  id_prefix="hora_"
          → id resultante: "hora_09:00"
      - Flujo multi-día:           id_prefix="hora_2025-06-03_"
          → id resultante: "hora_2025-06-03_09:00"

    El webhook lee el id para saber si trae fecha embebida:
      parts = id.split("_")
      len == 2  → hora_{HH:MM}         (fecha ya guardada en state)
      len == 3  → hora_{YYYY-MM-DD}_{HH:MM}  (fecha del slot)
    """
    settings = get_settings()

    # Construir filas de la lista (máx 10 por sección en WhatsApp)
    rows = []
    for slot in slots[:10]:
        rows.append({
            "id":          f"{id_prefix}{slot}",   # ← usa el prefijo
            "title":       slot,
            "description": service_name,
        })

    # Formatear fecha legible para el header
    try:
        from datetime import datetime
        days_es   = ["lunes","martes","miércoles","jueves","viernes","sábado","domingo"]
        months_es = ["enero","febrero","marzo","abril","mayo","junio","julio","agosto",
                     "septiembre","octubre","noviembre","diciembre"]
        d = datetime.strptime(date_str, "%Y-%m-%d")
        fecha_label = f"{days_es[d.weekday()]} {d.day} de {months_es[d.month - 1]}"
    except Exception:
        fecha_label = date_str

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "header": {
                "type": "text",
                "text": f"Horarios — {fecha_label}",
            },
            "body": {
                "text": f"Selecciona el horario que prefieras para *{service_name}* 👇",
            },
            "footer": {
                "text": "Elige una hora disponible",
            },
            "action": {
                "button": "Ver horarios",
                "sections": [{
                    "title": "Horas disponibles",
                    "rows": rows,
                }],
            },
        },
    }

    # ── Enviar via Meta Cloud API ──────────────────────────────────
    import httpx
    url = f"https://graph.facebook.com/v19.0/{settings.phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {settings.whatsapp_token}",
        "Content-Type":  "application/json",
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()


