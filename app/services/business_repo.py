import json
import os
from typing import Optional
import redis.asyncio as redis
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.database import SessionLocal
from app.models.db_models import Business, Service, BusinessHour
from app.services.business_config import BusinessConfig, DEMO_BUSINESS

logger = get_logger(__name__)
settings = get_settings()

DAYS_MAP = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


class BusinessRepository:
    def __init__(self):
        self._redis = None
        REDIS_URL = os.environ.get("REDIS_URL") or os.environ.get("REDIS_PRIVATE_URL")
        if REDIS_URL:
            self._redis = redis.from_url(REDIS_URL, decode_responses=True)
            logger.info("BusinessRepository: Redis inicializado")
        else:
            logger.warning("BusinessRepository: REDIS_URL no encontrada para caché de negocio")

    async def get_business_by_phone(self, phone_number_id: str) -> BusinessConfig:
        cache_key = f"business:phone:{phone_number_id}"

        # 1. Intentar leer de Redis cache
        if self._redis:
            try:
                cached_data = await self._redis.get(cache_key)
                if cached_data:
                    logger.info(f"BusinessRepository: Cache hit para phone {phone_number_id}")
                    return BusinessConfig.model_validate_json(cached_data)
            except Exception as e:
                logger.error(f"BusinessRepository: Error leyendo cache: {e}")

        # 2. Cache miss -> Leer de base de datos
        db: Session = SessionLocal()
        try:
            db_business = db.query(Business).filter(Business.phone_number_id == phone_number_id).first()
            if db_business:
                # Mapear a formato Pydantic BusinessConfig
                services_list = []
                for s in db_business.services:
                    services_list.append({
                        "id": s.list_item_id or str(s.id),
                        "name": s.name,
                        "duration_min": s.duration_min,
                        "price": float(s.price) if s.price is not None else 0.0
                    })

                # Mapear días de la semana (Lunes=0, Domingo=6)
                hours_dict = {day: None for day in DAYS_MAP}
                for h in db_business.working_hours:
                    if 0 <= h.day_of_week < len(DAYS_MAP):
                        day_name = DAYS_MAP[h.day_of_week]
                        if h.is_closed:
                            hours_dict[day_name] = None
                        else:
                            hours_dict[day_name] = {
                                "start": h.start_time or "09:00",
                                "end": h.end_time or "19:00"
                            }

                business_config = BusinessConfig(
                    business_id=str(db_business.id),
                    name=db_business.name,
                    services=services_list,
                    working_hours=hours_dict,
                    phone_number_id=db_business.phone_number_id
                )

                # 3. Guardar en caché Redis (TTL de 1 hora)
                if self._redis:
                    try:
                        await self._redis.setex(cache_key, 3600, business_config.model_dump_json())
                    except Exception as e:
                        logger.error(f"BusinessRepository: Error guardando en cache: {e}")

                logger.info(f"BusinessRepository: Negocio cargado desde DB para {phone_number_id}")
                return business_config
        except Exception as e:
            logger.exception(f"BusinessRepository: Error cargando de DB para {phone_number_id}: {e}")
        finally:
            db.close()

        # Fallback al demo preconfigurado si no existe en BD
        logger.warning(f"BusinessRepository: Negocio no encontrado para {phone_number_id}. Usando fallback demo.")
        return DEMO_BUSINESS

    async def invalidate_business_cache(self, phone_number_id: str) -> bool:
        """
        Invalida la caché de Redis para un negocio específico.
        """
        if self._redis:
            try:
                cache_key = f"business:phone:{phone_number_id}"
                await self._redis.delete(cache_key)
                logger.info(f"BusinessRepository: Caché invalidada para phone {phone_number_id}")
                return True
            except Exception as e:
                logger.error(f"BusinessRepository: Error invalidando caché para {phone_number_id}: {e}")
        return False


business_repository = BusinessRepository()
