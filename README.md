# BarberBot 💈

> Agente de WhatsApp con LLM que agenda citas automáticamente para barberías en LATAM.

## Setup rápido

```bash
# 1. Clonar y entrar
git clone https://github.com/tu-usuario/barberbot
cd barberbot

# 2. Entorno virtual
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 3. Dependencias
pip install -r requirements.txt

# 4. Variables de entorno
cp .env.example .env
# Edita .env con tus tokens reales

# 5. Correr en local
uvicorn app.main:app --reload --port 8000
```

## Exponer el webhook localmente (para Meta)

```bash
ngrok http 8000
# Copia la URL https://xxx.ngrok.io/webhook → Meta for Developers → Configuration
```

## Tests

```bash
pytest tests/ -v
```

## Stack

- **Framework**: FastAPI + Uvicorn
- **LLM**: Claude claude-sonnet-4-20250514 (Anthropic)
- **Mensajería**: WhatsApp Cloud API (Meta)
- **Calendario**: Google Calendar API
- **State**: Redis (o SQLite en local)
- **Deploy**: Railway

## Variables de entorno

Ver `.env.example` para la lista completa.

## Estructura

```
barberbot/
├── app/
│   ├── main.py              # Entry point FastAPI
│   ├── core/
│   │   ├── config.py        # Settings con pydantic-settings
│   │   └── logging.py       # Logger configurado
│   ├── routers/
│   │   └── webhook.py       # GET + POST /webhook
│   ├── models/
│   │   └── whatsapp.py      # Pydantic models del payload WA
│   └── services/            # (semana 2) orchestrator, claude, calendar
├── tests/
│   └── test_webhook.py
├── .env.example
├── Procfile                 # Railway deploy
├── railway.json
└── requirements.txt
```
