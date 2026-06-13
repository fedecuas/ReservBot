"""
Schemas Pydantic para la API de plataforma EQKO.
"""
from pydantic import BaseModel
from typing import Optional, List
from decimal import Decimal


# ── Business ──────────────────────────────────────────────────────

class BusinessCreate(BaseModel):
    name: str
    phone_number_id: str
    category: Optional[str] = None
    timezone: Optional[str] = "America/Mexico_City"
    language: Optional[str] = "es"
    bot_name: Optional[str] = "Valentina"
    welcome_message: Optional[str] = None
    subscription_plan: Optional[str] = "starter"
    monthly_price: Optional[Decimal] = None
    waba_id: Optional[str] = None
    phone_number: Optional[str] = None


class BusinessUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    timezone: Optional[str] = None
    language: Optional[str] = None
    bot_name: Optional[str] = None
    welcome_message: Optional[str] = None
    bot_active: Optional[bool] = None
    subscription_plan: Optional[str] = None
    subscription_status: Optional[str] = None
    monthly_price: Optional[Decimal] = None
    phone_number: Optional[str] = None
    waba_id: Optional[str] = None


# ── Services ──────────────────────────────────────────────────────

class ServiceItem(BaseModel):
    name: str
    description: Optional[str] = None
    duration_min: Optional[int] = 30
    price: Optional[Decimal] = None
    list_item_id: Optional[str] = None


class ServicesUpdate(BaseModel):
    services: List[ServiceItem]


# ── Hours ─────────────────────────────────────────────────────────

class HourItem(BaseModel):
    day_of_week: int          # 0=Lunes … 6=Domingo
    is_closed: Optional[bool] = False
    start_time: Optional[str] = "09:00"
    end_time: Optional[str] = "19:00"


class HoursUpdate(BaseModel):
    hours: List[HourItem]
