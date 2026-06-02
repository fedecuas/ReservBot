from datetime import datetime
from sqlalchemy import Column, String, Integer, Boolean, Text, DateTime, ForeignKey, Numeric
from sqlalchemy.orm import relationship
from app.core.database import Base

class Business(Base):
    __tablename__ = "businesses"
    id = Column(Integer, primary_key=True, index=True)
    phone_number_id = Column(String(64), unique=True, nullable=False, index=True)
    waba_id = Column(String(64), nullable=True)
    phone_number = Column(String(20), nullable=True)
    name = Column(String(128), nullable=False)
    category = Column(String(64), nullable=True)
    timezone = Column(String(64), default="America/Mexico_City")
    language = Column(String(8), default="es")
    bot_name = Column(String(64), default="Valentina")
    bot_active = Column(Boolean, default=True)
    welcome_message = Column(Text, nullable=True)
    subscription_plan = Column(String(32), default="starter")
    subscription_status = Column(String(32), default="active")
    monthly_price = Column(Numeric(10, 2), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    services = relationship("Service", back_populates="business", cascade="all, delete-orphan")
    working_hours = relationship("BusinessHour", back_populates="business", cascade="all, delete-orphan")

class Service(Base):
    __tablename__ = "services"
    id = Column(Integer, primary_key=True, index=True)
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=False, index=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    duration_min = Column(Integer, default=30)
    price = Column(Numeric(10, 2), nullable=True)
    active = Column(Boolean, default=True)
    list_item_id = Column(String(24), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    business = relationship("Business", back_populates="services")

class BusinessHour(Base):
    __tablename__ = "business_hours"
    id = Column(Integer, primary_key=True, index=True)
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=False, index=True)
    day_of_week = Column(Integer, nullable=False)
    is_closed = Column(Boolean, default=False)
    start_time = Column(String(5), default="09:00")
    end_time = Column(String(5), default="19:00")
    business = relationship("Business", back_populates="working_hours")
