import json
import os
from datetime import datetime, timezone
from typing import Any
from pydantic import BaseModel, Field
import redis.asyncio as redis

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


class ConversationState(BaseModel):
    """
    Representa el estado actual de la conversación de un usuario.
    """
    phone_number: str
    messages: list[dict[str, str]] = Field(default_factory=list)  # Historial de [{role, content}]
    current_intent: str = ""
    appointment_data: dict[str, Any] = Field(default_factory=dict)  # fecha, hora, servicio, nombre
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class StateManager:
    """
    Gestiona el estado de las conversaciones guardándolo en Redis o en memoria.
    """
    def __init__(self):
        self._in_memory_db = {}  # Fallback: {phone: (ConversationState, datetime_saved)}
        
        REDIS_URL = os.environ.get("REDIS_URL") or os.environ.get("REDIS_PRIVATE_URL")

        if REDIS_URL:
            self.redis = redis.from_url(REDIS_URL, decode_responses=True)
            logger.info(f"Redis conectado: {REDIS_URL[:30]}...")
        else:
            self.redis = None
            logger.warning("REDIS_URL no encontrada — usando memoria")

    async def get_state(self, phone: str) -> ConversationState:
        """
        Obtiene el estado de la conversación para un número de teléfono.
        Si no existe, retorna uno nuevo.
        """
        # Intentar obtener de Redis
        if self.redis:
            try:
                data = await self.redis.get(f"state:{phone}")
                if data:
                    state_dict = json.loads(data)
                    return ConversationState.model_validate(state_dict)
            except Exception as e:
                logger.warning(f"StateManager: Error al obtener estado de Redis para {phone}: {e}. Consultando memoria.")

        # Fallback en memoria
        if phone in self._in_memory_db:
            state, saved_time = self._in_memory_db[phone]
            # Verificar expiración de 24 horas (TTL)
            if (datetime.now(timezone.utc) - saved_time).total_seconds() > 86400:
                logger.info(f"StateManager: Estado en memoria para {phone} expirado por TTL.")
                del self._in_memory_db[phone]
            else:
                return state

        # Retornar un estado vacío si no se encuentra ninguno
        logger.info(f"StateManager: Creando nuevo estado de conversación para {phone}")
        return ConversationState(
            phone_number=phone,
            messages=[],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )

    async def save_state(self, state: ConversationState) -> bool:
        """
        Guarda el estado de la conversación.
        Establece un TTL de 24 horas.
        """
        state.updated_at = datetime.now(timezone.utc)
        phone = state.phone_number

        # Intentar guardar en Redis
        if self.redis:
            try:
                # model_dump_json maneja la serialización de datetime automáticamente
                json_data = state.model_dump_json()
                await self.redis.setex(f"state:{phone}", 86400, json_data)
                return True
            except Exception as e:
                logger.error(f"StateManager: Error al guardar estado en Redis para {phone}: {e}. Guardando en memoria.")

        # Guardar en memoria
        self._in_memory_db[phone] = (state, datetime.now(timezone.utc))
        return True

    async def clear_state(self, phone: str) -> bool:
        """
        Elimina el estado de la conversación para un número de teléfono.
        """
        deleted_any = False

        # Intentar borrar de Redis
        if self.redis:
            try:
                result = await self.redis.delete(f"state:{phone}")
                if result > 0:
                    deleted_any = True
            except Exception as e:
                logger.error(f"StateManager: Error al eliminar estado de Redis para {phone}: {e}")

        # Borrar de memoria
        if phone in self._in_memory_db:
            del self._in_memory_db[phone]
            deleted_any = True

        return deleted_any


# Instancia global
state_manager = StateManager()
