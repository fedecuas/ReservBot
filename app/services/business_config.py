from pydantic import BaseModel, Field
from typing import Optional, Any

from app.core.logging import get_logger

logger = get_logger(__name__)


class BusinessConfig(BaseModel):
    """
    Representa la configuración y catálogo de un negocio.
    """
    business_id: str
    name: str
    services: list[dict[str, Any]] = Field(default_factory=list)  # [{id, name, duration_min, price}]
    working_hours: dict[str, Optional[dict[str, str]]] = Field(default_factory=dict)  # {monday: {start: "09:00", end: "19:00"}, ...}
    phone_number_id: str


# Negocio demo preconfigurado al arrancar
DEMO_BUSINESS = BusinessConfig(
    business_id="demo",
    name="Barbería El Estilo",
    services=[
        {"id": "corte", "name": "Corte de cabello", "duration_min": 30, "price": 150},
        {"id": "barba", "name": "Arreglo de barba", "duration_min": 20, "price": 100},
        {"id": "corte_barba", "name": "Corte + Barba", "duration_min": 45, "price": 220},
        {"id": "tinte", "name": "Tinte", "duration_min": 60, "price": 350}
    ],
    working_hours={
        "monday": {"start": "09:00", "end": "19:00"},
        "tuesday": {"start": "09:00", "end": "19:00"},
        "wednesday": {"start": "09:00", "end": "19:00"},
        "thursday": {"start": "09:00", "end": "19:00"},
        "friday": {"start": "09:00", "end": "19:00"},
        "saturday": {"start": "09:00", "end": "19:00"},
        "sunday": None  # Cerrado
    },
    phone_number_id="1147614285101997"  # El número del negocio del cliente
)

# Almacenamiento en memoria temporal
_businesses_db: dict[str, BusinessConfig] = {
    DEMO_BUSINESS.business_id: DEMO_BUSINESS,
    DEMO_BUSINESS.phone_number_id: DEMO_BUSINESS
}


def get_business_by_phone(phone_number_id: str) -> BusinessConfig:
    """
    Retorna la configuración del negocio asociado al phone_number_id de Meta.
    Si no existe o no se encuentra, retorna el negocio demo como fallback.
    """
    business = _businesses_db.get(phone_number_id)
    if business:
        logger.info(f"Negocio encontrado para phone_number_id '{phone_number_id}': {business.name}")
        return business
    
    logger.warning(f"No se encontró negocio para phone_number_id '{phone_number_id}'. Usando demo fallback.")
    return DEMO_BUSINESS
