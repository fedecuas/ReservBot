import json
import os
from datetime import datetime, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _get_credentials():
    raw = settings.google_credentials_json

    try:
        info = json.loads(raw)
        return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    except (json.JSONDecodeError, ValueError):
        pass

    if os.path.exists(raw):
        return service_account.Credentials.from_service_account_file(raw, scopes=SCOPES)

    raise ValueError(f"GOOGLE_CREDENTIALS_JSON no es JSON válido ni ruta existente: {raw[:50]}")


async def create_calendar_event(appointment_data: dict) -> str | None:
    try:
        nombre = appointment_data.get("nombre", "Cliente")
        servicio = appointment_data.get("servicio", "Cita")
        fecha = appointment_data.get("fecha")
        hora = appointment_data.get("hora")

        if not fecha or not hora:
            logger.warning("create_calendar_event: falta fecha u hora")
            return None

        start_dt = datetime.strptime(f"{fecha} {hora}", "%Y-%m-%d %H:%M")
        end_dt = start_dt + timedelta(hours=1)

        creds = _get_credentials()
        service = build("calendar", "v3", credentials=creds)

        event = {
            "summary": f"{servicio} — {nombre}",
            "description": f"Cita agendada por Valentina vía WhatsApp\nCliente: {nombre}\nServicio: {servicio}",
            "start": {
                "dateTime": start_dt.isoformat(),
                "timeZone": "America/Mexico_City",
            },
            "end": {
                "dateTime": end_dt.isoformat(),
                "timeZone": "America/Mexico_City",
            },
        }

        result = service.events().insert(
            calendarId=settings.google_calendar_id,
            body=event
        ).execute()

        event_link = result.get("htmlLink")
        logger.info(f"Evento creado en Calendar: {event_link}")
        return event_link

    except Exception as e:
        logger.exception(f"Error creando evento en Calendar: {e}")
        return None
