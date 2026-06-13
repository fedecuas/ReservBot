"""
Notification Service — envío de notificaciones al dueño del negocio
y recordatorios automáticos 24h a clientes.
"""
from app.core.logging import get_logger
from app.services.whatsapp_sender import send_text_message

logger = get_logger(__name__)


async def notify_owner_new_appointment(
    owner_phone: str,
    client_name: str,
    service_name: str,
    appointment_date: str,
    appointment_time: str,
    professional_name: str = None,
) -> None:
    """
    Notifica al dueño del negocio cuando se agenda una nueva cita.
    Se llama automáticamente después de confirmar la cita con el cliente.
    """
    if not owner_phone:
        logger.info("No hay owner_phone configurado — notificación omitida")
        return

    prof_line = f"\n👤 *Profesional:* {professional_name}" if professional_name else ""

    # Formatear fecha legible
    try:
        from datetime import datetime
        days_es   = ["lunes","martes","miércoles","jueves","viernes","sábado","domingo"]
        months_es = ["enero","febrero","marzo","abril","mayo","junio","julio","agosto",
                     "septiembre","octubre","noviembre","diciembre"]
        d = datetime.strptime(appointment_date, "%Y-%m-%d")
        fecha_label = f"{days_es[d.weekday()]} {d.day} de {months_es[d.month-1]}"
    except Exception:
        fecha_label = appointment_date

    message = (
        f"🔔 *Nueva cita confirmada*\n\n"
        f"👤 *Cliente:* {client_name}\n"
        f"✂️ *Servicio:* {service_name}\n"
        f"📅 *Fecha:* {fecha_label}\n"
        f"⏰ *Hora:* {appointment_time}"
        f"{prof_line}\n\n"
        f"La cita ya está en tu Google Calendar ✅"
    )

    try:
        await send_text_message(to=owner_phone, message=message)
        logger.info(f"Notificación enviada al dueño: {owner_phone}")
    except Exception as e:
        logger.error(f"Error enviando notificación al dueño {owner_phone}: {e}")


async def send_reminder_24h(
    client_phone: str,
    client_name: str,
    service_name: str,
    appointment_date: str,
    appointment_time: str,
    business_name: str,
    bot_name: str = "Valentina",
) -> bool:
    """
    Envía recordatorio de cita 24 horas antes al cliente.
    Retorna True si se envió correctamente, False si falló.
    Llamado por el cron job diario.
    """
    try:
        from datetime import datetime
        days_es   = ["lunes","martes","miércoles","jueves","viernes","sábado","domingo"]
        months_es = ["enero","febrero","marzo","abril","mayo","junio","julio","agosto",
                     "septiembre","octubre","noviembre","diciembre"]
        d = datetime.strptime(appointment_date, "%Y-%m-%d")
        fecha_label = f"{days_es[d.weekday()]} {d.day} de {months_es[d.month-1]}"
    except Exception:
        fecha_label = appointment_date

    message = (
        f"¡Hola {client_name}! 👋 Soy {bot_name} de *{business_name}*.\n\n"
        f"Te recuerdo que mañana tienes una cita:\n\n"
        f"✂️ *Servicio:* {service_name}\n"
        f"📅 *Fecha:* {fecha_label}\n"
        f"⏰ *Hora:* {appointment_time}\n\n"
        f"Si necesitas cancelar o cambiar tu cita, escríbeme aquí mismo 😊"
    )

    try:
        await send_text_message(to=client_phone, message=message)
        logger.info(f"Recordatorio enviado a {client_phone} para cita del {appointment_date}")
        return True
    except Exception as e:
        logger.error(f"Error enviando recordatorio a {client_phone}: {e}")
        return False
