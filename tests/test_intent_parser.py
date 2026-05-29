import pytest
from unittest.mock import patch, MagicMock
from app.services.intent_parser import parse_intent


@pytest.mark.anyio
async def test_parse_intent_success():
    mock_message = MagicMock()
    mock_message.content = [
        MagicMock(text='{"intent": "agendar", "servicio": "corte", "fecha": "2026-06-01", "hora": "15:00", "nombre": "Fede", "respuesta": "¡Claro! Agenda confirmada."}')
    ]
    
    with patch("app.services.intent_parser.settings") as mock_settings, \
         patch("app.services.intent_parser.AsyncAnthropic") as mock_anthropic_class:
        
        mock_settings.anthropic_api_key = "test_key"
        
        mock_client = MagicMock()
        
        # Simular messages.create de forma asíncrona
        async def mock_create(*args, **kwargs):
            return mock_message
        
        mock_client.messages.create = mock_create
        mock_anthropic_class.return_value = mock_client
        
        res = await parse_intent("12345", "Quiero un corte mañana a las 3", [])
        
        assert res["intent"] == "agendar"
        assert res["servicio"] == "corte"
        assert res["fecha"] == "2026-06-01"
        assert res["hora"] == "15:00"
        assert res["nombre"] == "Fede"
        assert res["respuesta"] == "¡Claro! Agenda confirmada."


@pytest.mark.anyio
async def test_parse_intent_invalid_json_fallback():
    mock_message = MagicMock()
    mock_message.content = [
        MagicMock(text='Este no es un JSON válido')
    ]
    
    with patch("app.services.intent_parser.settings") as mock_settings, \
         patch("app.services.intent_parser.AsyncAnthropic") as mock_anthropic_class:
        
        mock_settings.anthropic_api_key = "test_key"
        
        mock_client = MagicMock()
        
        async def mock_create(*args, **kwargs):
            return mock_message
        
        mock_client.messages.create = mock_create
        mock_anthropic_class.return_value = mock_client
        
        res = await parse_intent("12345", "Hola", [])
        
        assert res["intent"] == "otro"
        assert res["servicio"] is None
        assert "problemas" in res["respuesta"]
