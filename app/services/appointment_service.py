"""
Appointment Service — gestión de citas: creación, cancelación, reagendado,
log de conversaciones y notificación al dueño del negocio.
"""
import json
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.db_models import Appointment, Business, Conversation, Professional

logger = get_logger(__name__)


# ── Appointments ──────────────────────────────────────────────────────────────

async def create_appointment(
    db: Session,
    business_id: int,
    client_name: str,
    client_phone: str,
    service_name: str,
    appointment_date: str,
    appointment_time: str,
    duration_min: int = 30,
    calendar_event_id: Optional[str] = None,
    professional_id: Optional[int] = None,
) -> Appointment:
    """Registra una cita confirmada en la base de datos."""
    appt = Appointment(
        business_id=business_id,
        professional_id=professional_id,
        client_name=client_name,
        client_phone=client_phone,
        service_name=service_name,
        appointment_date=appointment_date,
        appointment_time=appointment_time,
        duration_min=duration_min,
        calendar_event_id=calendar_event_id,
        status="confirmed",
        reminder_sent=False,
    )
    db.add(appt)
    db.commit()
    db.refresh(appt)
    logger.info(f"Cita registrada: {client_name} — {service_name} — {appointment_date} {appointment_time}")
    return appt


async def cancel_appointment(
    db: Session,
    appointment_id: int,
    reason: Optional[str] = None,
) -> Optional[Appointment]:
    """Cancela una cita existente."""
    appt = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appt:
        return None
    appt.status = "cancelled"
    appt.notes = reason or appt.notes
    appt.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(appt)
    logger.info(f"Cita cancelada: id={appointment_id}")
    return appt


async def reschedule_appointment(
    db: Session,
    appointment_id: int,
    new_date: str,
    new_time: str,
    new_calendar_event_id: Optional[str] = None,
) -> Optional[Appointment]:
    """Reagenda una cita a nueva fecha/hora."""
    appt = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appt:
        return None
    appt.appointment_date = new_date
    appt.appointment_time = new_time
    appt.status = "rescheduled"
    appt.reminder_sent = False  # resetear recordatorio para la nueva fecha
    if new_calendar_event_id:
        appt.calendar_event_id = new_calendar_event_id
    appt.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(appt)
    logger.info(f"Cita reagendada: id={appointment_id} → {new_date} {new_time}")
    return appt


async def get_appointment_by_phone(
    db: Session,
    client_phone: str,
    business_id: int,
    status: str = "confirmed",
) -> Optional[Appointment]:
    """Busca la cita más reciente activa de un cliente en un negocio."""
    return (
        db.query(Appointment)
        .filter(
            Appointment.client_phone == client_phone,
            Appointment.business_id == business_id,
            Appointment.status == status,
        )
        .order_by(Appointment.created_at.desc())
        .first()
    )


async def get_appointments_pending_reminder(db: Session) -> list[Appointment]:
    """
    Devuelve citas que necesitan recordatorio:
    - Status: confirmed o rescheduled
    - Fecha: mañana
    - reminder_sent: False
    Usado por el cron job de recordatorios 24h.
    """
    from datetime import date, timedelta
    tomorrow = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
    return (
        db.query(Appointment)
        .filter(
            Appointment.appointment_date == tomorrow,
            Appointment.status.in_(["confirmed", "rescheduled"]),
            Appointment.reminder_sent == False,
        )
        .all()
    )


async def mark_reminder_sent(db: Session, appointment_id: int) -> None:
    """Marca que el recordatorio fue enviado para evitar duplicados."""
    appt = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if appt:
        appt.reminder_sent = True
        appt.updated_at = datetime.utcnow()
        db.commit()


async def list_appointments(
    db: Session,
    business_id: int,
    status: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    """Lista citas de un negocio con filtros opcionales."""
    query = db.query(Appointment).filter(Appointment.business_id == business_id)
    if status:
        query = query.filter(Appointment.status == status)
    if date_from:
        query = query.filter(Appointment.appointment_date >= date_from)
    if date_to:
        query = query.filter(Appointment.appointment_date <= date_to)

    appointments = query.order_by(Appointment.appointment_date.desc()).limit(limit).all()

    return [_appointment_to_dict(a) for a in appointments]


def _appointment_to_dict(a: Appointment) -> dict:
    return {
        "id": a.id,
        "client_name": a.client_name,
        "client_phone": a.client_phone,
        "service_name": a.service_name,
        "appointment_date": a.appointment_date,
        "appointment_time": a.appointment_time,
        "duration_min": a.duration_min,
        "status": a.status,
        "reminder_sent": a.reminder_sent,
        "professional_id": a.professional_id,
        "calendar_event_id": a.calendar_event_id,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


# ── Conversations ─────────────────────────────────────────────────────────────

async def log_conversation_message(
    db: Session,
    business_id: int,
    client_phone: str,
    client_name: Optional[str],
    role: str,      # "user" | "assistant"
    content: str,
    intent: Optional[str] = None,
) -> None:
    """
    Agrega un mensaje al log de conversación del cliente.
    Si no existe conversación activa, la crea.
    """
    conv = (
        db.query(Conversation)
        .filter(
            Conversation.business_id == business_id,
            Conversation.client_phone == client_phone,
            Conversation.ended_at.is_(None),
        )
        .first()
    )

    if not conv:
        conv = Conversation(
            business_id=business_id,
            client_phone=client_phone,
            client_name=client_name,
            messages=json.dumps([]),
            intent_log=json.dumps([]),
        )
        db.add(conv)
        db.flush()

    # Actualizar nombre si lo tenemos
    if client_name and not conv.client_name:
        conv.client_name = client_name

    # Agregar mensaje
    messages = json.loads(conv.messages or "[]")
    messages.append({
        "role": role,
        "content": content,
        "timestamp": datetime.utcnow().isoformat(),
    })
    conv.messages = json.dumps(messages)

    # Agregar intent si viene
    if intent:
        intents = json.loads(conv.intent_log or "[]")
        intents.append({
            "intent": intent,
            "timestamp": datetime.utcnow().isoformat(),
        })
        conv.intent_log = json.dumps(intents)

    conv.updated_at = datetime.utcnow()
    db.commit()


async def close_conversation(db: Session, business_id: int, client_phone: str) -> None:
    """Cierra la conversación activa de un cliente (cuando dice 'reset' o se despide)."""
    conv = (
        db.query(Conversation)
        .filter(
            Conversation.business_id == business_id,
            Conversation.client_phone == client_phone,
            Conversation.ended_at.is_(None),
        )
        .first()
    )
    if conv:
        conv.ended_at = datetime.utcnow()
        db.commit()


async def get_conversation_history(
    db: Session,
    business_id: int,
    client_phone: str,
    limit: int = 10,
) -> list[dict]:
    """Retorna las últimas N conversaciones de un cliente."""
    convs = (
        db.query(Conversation)
        .filter(
            Conversation.business_id == business_id,
            Conversation.client_phone == client_phone,
        )
        .order_by(Conversation.started_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": c.id,
            "client_name": c.client_name,
            "messages": json.loads(c.messages or "[]"),
            "intent_log": json.loads(c.intent_log or "[]"),
            "started_at": c.started_at.isoformat() if c.started_at else None,
            "ended_at": c.ended_at.isoformat() if c.ended_at else None,
        }
        for c in convs
    ]
