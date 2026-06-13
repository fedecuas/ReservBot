from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, Boolean, Text, DateTime,
    ForeignKey, Numeric
)
from sqlalchemy.orm import relationship
from app.core.database import Base


class Business(Base):
    __tablename__ = "businesses"

    id                  = Column(Integer, primary_key=True, index=True)
    phone_number_id     = Column(String(64), unique=True, nullable=False, index=True)
    waba_id             = Column(String(64), nullable=True)
    phone_number        = Column(String(20), nullable=True)
    name                = Column(String(128), nullable=False)
    category            = Column(String(64), nullable=True)
    timezone            = Column(String(64), default="America/Mexico_City")
    language            = Column(String(8), default="es")
    bot_name            = Column(String(64), default="Valentina")
    bot_active          = Column(Boolean, default=True)
    welcome_message     = Column(Text, nullable=True)
    owner_phone         = Column(String(20), nullable=True)   # ← NUEVO: para notificar al dueño
    subscription_plan   = Column(String(32), default="starter")
    subscription_status = Column(String(32), default="active")
    monthly_price       = Column(Numeric(10, 2), nullable=True)
    created_at          = Column(DateTime, default=datetime.utcnow)
    updated_at          = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    services      = relationship("Service", back_populates="business", cascade="all, delete-orphan")
    working_hours = relationship("BusinessHour", back_populates="business", cascade="all, delete-orphan")
    professionals = relationship("Professional", back_populates="business", cascade="all, delete-orphan")  # ← NUEVO
    appointments  = relationship("Appointment", back_populates="business", cascade="all, delete-orphan")   # ← NUEVO
    conversations = relationship("Conversation", back_populates="business", cascade="all, delete-orphan")  # ← NUEVO


class Service(Base):
    __tablename__ = "services"

    id           = Column(Integer, primary_key=True, index=True)
    business_id  = Column(Integer, ForeignKey("businesses.id"), nullable=False, index=True)
    name         = Column(String(128), nullable=False)
    description  = Column(Text, nullable=True)
    duration_min = Column(Integer, default=30)
    price        = Column(Numeric(10, 2), nullable=True)
    active       = Column(Boolean, default=True)
    list_item_id = Column(String(24), nullable=True)
    created_at   = Column(DateTime, default=datetime.utcnow)

    business = relationship("Business", back_populates="services")


class BusinessHour(Base):
    __tablename__ = "business_hours"

    id          = Column(Integer, primary_key=True, index=True)
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=False, index=True)
    day_of_week = Column(Integer, nullable=False)
    is_closed   = Column(Boolean, default=False)
    start_time  = Column(String(5), default="09:00")
    end_time    = Column(String(5), default="19:00")

    business = relationship("Business", back_populates="working_hours")


# ── NUEVO: Profesionales ──────────────────────────────────────────────────────

class Professional(Base):
    """
    Representa a un profesional (barbero, estilista, etc.) dentro de un negocio.
    Cada profesional puede tener su propio Google Calendar y sus propios servicios.
    """
    __tablename__ = "professionals"

    id              = Column(Integer, primary_key=True, index=True)
    business_id     = Column(Integer, ForeignKey("businesses.id"), nullable=False, index=True)
    name            = Column(String(128), nullable=False)
    phone           = Column(String(20), nullable=True)
    calendar_id     = Column(String(255), nullable=True)   # Google Calendar propio
    active          = Column(Boolean, default=True)
    accepts_walkins = Column(Boolean, default=False)
    created_at      = Column(DateTime, default=datetime.utcnow)

    business     = relationship("Business", back_populates="professionals")
    appointments = relationship("Appointment", back_populates="professional")


# ── NUEVO: Citas ──────────────────────────────────────────────────────────────

class Appointment(Base):
    """
    Registro permanente de cada cita confirmada.
    Se crea cuando el cliente confirma en WhatsApp y se crea el evento en Calendar.
    """
    __tablename__ = "appointments"

    id              = Column(Integer, primary_key=True, index=True)
    business_id     = Column(Integer, ForeignKey("businesses.id"), nullable=False, index=True)
    professional_id = Column(Integer, ForeignKey("professionals.id"), nullable=True)
    client_name     = Column(String(128), nullable=False)
    client_phone    = Column(String(20), nullable=False, index=True)
    service_name    = Column(String(128), nullable=False)
    appointment_date = Column(String(10), nullable=False)   # YYYY-MM-DD
    appointment_time = Column(String(5), nullable=False)    # HH:MM
    duration_min    = Column(Integer, default=30)
    calendar_event_id = Column(String(255), nullable=True)  # ID del evento en Google Calendar
    status          = Column(
        String(20),
        default="confirmed"
    )
    # status values: confirmed | cancelled | rescheduled | completed | no_show
    reminder_sent   = Column(Boolean, default=False)        # ← para recordatorios 24h
    notes           = Column(Text, nullable=True)
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    business     = relationship("Business", back_populates="appointments")
    professional = relationship("Professional", back_populates="appointments")


# ── NUEVO: Conversaciones ─────────────────────────────────────────────────────

class Conversation(Base):
    """
    Log de conversaciones por cliente y negocio.
    Permite ver el historial de mensajes intercambiados.
    """
    __tablename__ = "conversations"

    id           = Column(Integer, primary_key=True, index=True)
    business_id  = Column(Integer, ForeignKey("businesses.id"), nullable=False, index=True)
    client_phone = Column(String(20), nullable=False, index=True)
    client_name  = Column(String(128), nullable=True)
    messages     = Column(Text, nullable=True)   # JSON array de mensajes
    intent_log   = Column(Text, nullable=True)   # JSON array de intents detectados
    started_at   = Column(DateTime, default=datetime.utcnow)
    updated_at   = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    ended_at     = Column(DateTime, nullable=True)

    business = relationship("Business", back_populates="conversations")
