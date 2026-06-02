import sys
import os
from sqlalchemy.orm import Session

# Add the current directory to sys.path so we can import app modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.database import SessionLocal, engine
from app.models.db_models import Base, Business, Service, BusinessHour
from app.services.business_config import DEMO_BUSINESS

DAYS_MAP = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def seed():
    print("Iniciando el sembrado de datos (Seeding)...")
    db: Session = SessionLocal()
    try:
        # 1. Verificar si ya existe el negocio demo en la base de datos
        existing_business = db.query(Business).filter(Business.phone_number_id == DEMO_BUSINESS.phone_number_id).first()
        if existing_business:
            print(f"El negocio '{DEMO_BUSINESS.name}' con phone_number_id '{DEMO_BUSINESS.phone_number_id}' ya existe.")
            print("Borrando datos antiguos para resembrar...")
            db.delete(existing_business)
            db.commit()
            print("Datos antiguos eliminados.")

        # 2. Crear nuevo negocio
        new_business = Business(
            name=DEMO_BUSINESS.name,
            phone_number_id=DEMO_BUSINESS.phone_number_id
        )
        db.add(new_business)
        db.flush()  # Para obtener el ID del negocio generado autoincrementalmente

        print(f"Negocio '{new_business.name}' creado con ID: {new_business.id}")

        # 3. Agregar servicios
        for s in DEMO_BUSINESS.services:
            new_service = Service(
                id=s["id"],
                business_id=new_business.id,
                name=s["name"],
                duration_min=s["duration_min"],
                price=s["price"]
            )
            db.add(new_service)
            print(f"Servicio agregado: {s['name']} (ID: {s['id']})")

        # 4. Agregar horarios de atención
        for idx, day_name in enumerate(DAYS_MAP):
            hours = DEMO_BUSINESS.working_hours.get(day_name)
            if hours is None:
                new_hour = BusinessHour(
                    business_id=new_business.id,
                    day_of_week=idx,
                    is_closed=True,
                    start_time=None,
                    end_time=None
                )
            else:
                new_hour = BusinessHour(
                    business_id=new_business.id,
                    day_of_week=idx,
                    is_closed=False,
                    start_time=hours["start"],
                    end_time=hours["end"]
                )
            db.add(new_hour)
            time_str = "Cerrado" if hours is None else f"{hours['start']} - {hours['end']}"
            print(f"Horario de atencion agregado para {day_name.capitalize()}: {time_str}")

        db.commit()
        print("El sembrado de datos (Seeding) se completo con exito!")

    except Exception as e:
        db.rollback()
        print(f"Ocurrio un error durante el sembrado de datos: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
