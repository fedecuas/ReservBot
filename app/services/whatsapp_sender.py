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

