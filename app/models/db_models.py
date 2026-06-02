from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base


class Business(Base):
    __tablename__ = "businesses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    phone_number_id = Column(String(100), unique=True, index=True, nullable=False)

    services = relationship("Service", back_populates="business", cascade="all, delete-orphan")
    working_hours = relationship("BusinessHour", back_populates="business", cascade="all, delete-orphan")


class Service(Base):
    __tablename__ = "services"

    id = Column(String(100), primary_key=True)  # e.g., "corte", "barba"
    business_id = Column(Integer, ForeignKey("businesses.id", ondelete="CASCADE"), primary_key=True)
    name = Column(String(255), nullable=False)
    duration_min = Column(Integer, nullable=False)
    price = Column(Float, nullable=False)

    business = relationship("Business", back_populates="services")


class BusinessHour(Base):
    __tablename__ = "business_hours"

    id = Column(Integer, primary_key=True, autoincrement=True)
    business_id = Column(Integer, ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    day_of_week = Column(Integer, nullable=False)  # 0=Lunes, 6=Domingo
    start_time = Column(String(5), nullable=True)  # "09:00"
    end_time = Column(String(5), nullable=True)    # "19:00"
    is_closed = Column(Boolean, default=False, nullable=False)

    business = relationship("Business", back_populates="working_hours")
