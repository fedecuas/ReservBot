import asyncio
from app.core.database import SessionLocal
from app.core.logging import get_logger
from app.services.appointment_service import (
    get_appointments_pending_reminder,
    mark_reminder_sent,
)
from app.services.notification_service import send_reminder_24h

logger = get_logger(__name__)


async def run_reminders() -> dict:
    """
    Proceso principal del cron job:
    1. Busca todas las citas de mañana con reminder_sent=False
    2. Envía WhatsApp de recordatorio a cada cliente
    3. Marca reminder_sent=True para no repetir
    4. Retorna resumen del proceso
    """
    db = SessionLocal()
    sent = 0
    failed = 0
    skipped = 0

    try:
        appointments = await get_appointments_pending_reminder(db)
        logger.info(f"Cron recordatorios: {len(appointments)} citas pendientes")

        for appt in appointments:
            business = appt.business
            if not business or not business.bot_active:
                skipped += 1
                continue

            success = await send_reminder_24h(
                client_phone=appt.client_phone,
                client_name=appt.client_name,
                service_name=appt.service_name,
                appointment_date=appt.appointment_date,
                appointment_time=appt.appointment_time,
                business_name=business.name,
                bot_name=business.bot_name or "Valentina",
            )

            if success:
                await mark_reminder_sent(db, appt.id)
                sent += 1
            else:
                failed += 1

    except Exception as e:
        logger.exception(f"Error en cron de recordatorios: {e}")
    finally:
        db.close()

    result = {"sent": sent, "failed": failed, "skipped": skipped}
    logger.info(f"Cron completado: {result}")
    return result


if __name__ == "__main__":
    asyncio.run(run_reminders())
