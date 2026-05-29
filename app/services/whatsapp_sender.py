import httpx
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


async def send_text_message(to: str, message: str) -> bool:
    """
    Envía un mensaje de texto usando la WhatsApp Cloud API v19.0.
    """
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
