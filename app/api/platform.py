"""
EQKO Platform API v2 — agrega endpoints para:
- Citas (appointments): listar, cancelar, reagendar
- Conversaciones: historial por cliente
- Profesionales: CRUD
- Métricas por negocio
- Jobs: trigger manual de recordatorios
"""
import os
from fastapi import APIRouter, Depends, HTTPException, Query, Header
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
from datetime import date, timedelta

from app.core.database import get_db
from app.core.logging import get_logger
from app.models.db_models import Appointment, Conversation, Professional, Business
from app.services.appointment_service import (
    list_appointments,
    cancel_appointment,
    reschedule_appointment,
)
from app.services.platform_service import (
    get_all_businesses, get_business_detail, create_business,
    update_business, delete_business, get_business_health,
    upsert_services, upsert_hours, get_platform_metrics,
)
from app.schemas.platform import (
    BusinessCreate, BusinessUpdate, ServicesUpdate, HoursUpdate,
    ProfessionalCreate, ProfessionalUpdate, RescheduleRequest,
)

router = APIRouter(prefix="/platform", tags=["platform"])
logger = get_logger(__name__)


# ══════════════════════════════════════════════════════════════════
# BUSINESSES (existentes — sin cambios)
# ══════════════════════════════════════════════════════════════════

