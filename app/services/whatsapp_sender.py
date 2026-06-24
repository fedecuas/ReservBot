import httpx
from datetime import datetime
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

DAYS_ES   = ["lunes","martes","miércoles","jueves","viernes","sábado","domingo"]
MONTHS_ES = ["enero","febrero","marzo","abril","mayo","junio","julio","agosto",
             "septiembre","octubre","noviembre","diciembre"]


def normalize_phone(phone: str) -> str:
    """Normaliza número mexicano: 5215659XXXXXX → 525659XXXXXX"""
    if phone.startswith("521") and len(phone) == 13:
        return "52" + phone[3:]
    return phone


async def _send_payload(payload: dict) -> bool:
    """Despacha cualquier payload a la WhatsApp Cloud API. Normaliza el número y maneja errores."""
    to = normalize_phone(payload.get("to", ""))
    payload["to"] = to
    logger.info(f"Enviando payload a: {to}")

    if not settings.phone_number_id or not settings.whatsapp_token:
        logger.error("WhatsApp credentials no configuradas.")
        return False

    url = f"https://graph.facebook.com/v25.0/{settings.phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {settings.whatsapp_token}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, headers=headers, json=payload, timeout=10.0)

        if resp.status_code in (200, 201):
            logger.info(f"Mensaje enviado con éxito a {to}")
            return True

        logger.error(f"WhatsApp API error {resp.status_code} → {to}: {resp.text}")
        return False
    except Exception as e:
        logger.exception(f"Excepción enviando mensaje a {to}: {e}")
        return False


async def send_text_message(to: str, message: str) -> bool:
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"preview_url": False, "body": message},
    }
    return await _send_payload(payload)


async def send_service_list(to: str, services: list[dict]) -> bool:
    rows = []
    for svc in services:
        title       = str(svc.get("name", ""))[:24]
        description = f"Duración: {svc.get('duration_min', 0)} min | ${svc.get('price', 0)}"[:72]
        rows.append({"id": str(svc.get("id", "")), "title": title, "description": description})

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "header": {"type": "text", "text": "Catálogo de Servicios"},
            "body": {"text": "Selecciona el servicio que deseas agendar:"},
            "footer": {"text": "ReservBot"},
            "action": {
                "button": "Ver catálogo",
                "sections": [{"title": "Nuestros Servicios", "rows": rows}],
            },
        },
    }
    return await _send_payload(payload)


async def send_time_slots_list(
    to: str,
    slots: list[str],
    date_str: str,
    service_name: str,
    id_prefix: str = "hora_",
) -> bool:
    rows = []
    for slot in slots[:10]:
        slot_id = slot.replace(":", "")
        rows.append({"id": f"{id_prefix}{slot_id}", "title": slot, "description": service_name})

    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        fecha_label = f"{DAYS_ES[d.weekday()]} {d.day} de {MONTHS_ES[d.month - 1]}"
    except Exception:
        fecha_label = date_str

    logger.info(f"Enviando slots a: {to}, rows: {[r['id'] for r in rows]}")

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "header": {"type": "text", "text": f"Horarios — {fecha_label}"},
            "body": {"text": f"Selecciona el horario que prefieras para *{service_name}* 👇"},
            "footer": {"text": "Elige una hora disponible"},
            "action": {
                "button": "Ver horarios",
                "sections": [{"title": "Horas disponibles", "rows": rows}],
            },
        },
    }
    return await _send_payload(payload)
