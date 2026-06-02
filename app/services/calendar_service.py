import json
import os
from datetime import datetime, timedelta
import pytz
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


async def check_availability(date_str: str, duration_min: int, calendar_id: str, credentials) -> list[str]:
    """
    Retorna lista de slots libres para una fecha dada.
    date_str: "YYYY-MM-DD"
    duration_min: duración del servicio en minutos
    Retorna: ["09:00", "09:30", "10:00", ...] solo los slots libres
    """
    try:
        service = build("calendar", "v3", credentials=credentials)
        
        # Rango del día laboral (09:00 - 19:00 Mexico City)
        tz = pytz.timezone("America/Mexico_City")
        day = datetime.strptime(date_str, "%Y-%m-%d")
        start_of_day = tz.localize(day.replace(hour=9, minute=0, second=0))
        end_of_day = tz.localize(day.replace(hour=19, minute=0, second=0))

        # Consultar eventos ocupados via freebusy
        body = {
            "timeMin": start_of_day.isoformat(),
            "timeMax": end_of_day.isoformat(),
            "timeZone": "America/Mexico_City",
            "items": [{"id": calendar_id}]
        }
        result = service.freebusy().query(body=body).execute()
        busy_periods = result["calendars"][calendar_id]["busy"]

        # Generar todos los slots del día (cada 30 min)
        all_slots = []
        current = start_of_day
        while current + timedelta(minutes=duration_min) <= end_of_day:
            all_slots.append(current)
            current += timedelta(minutes=30)

        # Filtrar slots ocupados
        free_slots = []
        for slot in all_slots:
            slot_end = slot + timedelta(minutes=duration_min)
            is_busy = False
            for busy in busy_periods:
                busy_start = datetime.fromisoformat(busy["start"]).astimezone(tz)
                busy_end = datetime.fromisoformat(busy["end"]).astimezone(tz)
                if slot < busy_end and slot_end > busy_start:
                    is_busy = True
                    break
            if not is_busy:
                free_slots.append(slot.strftime("%H:%M"))

        logger.info(f"Slots libres para {date_str}: {free_slots}")
        return free_slots

    except Exception as e:
        logger.exception(f"Error consultando disponibilidad: {e}")
        return []


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
        duration = appointment_data.get("duration_min", 60)
        end_dt = start_dt + timedelta(minutes=duration)

        logger.info(f"Intentando crear evento en calendarId: {settings.google_calendar_id}")
        logger.info(f"appointment_data recibido: {appointment_data}")
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

        logger.info(f"Resultado completo de Google: {result}")
        event_link = result.get("htmlLink")
        logger.info(f"Evento creado en Calendar: {event_link}")
        return event_link

    except Exception as e:
        logger.exception(f"Error creando evento en Calendar: {e}")
        return None
