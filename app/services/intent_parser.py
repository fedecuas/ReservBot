import json
from datetime import datetime
from anthropic import AsyncAnthropic

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.business_config import get_business_by_phone

logger = get_logger(__name__)
settings = get_settings()


async def parse_intent(phone: str, message: str, conversation_history: list[dict], appointment_data: dict = {}) -> dict:
    fallback_response = {
        "intent": "otro",
        "servicio": None,
        "fecha": None,
        "fechas_candidatas": None,
        "hora": None,
        "nombre": None,
        "respuesta": "Lo siento, por el momento tengo problemas para procesar tu mensaje. ¿Podrías escribirlo de nuevo?"
    }

    if not settings.anthropic_api_key:
        logger.error("Anthropic API key no está configurada.")
        return fallback_response

    # ── Limpiar historial ──────────────────────────────────────────
    raw_messages = []
    for msg in conversation_history:
        role = msg.get("role", "user")
        if role not in ("user", "assistant"):
            role = "user"
        raw_messages.append({"role": role, "content": msg.get("content", "")})

    raw_messages.append({"role": "user", "content": message})

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

    if messages and messages[0]["role"] != "user":
        messages.pop(0)

    if not messages:
        return fallback_response

    # ── Configurar prompt ──────────────────────────────────────────
    business = await get_business_by_phone(settings.phone_number_id)
    business_name = business.name if business else "Barbería El Estilo"

    nombre = appointment_data.get("nombre") or "no proporcionado"
    servicio = appointment_data.get("servicio") or "no seleccionado"
    fecha = appointment_data.get("fecha") or "no proporcionada"
    hora = appointment_data.get("hora") or "no proporcionada"
    fechas_candidatas = appointment_data.get("fechas_candidatas") or []

    today = datetime.now().strftime("%Y-%m-%d")
    today_readable = datetime.now().strftime("%d de %B de %Y")

    # Contexto de fechas candidatas para el prompt
    candidatas_ctx = ""
    if fechas_candidatas:
        days_es = ["lunes","martes","miércoles","jueves","viernes","sábado","domingo"]
        months_es = ["enero","febrero","marzo","abril","mayo","junio","julio","agosto","septiembre","octubre","noviembre","diciembre"]
        labels = []
        for fc in fechas_candidatas:
            try:
                d = datetime.strptime(fc, "%Y-%m-%d")
                labels.append(f"{days_es[d.weekday()]} {d.day} de {months_es[d.month-1]} ({fc})")
            except:
                labels.append(fc)
        candidatas_ctx = f"- Fechas candidatas (cliente mencionó ambas): {', '.join(labels)}\n"

    system_prompt = (
        f"Eres Valentina, la recepcionista virtual de {business_name}.\n"
        f"HOY ES: {today_readable} ({today}). Usa esta fecha como referencia para calcular 'mañana', 'el lunes', etc.\n"
        f"NUNCA uses años anteriores a {datetime.now().year}.\n"
        "Tienes una personalidad cálida, profesional y empática.\n"
        "Haces sentir a cada cliente especial y bienvenido.\n\n"

        "DATOS YA RECOPILADOS:\n"
        f"- Nombre: {nombre}\n"
        f"- Servicio: {servicio}\n"
        f"- Fecha: {fecha}\n"
        f"- Hora: {hora}\n"
        f"{candidatas_ctx}\n"

        "REGLAS ESTRICTAS — SÍGUELAS AL PIE DE LA LETRA:\n"
        "1. Si NO tienes el nombre → preguntar el nombre ES TU PRIMERA PRIORIDAD.\n"
        "2. Si ya tienes el nombre → úsalo en CADA mensaje.\n"
        "3. NUNCA preguntes por datos que ya están en DATOS YA RECOPILADOS.\n"
        "4. Cuando tengas nombre+servicio+fecha+hora → intent='confirmar'.\n"
        "5. Sé cálida, usa el nombre del cliente, haz que se sienta bien atendido.\n"
        "6. Si el servicio en DATOS YA RECOPILADOS NO es 'no seleccionado', el cliente YA eligió. NUNCA vuelvas a preguntar por él.\n"
        "7. NUNCA inventes ni sugieras un servicio específico. Si el cliente no ha elegido uno, devuelve servicio=null.\n"
        "8. Solo usa intent='agendar' cuando el cliente EXPLÍCITAMENTE diga que quiere agendar, reservar o hacer una cita.\n"
        "9. Si el cliente solo saluda o da su nombre → intent='saludo'. No asumas que quiere agendar.\n"
        "10. Si el cliente pregunta por servicios, precios o disponibilidad → intent='consultar'.\n"
        "11. NUNCA uses ejemplos de servicios reales en tu respuesta como sugerencia.\n"
        "12. NUNCA menciones ni listes servicios específicos en tu respuesta. "
        "Si el cliente quiere agendar, responde ÚNICAMENTE con algo como: "
        "'¡Con mucho gusto! Aquí te muestro nuestros servicios disponibles 😊' "
        "El sistema se encargará de mostrar la lista automáticamente.\n\n"

        "MANEJO DE FECHAS MÚLTIPLES:\n"
        "13. Si el cliente menciona DOS días alternativos (ej: 'martes o miércoles', 'el lunes o el martes', "
        "'¿tienes el jueves o viernes?') → guarda AMBAS fechas calculadas en 'fechas_candidatas' "
        "como lista ['YYYY-MM-DD', 'YYYY-MM-DD'] y pon fecha=null. "
        "Responde algo como: '¡Claro! Déjame mostrarte los horarios disponibles para ambos días 😊'\n"
        "14. Si el cliente pregunta '¿qué horarios tienes?' o '¿tienes disponibilidad?' y ya hay "
        "fechas_candidatas en DATOS YA RECOPILADOS → responde con: "
        "'¡Claro! Aquí te muestro los horarios disponibles para ambos días 😊' "
        "El sistema mostrará automáticamente los slots. intent='consultar'.\n"
        "15. Si hay fechas_candidatas y el cliente confirma UN día específico → "
        "mueve esa fecha a 'fecha' (YYYY-MM-DD), pon fechas_candidatas=null.\n\n"

        "FLUJO CORRECTO:\n"
        "Paso 1 → Saludar y pedir nombre (si no lo tienes)\n"
        "Paso 2 → Preguntar en qué puedes ayudar\n"
        "Paso 3 → Si quiere agendar, responde con mensaje corto — el sistema muestra la lista\n"
        "Paso 4 → Pedir fecha\n"
        "Paso 5 → Pedir hora\n"
        "Paso 6 → Confirmar todo\n\n"

        "EJEMPLO DE TONO:\n"
        "'¡Hola! Soy Valentina 😊 ¿Con quién tengo el gusto de hablar?'\n"
        "'¡Qué gusto conocerte! ¿En qué te puedo ayudar hoy?'\n"
        "'¡Con mucho gusto! Aquí te muestro nuestros servicios disponibles 😊'\n"
        "'¡Claro! Déjame mostrarte los horarios disponibles para ambos días 😊'\n\n"

        "CRÍTICO: Tu respuesta debe ser ÚNICAMENTE el objeto JSON. "
        "Sin saludos previos, sin explicaciones, sin markdown, sin bloques de código. "
        "Solo el JSON puro comenzando con { y terminando con }.\n\n"

        "Responde SOLO con este JSON:\n"
        "{\n"
        "  \"intent\": \"agendar|consultar|cancelar|saludo|confirmar|otro\",\n"
        "  \"servicio\": \"nombre del servicio o null\",\n"
        "  \"fecha\": \"YYYY-MM-DD o null\",\n"
        "  \"fechas_candidatas\": [\"YYYY-MM-DD\", \"YYYY-MM-DD\"] o null,\n"
        "  \"hora\": \"HH:MM o null\",\n"
        "  \"nombre\": \"nombre del cliente o null\",\n"
        "  \"respuesta\": \"mensaje amigable para el cliente en español\"\n"
        "}\n"
    )

    try:
        client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        logger.info(f"Enviando consulta a Anthropic para {phone}")

        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            system=system_prompt,
            messages=messages
        )

        response_text = response.content[0].text.strip()

        # Limpiar markdown si viene
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        if response_text.startswith("```"):
            response_text = response_text[3:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]
        response_text = response_text.strip()

        parsed_json = json.loads(response_text)

        required_keys = ["intent", "servicio", "fecha", "fechas_candidatas", "hora", "nombre", "respuesta"]
        for key in required_keys:
            if key not in parsed_json:
                parsed_json[key] = None

        logger.info(f"Intent detectado: {parsed_json.get('intent')} para {phone}")
        return parsed_json

    except json.JSONDecodeError as jde:
        logger.error(f"Error JSON de Claude: {jde}. Respuesta: {response_text}")
        return fallback_response
    except Exception as e:
        logger.exception(f"Excepción Anthropic API: {e}")
        return fallback_response