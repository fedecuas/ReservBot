# Arquitectura de ReservBot

ReservBot es un agente conversacional para WhatsApp que ayuda a automatizar las reservas de citas utilizando Inteligencia Artificial.

## Stack Tecnológico

- **Framework Web**: FastAPI (Python 3.12+)
- **IA/LLM**: Anthropic Claude API (`claude-sonnet-4-20250514`) para el procesamiento de lenguaje natural y extracción de intenciones (intent parsing).
- **Validación de Datos**: Pydantic v2
- **Integración de Mensajería**: WhatsApp Business Cloud API (Meta API)
- **Gestión de Estado**: `StateManager` en memoria (con soporte preparado para Redis)
- **Base de Pruebas**: pytest con soporte asíncrono (`anyio`)

## Componentes Principales

1. **`app/main.py`**: Punto de entrada de la aplicación FastAPI.
2. **`app/routers/webhook.py`**: Endpoint receptor para la API de WhatsApp. Controla la firma de seguridad HMAC, extrae mensajes, maneja respuestas interactivas, y despacha la lógica del bot.
3. **`app/services/intent_parser.py`**: Conector con Anthropic. Contiene la personalidad del agente ("Valentina") y procesa la conversación actual usando datos estructurados en formato JSON.
4. **`app/services/whatsapp_sender.py`**: Servicio encargado de normalizar teléfonos y enviar mensajes (de texto o interactivos) de vuelta a Meta.
5. **`app/services/state_manager.py`**: Persistencia temporal de la sesión del cliente, guardando el historial de mensajes e información recopilada (`appointment_data`).
6. **`app/services/business_config.py`**: Configuración estática y catálogos de servicios del negocio.
