import os
from dotenv import load_dotenv
load_dotenv()

from app.core.database import SessionLocal
from app.models.db_models import Business, Service, BusinessHour

PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID", "1147614285101997")

def seed():
    db = SessionLocal()
    try:
        existing = db.query(Business).filter(Business.phone_number_id == PHONE_NUMBER_ID).first()
        if existing:
            print(f"Ya existe negocio con phone_number_id={PHONE_NUMBER_ID}. Nada que hacer.")
            return

        business = Business(
            phone_number_id=PHONE_NUMBER_ID,
            phone_number="525659155222",
            name="Barberia El Estilo",
            category="barbershop",
            timezone="America/Mexico_City",
            bot_name="Valentina",
            welcome_message="¡Hola! 👋 Soy *Valentina*, tu asistente virtual. ¿Con quién tengo el gusto? 😊",
        )
        db.add(business)
        db.flush()

        services = [
            Service(business_id=business.id, name="Corte de cabello", duration_min=30, price=150, list_item_id="corte"),
            Service(business_id=business.id, name="Arreglo de barba",  duration_min=20, price=100, list_item_id="barba"),
            Service(business_id=business.id, name="Corte + Barba",     duration_min=45, price=220, list_item_id="corte_barba"),
            Service(business_id=business.id, name="Tinte",             duration_min=60, price=350, list_item_id="tinte"),
        ]
        for s in services:
            db.add(s)

        hours = [
            BusinessHour(business_id=business.id, day_of_week=0, start_time="09:00", end_time="19:00"),
            BusinessHour(business_id=business.id, day_of_week=1, start_time="09:00", end_time="19:00"),
            BusinessHour(business_id=business.id, day_of_week=2, start_time="09:00", end_time="19:00"),
            BusinessHour(business_id=business.id, day_of_week=3, start_time="09:00", end_time="19:00"),
            BusinessHour(business_id=business.id, day_of_week=4, start_time="09:00", end_time="19:00"),
            BusinessHour(business_id=business.id, day_of_week=5, start_time="09:00", end_time="17:00"),
            BusinessHour(business_id=business.id, day_of_week=6, is_closed=True),
        ]
        for h in hours:
            db.add(h)

        db.commit()
        print(f"Negocio creado: {business.name} (id={business.id})")
    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    seed()
