import pytest
from datetime import datetime, timezone
from app.services.state_manager import ConversationState, StateManager


@pytest.mark.anyio
async def test_state_manager_in_memory():
    manager = StateManager()
    manager.redis_client = None  # Forzar uso de memoria
    
    phone = "1234567890"
    
    # Obtener estado inicial (vacío)
    state = await manager.get_state(phone)
    assert state.phone_number == phone
    assert len(state.messages) == 0
    assert state.current_intent == ""
    
    # Modificar y guardar estado
    state.current_intent = "book_appointment"
    state.messages.append({"role": "user", "content": "Hola"})
    state.appointment_data = {"servicio": "corte"}
    success = await manager.save_state(state)
    assert success is True
    
    # Recuperar estado y validar
    retrieved = await manager.get_state(phone)
    assert retrieved.current_intent == "book_appointment"
    assert len(retrieved.messages) == 1
    assert retrieved.messages[0]["content"] == "Hola"
    assert retrieved.appointment_data["servicio"] == "corte"
    
    # Limpiar estado
    cleared = await manager.clear_state(phone)
    assert cleared is True
    
    # Verificar que el estado vuelve a estar vacío
    cleared_state = await manager.get_state(phone)
    assert len(cleared_state.messages) == 0
    assert cleared_state.current_intent == ""
