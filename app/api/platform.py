"""
EQKO Platform API — endpoints de agencia para gestionar negocios cliente.
Prefijo: /platform
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.core.database import get_db
from app.core.logging import get_logger
from app.services.platform_service import (
    get_all_businesses,
    get_business_detail,
    create_business,
    update_business,
    delete_business,
    get_business_health,
    upsert_services,
    upsert_hours,
    get_platform_metrics,
)
from app.schemas.platform import (
    BusinessCreate,
    BusinessUpdate,
    ServicesUpdate,
    HoursUpdate,
)

router = APIRouter(prefix="/platform", tags=["platform"])
logger = get_logger(__name__)


# ── Businesses ────────────────────────────────────────────────────

@router.get("/businesses")
async def list_businesses(
    status: Optional[str] = Query(None, description="Filtrar por subscription_status: active, inactive, trial"),
    db: Session = Depends(get_db),
):
    """Lista todos los negocios cliente con resumen de estado."""
    return await get_all_businesses(db, status=status)


@router.post("/businesses", status_code=201)
async def create_new_business(
    payload: BusinessCreate,
    db: Session = Depends(get_db),
):
    """Crea un nuevo negocio cliente."""
    try:
        return await create_business(db, payload)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/businesses/{business_id}")
async def get_business(
    business_id: int,
    db: Session = Depends(get_db),
):
    """Detalle completo de un negocio: info, servicios, horarios."""
    business = await get_business_detail(db, business_id)
    if not business:
        raise HTTPException(status_code=404, detail="Negocio no encontrado")
    return business


@router.patch("/businesses/{business_id}")
async def update_business_info(
    business_id: int,
    payload: BusinessUpdate,
    db: Session = Depends(get_db),
):
    """Actualiza datos del negocio (campos parciales)."""
    business = await update_business(db, business_id, payload)
    if not business:
        raise HTTPException(status_code=404, detail="Negocio no encontrado")
    return business


@router.delete("/businesses/{business_id}", status_code=204)
async def remove_business(
    business_id: int,
    db: Session = Depends(get_db),
):
    """Elimina un negocio y todos sus datos asociados."""
    deleted = await delete_business(db, business_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Negocio no encontrado")


# ── Health ────────────────────────────────────────────────────────

@router.get("/businesses/{business_id}/health")
async def business_health(
    business_id: int,
    db: Session = Depends(get_db),
):
    """
    Estado de salud del bot:
    - webhook_configured: tiene phone_number_id y token
    - calendar_configured: tiene google_calendar_id
    - bot_active: flag activo en DB
    - services_count: número de servicios activos
    - hours_configured: tiene horarios definidos
    """
    health = await get_business_health(db, business_id)
    if not health:
        raise HTTPException(status_code=404, detail="Negocio no encontrado")
    return health


# ── Services ──────────────────────────────────────────────────────

@router.put("/businesses/{business_id}/services")
async def set_services(
    business_id: int,
    payload: ServicesUpdate,
    db: Session = Depends(get_db),
):
    """
    Reemplaza el catálogo completo de servicios de un negocio.
    Enviar la lista completa — los servicios que no estén se marcan como inactivos.
    """
    result = await upsert_services(db, business_id, payload.services)
    if result is None:
        raise HTTPException(status_code=404, detail="Negocio no encontrado")
    return result


# ── Hours ─────────────────────────────────────────────────────────

@router.put("/businesses/{business_id}/hours")
async def set_hours(
    business_id: int,
    payload: HoursUpdate,
    db: Session = Depends(get_db),
):
    """
    Reemplaza los horarios de atención de un negocio.
    Enviar los 7 días — días no incluidos se marcan como cerrados.
    """
    result = await upsert_hours(db, business_id, payload.hours)
    if result is None:
        raise HTTPException(status_code=404, detail="Negocio no encontrado")
    return result


# ── Metrics ───────────────────────────────────────────────────────

@router.get("/metrics")
async def platform_metrics(
    db: Session = Depends(get_db),
):
    """
    Métricas globales de la plataforma EQKO:
    - total_businesses: total de negocios
    - active_businesses: negocios con bot activo
    - mrr: ingreso mensual recurrente total
    - businesses_by_plan: desglose por plan
    - businesses_by_status: desglose por status
    """
    return await get_platform_metrics(db)
