"""
EQKO Platform Service — lógica de negocio para gestión de clientes de agencia.
"""
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.logging import get_logger
from app.models.db_models import Business, Service, BusinessHour
from app.schemas.platform import BusinessCreate, BusinessUpdate

logger = get_logger(__name__)


# ── Businesses ────────────────────────────────────────────────────

async def get_all_businesses(db: Session, status: Optional[str] = None) -> dict:
    query = db.query(Business)
    if status:
        query = query.filter(Business.subscription_status == status)

    businesses = query.order_by(Business.created_at.desc()).all()

    return {
        "total": len(businesses),
        "businesses": [_business_summary(b) for b in businesses],
    }


async def get_business_detail(db: Session, business_id: int) -> Optional[dict]:
    business = db.query(Business).filter(Business.id == business_id).first()
    if not business:
        return None

    services = [
        {
            "id": s.id,
            "name": s.name,
            "description": s.description,
            "duration_min": s.duration_min,
            "price": float(s.price) if s.price else None,
            "active": s.active,
            "list_item_id": s.list_item_id,
        }
        for s in business.services
    ]

    hours = [
        {
            "day_of_week": h.day_of_week,
            "day_name": _day_name(h.day_of_week),
            "is_closed": h.is_closed,
            "start_time": h.start_time,
            "end_time": h.end_time,
        }
        for h in sorted(business.working_hours, key=lambda x: x.day_of_week)
    ]

    return {
        **_business_summary(business),
        "bot_name": business.bot_name,
        "welcome_message": business.welcome_message,
        "language": business.language,
        "timezone": business.timezone,
        "waba_id": business.waba_id,
        "phone_number": business.phone_number,
        "services": services,
        "hours": hours,
    }


async def create_business(db: Session, payload: BusinessCreate) -> dict:
    # Verificar que no exista ya ese phone_number_id
    existing = db.query(Business).filter(
        Business.phone_number_id == payload.phone_number_id
    ).first()
    if existing:
        raise ValueError(f"Ya existe un negocio con phone_number_id={payload.phone_number_id}")

    business = Business(
        phone_number_id=payload.phone_number_id,
        name=payload.name,
        category=payload.category,
        timezone=payload.timezone or "America/Mexico_City",
        language=payload.language or "es",
        bot_name=payload.bot_name or "Valentina",
        welcome_message=payload.welcome_message,
        subscription_plan=payload.subscription_plan or "starter",
        subscription_status="active",
        monthly_price=payload.monthly_price,
        waba_id=payload.waba_id,
        phone_number=payload.phone_number,
    )
    db.add(business)
    db.commit()
    db.refresh(business)

    logger.info(f"Negocio creado: {business.name} (id={business.id})")
    return _business_summary(business)


async def update_business(db: Session, business_id: int, payload: BusinessUpdate) -> Optional[dict]:
    business = db.query(Business).filter(Business.id == business_id).first()
    if not business:
        return None

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(business, field, value)

    business.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(business)

    logger.info(f"Negocio actualizado: {business.name} (id={business.id})")
    return _business_summary(business)


async def delete_business(db: Session, business_id: int) -> bool:
    business = db.query(Business).filter(Business.id == business_id).first()
    if not business:
        return False

    db.delete(business)
    db.commit()
    logger.info(f"Negocio eliminado: id={business_id}")
    return True


# ── Health ────────────────────────────────────────────────────────

async def get_business_health(db: Session, business_id: int) -> Optional[dict]:
    business = db.query(Business).filter(Business.id == business_id).first()
    if not business:
        return None

    active_services = [s for s in business.services if s.active]
    has_hours = len(business.working_hours) > 0
    open_days = [h for h in business.working_hours if not h.is_closed]

    webhook_ok = bool(business.phone_number_id)
    calendar_ok = True  # Service Account global — siempre disponible

    health_score = sum([
        webhook_ok,
        calendar_ok,
        business.bot_active,
        len(active_services) > 0,
        has_hours,
        len(open_days) > 0,
    ])

    status = "healthy" if health_score >= 5 else "warning" if health_score >= 3 else "critical"

    return {
        "business_id": business_id,
        "business_name": business.name,
        "status": status,
        "health_score": health_score,
        "checks": {
            "webhook_configured": webhook_ok,
            "calendar_configured": calendar_ok,
            "bot_active": business.bot_active,
            "services_count": len(active_services),
            "hours_configured": has_hours,
            "open_days_count": len(open_days),
        },
    }


# ── Services ──────────────────────────────────────────────────────

async def upsert_services(db: Session, business_id: int, services_data: list) -> Optional[dict]:
    business = db.query(Business).filter(Business.id == business_id).first()
    if not business:
        return None

    # Marcar todos los servicios actuales como inactivos
    for svc in business.services:
        svc.active = False

    # Insertar o actualizar los servicios enviados
    for svc_data in services_data:
        existing = next(
            (s for s in business.services if s.name == svc_data.name), None
        )
        if existing:
            existing.description = svc_data.description
            existing.duration_min = svc_data.duration_min
            existing.price = svc_data.price
            existing.active = True
            existing.list_item_id = svc_data.list_item_id
        else:
            new_svc = Service(
                business_id=business_id,
                name=svc_data.name,
                description=svc_data.description,
                duration_min=svc_data.duration_min or 30,
                price=svc_data.price,
                active=True,
                list_item_id=svc_data.list_item_id,
            )
            db.add(new_svc)

    db.commit()
    db.refresh(business)
    logger.info(f"Servicios actualizados para negocio id={business_id}")

    return {
        "business_id": business_id,
        "services": [
            {
                "id": s.id,
                "name": s.name,
                "duration_min": s.duration_min,
                "price": float(s.price) if s.price else None,
                "active": s.active,
            }
            for s in business.services
        ],
    }


# ── Hours ─────────────────────────────────────────────────────────

async def upsert_hours(db: Session, business_id: int, hours_data: list) -> Optional[dict]:
    business = db.query(Business).filter(Business.id == business_id).first()
    if not business:
        return None

    # Eliminar horarios actuales y reemplazar
    db.query(BusinessHour).filter(BusinessHour.business_id == business_id).delete()

    for hour_data in hours_data:
        new_hour = BusinessHour(
            business_id=business_id,
            day_of_week=hour_data.day_of_week,
            is_closed=hour_data.is_closed or False,
            start_time=hour_data.start_time or "09:00",
            end_time=hour_data.end_time or "19:00",
        )
        db.add(new_hour)

    db.commit()
    db.refresh(business)
    logger.info(f"Horarios actualizados para negocio id={business_id}")

    return {
        "business_id": business_id,
        "hours": [
            {
                "day_of_week": h.day_of_week,
                "day_name": _day_name(h.day_of_week),
                "is_closed": h.is_closed,
                "start_time": h.start_time,
                "end_time": h.end_time,
            }
            for h in sorted(business.working_hours, key=lambda x: x.day_of_week)
        ],
    }


# ── Metrics ───────────────────────────────────────────────────────

async def get_platform_metrics(db: Session) -> dict:
    total = db.query(Business).count()
    active = db.query(Business).filter(Business.bot_active == True).count()

    # MRR
    mrr_result = db.query(
        func.sum(Business.monthly_price)
    ).filter(
        Business.subscription_status == "active",
        Business.monthly_price.isnot(None)
    ).scalar()
    mrr = float(mrr_result) if mrr_result else 0.0

    # Por plan
    by_plan_rows = db.query(
        Business.subscription_plan,
        func.count(Business.id)
    ).group_by(Business.subscription_plan).all()

    # Por status
    by_status_rows = db.query(
        Business.subscription_status,
        func.count(Business.id)
    ).group_by(Business.subscription_status).all()

    return {
        "total_businesses": total,
        "active_businesses": active,
        "inactive_businesses": total - active,
        "mrr": mrr,
        "mrr_formatted": f"${mrr:,.2f} MXN",
        "businesses_by_plan": {plan: count for plan, count in by_plan_rows},
        "businesses_by_status": {status: count for status, count in by_status_rows},
    }


# ── Helpers ───────────────────────────────────────────────────────

def _business_summary(business: Business) -> dict:
    return {
        "id": business.id,
        "name": business.name,
        "category": business.category,
        "phone_number_id": business.phone_number_id,
        "phone_number": business.phone_number,
        "bot_active": business.bot_active,
        "subscription_plan": business.subscription_plan,
        "subscription_status": business.subscription_status,
        "monthly_price": float(business.monthly_price) if business.monthly_price else None,
        "created_at": business.created_at.isoformat() if business.created_at else None,
        "updated_at": business.updated_at.isoformat() if business.updated_at else None,
    }


def _day_name(day_of_week: int) -> str:
    days = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    return days[day_of_week] if 0 <= day_of_week <= 6 else "Desconocido"
