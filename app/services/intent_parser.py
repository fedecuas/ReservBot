import json
from anthropic import AsyncAnthropic

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


async def parse_intent(phone: str, message: str, conversation_history: list[dict]) -> dict:
    """
    Analiza el mensaje del usuario con la API de Anthropic para determinar el intent y extraer datos.
    """
    fallback_response = {
        "intent": "otro",
        "servicio": None,
        "fecha": None,
        "hora": None,
        "nombre": None,
        "respuesta": "Lo siento, por el momento tengo problemas para procesar tu mensaje. ¿Podrías escribirlo de nuevo?"
    }

    if not settings.anthropic_api_key:
        logger.error("Anthropic API key no está configurada en settings.")
        return fallback_response

    # 1. Limpiar y estructurar el historial para cumplir con las reglas de Anthropic
    # Anthropic requiere alternancia estricta user <-> assistant y que empiece con user.
    raw_messages = []
    for msg in conversation_history:
        role = msg.get("role", "user")
        if role not in ("user", "assistant"):
            role = "user" if role == "user" else "assistant"
        raw_messages.append({"role": role, "content": msg.get("content", "")})

    # Añadir el mensaje actual del usuario
    raw_messages.append({"role": "user", "content": message})

    # Alternar y mezclar mensajes consecutivos del mismo rol
    messages = []
    for msg in raw_messages:
        role = msg["role"]
        content = msg["content"].strip()
        if not content:
            continue
        if messages and messages[-1]["role"] == role:
            messages[-1]["content"] += f"\n{content}"
        else:
            messages.append({"role": role, "content": content})

    # Si por alguna razón el primer mensaje no es "user", lo eliminamos o insertamos uno ficticio
    if messages and messages[0]["role"] != "user":
        messages.pop(0)

    if not messages:
        return fallback_response

    # 2. Configurar la llamada a Claude
    system_prompt = (
        "Eres el asistente de reservas de un negocio. Tu trabajo es extraer \n"
        "información de citas desde mensajes en español de WhatsApp.\n\n"
        "Responde SOLO con un JSON con esta estructura:\n"
        "{\n"
        "  \"intent\": \"agendar|consultar|cancelar|saludo|otro\",\n"
        "  \"servicio\": \"nombre del servicio o null\",\n"
        "  \"fecha\": \"YYYY-MM-DD o null\",\n"
        "  \"hora\": \"HH:MM o null\", \n"
        "  \"nombre\": \"nombre del cliente o null\",\n"
        "  \"respuesta\": \"mensaje amigable para el cliente en español\"\n"
        "}\n\n"
        "Si falta información para agendar, pídela en el campo 'respuesta'.\n"
        "Usa el historial de conversación para mantener contexto."
    )

    try:
        # Usar la API Key de settings
        client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        
        logger.info(f"Enviando consulta a Anthropic para el número {phone}")
        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            system=system_prompt,
            messages=messages
        )
        
        response_text = response.content[0].text.strip()
        
        # 3. Intentar parsear el JSON retornado
        # Eliminar posible envoltura de código markdown
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]
        response_text = response_text.strip()

        parsed_json = json.loads(response_text)
        
        # Asegurar que todas las llaves requeridas existan en el dict retornado
        required_keys = ["intent", "servicio", "fecha", "hora", "nombre", "respuesta"]
        for key in required_keys:
            if key not in parsed_json:
                parsed_json[key] = None
        
        logger.info(f"Intent detectado: {parsed_json.get('intent')} para {phone}")
        return parsed_json

    except json.JSONDecodeError as jde:
        logger.error(f"Error al decodificar JSON de la respuesta de Claude: {jde}. Respuesta original: {response_text}")
        return fallback_response
    except Exception as e:
        logger.exception(f"Excepción al llamar a la API de Anthropic: {e}")
        return fallback_response