@router.get("/businesses")
async def list_businesses(
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    return await get_all_businesses(db, status=status)


@router.post("/businesses", status_code=201)
async def create_new_business(payload: BusinessCreate, db: Session = Depends(get_db)):
    try:
        return await create_business(db, payload)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/businesses/{business_id}")
async def get_business(business_id: int, db: Session = Depends(get_db)):
    b = await get_business_detail(db, business_id)
    if not b:
        raise HTTPException(status_code=404, detail="Negocio no encontrado")
    return b


@router.patch("/businesses/{business_id}")
async def update_business_info(
    business_id: int, payload: BusinessUpdate, db: Session = Depends(get_db)
):
    b = await update_business(db, business_id, payload)
    if not b:
        raise HTTPException(status_code=404, detail="Negocio no encontrado")
    return b


@router.delete("/businesses/{business_id}", status_code=204)
async def remove_business(business_id: int, db: Session = Depends(get_db)):
    if not await delete_business(db, business_id):
        raise HTTPException(status_code=404, detail="Negocio no encontrado")


@router.get("/businesses/{business_id}/health")
async def business_health(business_id: int, db: Session = Depends(get_db)):
    h = await get_business_health(db, business_id)
    if not h:
        raise HTTPException(status_code=404, detail="Negocio no encontrado")
    return h


@router.put("/businesses/{business_id}/services")
async def set_services(
    business_id: int, payload: ServicesUpdate, db: Session = Depends(get_db)
):
    r = await upsert_services(db, business_id, payload.services)
    if r is None:
        raise HTTPException(status_code=404, detail="Negocio no encontrado")
    return r


@router.put("/businesses/{business_id}/hours")
async def set_hours(
    business_id: int, payload: HoursUpdate, db: Session = Depends(get_db)
):
    r = await upsert_hours(db, business_id, payload.hours)
    if r is None:
        raise HTTPException(status_code=404, detail="Negocio no encontrado")
    return r


@router.get("/metrics")
async def platform_metrics(db: Session = Depends(get_db)):
    return await get_platform_metrics(db)


# ══════════════════════════════════════════════════════════════════
# PROFESSIONALS — NUEVO
# ══════════════════════════════════════════════════════════════════

@router.get("/businesses/{business_id}/professionals")
async def list_professionals(business_id: int, db: Session = Depends(get_db)):
    """Lista los profesionales de un negocio."""
    profs = db.query(Professional).filter(
        Professional.business_id == business_id
    ).order_by(Professional.name).all()

    return {"professionals": [_prof_to_dict(p) for p in profs]}


@router.post("/businesses/{business_id}/professionals", status_code=201)
async def create_professional(
    business_id: int,
    payload: ProfessionalCreate,
    db: Session = Depends(get_db),
):
    """Agrega un nuevo profesional al negocio."""
    business = db.query(Business).filter(Business.id == business_id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Negocio no encontrado")

    prof = Professional(
        business_id=business_id,
        name=payload.name,
        phone=payload.phone,
        calendar_id=payload.calendar_id,
        active=True,
        accepts_walkins=payload.accepts_walkins or False,
    )
    db.add(prof)
    db.commit()
    db.refresh(prof)
    return _prof_to_dict(prof)


@router.patch("/businesses/{business_id}/professionals/{prof_id}")
async def update_professional(
    business_id: int,
    prof_id: int,
    payload: ProfessionalUpdate,
    db: Session = Depends(get_db),
):
    """Actualiza datos de un profesional."""
    prof = db.query(Professional).filter(
        Professional.id == prof_id,
        Professional.business_id == business_id,
    ).first()
    if not prof:
        raise HTTPException(status_code=404, detail="Profesional no encontrado")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(prof, field, value)
    db.commit()
    db.refresh(prof)
    return _prof_to_dict(prof)


@router.delete("/businesses/{business_id}/professionals/{prof_id}", status_code=204)
async def delete_professional(
    business_id: int, prof_id: int, db: Session = Depends(get_db)
):
    """Elimina (desactiva) un profesional."""
    prof = db.query(Professional).filter(
        Professional.id == prof_id,
        Professional.business_id == business_id,
    ).first()
    if not prof:
        raise HTTPException(status_code=404, detail="Profesional no encontrado")
    prof.active = False
    db.commit()


# ══════════════════════════════════════════════════════════════════
# APPOINTMENTS — NUEVO
# ══════════════════════════════════════════════════════════════════

@router.get("/businesses/{business_id}/appointments")
async def get_appointments(
    business_id: int,
    status: Optional[str] = Query(None, description="confirmed|cancelled|rescheduled|completed|no_show"),
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD"),
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
):
    """Lista las citas de un negocio con filtros opcionales."""
    return {
        "appointments": await list_appointments(
            db, business_id, status=status,
            date_from=date_from, date_to=date_to, limit=limit
        )
    }


@router.patch("/appointments/{appointment_id}/cancel")
async def cancel_appt(
    appointment_id: int,
    reason: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Cancela una cita."""
    appt = await cancel_appointment(db, appointment_id, reason=reason)
    if not appt:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    return {"id": appt.id, "status": appt.status}


@router.patch("/appointments/{appointment_id}/reschedule")
async def reschedule_appt(
    appointment_id: int,
    payload: RescheduleRequest,
    db: Session = Depends(get_db),
):
    """Reagenda una cita a nueva fecha/hora."""
    appt = await reschedule_appointment(
        db, appointment_id,
        new_date=payload.new_date,
        new_time=payload.new_time,
        new_calendar_event_id=payload.new_calendar_event_id,
    )
    if not appt:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    return {"id": appt.id, "status": appt.status, "date": appt.appointment_date, "time": appt.appointment_time}


# ══════════════════════════════════════════════════════════════════
# CONVERSATIONS — NUEVO
# ══════════════════════════════════════════════════════════════════

@router.get("/businesses/{business_id}/conversations")
async def get_conversations(
    business_id: int,
    client_phone: Optional[str] = Query(None),
    limit: int = Query(20, le=100),
    db: Session = Depends(get_db),
):
    """Lista conversaciones de un negocio. Filtra por número de cliente si se especifica."""
    query = db.query(Conversation).filter(Conversation.business_id == business_id)
    if client_phone:
        query = query.filter(Conversation.client_phone == client_phone)

    convs = query.order_by(Conversation.started_at.desc()).limit(limit).all()
    import json
    return {
        "conversations": [
            {
                "id": c.id,
                "client_phone": c.client_phone,
                "client_name": c.client_name,
                "message_count": len(json.loads(c.messages or "[]")),
                "started_at": c.started_at.isoformat() if c.started_at else None,
                "ended_at": c.ended_at.isoformat() if c.ended_at else None,
            }
            for c in convs
        ]
    }


@router.get("/businesses/{business_id}/conversations/{conversation_id}")
async def get_conversation_detail(
    business_id: int,
    conversation_id: int,
    db: Session = Depends(get_db),
):
    """Detalle completo de una conversación con todos los mensajes."""
    import json
    conv = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.business_id == business_id,
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    return {
        "id": conv.id,
        "client_phone": conv.client_phone,
        "client_name": conv.client_name,
        "messages": json.loads(conv.messages or "[]"),
        "intent_log": json.loads(conv.intent_log or "[]"),
        "started_at": conv.started_at.isoformat() if conv.started_at else None,
        "ended_at": conv.ended_at.isoformat() if conv.ended_at else None,
    }


# ══════════════════════════════════════════════════════════════════
# MÉTRICAS POR NEGOCIO — NUEVO
# ══════════════════════════════════════════════════════════════════

@router.get("/businesses/{business_id}/metrics")
async def business_metrics(
    business_id: int,
    db: Session = Depends(get_db),
):
    """
    Métricas específicas de un negocio:
    - Total de citas por status
    - Citas esta semana / este mes
    - Servicios más solicitados
    - Tasa de cancelación
    """
    today = date.today()
    week_start = (today - timedelta(days=today.weekday())).strftime("%Y-%m-%d")
    month_start = today.replace(day=1).strftime("%Y-%m-%d")
    today_str = today.strftime("%Y-%m-%d")

    # Total por status
    by_status = dict(
        db.query(Appointment.status, func.count(Appointment.id))
        .filter(Appointment.business_id == business_id)
        .group_by(Appointment.status)
        .all()
    )

    total = sum(by_status.values())
    cancelled = by_status.get("cancelled", 0)
    cancel_rate = round((cancelled / total * 100), 1) if total > 0 else 0

    # Esta semana
    week_count = db.query(Appointment).filter(
        Appointment.business_id == business_id,
        Appointment.appointment_date >= week_start,
        Appointment.appointment_date <= today_str,
        Appointment.status.in_(["confirmed", "rescheduled", "completed"]),
    ).count()

    # Este mes
    month_count = db.query(Appointment).filter(
        Appointment.business_id == business_id,
        Appointment.appointment_date >= month_start,
        Appointment.status.in_(["confirmed", "rescheduled", "completed"]),
    ).count()

    # Top servicios
    top_services = (
        db.query(Appointment.service_name, func.count(Appointment.id).label("count"))
        .filter(Appointment.business_id == business_id)
        .group_by(Appointment.service_name)
        .order_by(func.count(Appointment.id).desc())
        .limit(5)
        .all()
    )

    # Conversaciones
    total_convs = db.query(Conversation).filter(
        Conversation.business_id == business_id
    ).count()

    return {
        "business_id": business_id,
        "appointments": {
            "total": total,
            "by_status": by_status,
            "this_week": week_count,
            "this_month": month_count,
            "cancellation_rate_pct": cancel_rate,
        },
        "top_services": [
            {"service": s, "count": c} for s, c in top_services
        ],
        "total_conversations": total_convs,
    }


# ══════════════════════════════════════════════════════════════════
# JOBS — NUEVO
# ══════════════════════════════════════════════════════════════════

@router.post("/jobs/send-reminders")
async def trigger_reminders(
    x_cron_secret: Optional[str] = Header(None),
):
    """
    Trigger manual del cron job de recordatorios.
    Protegido con header X-Cron-Secret.
    Se puede llamar desde Railway Cron o cualquier scheduler externo.
    """
    cron_secret = os.environ.get("CRON_SECRET", "")
    if cron_secret and x_cron_secret != cron_secret:
        raise HTTPException(status_code=403, detail="Unauthorized")

    from app.jobs.reminder_cron import run_reminders
    result = await run_reminders()
    return {"status": "completed", **result}


# ── Helpers ───────────────────────────────────────────────────────

def _prof_to_dict(p: Professional) -> dict:
    return {
        "id": p.id,
        "business_id": p.business_id,
        "name": p.name,
        "phone": p.phone,
        "calendar_id": p.calendar_id,
        "active": p.active,
        "accepts_walkins": p.accepts_walkins,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }
