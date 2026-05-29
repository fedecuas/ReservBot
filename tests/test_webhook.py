import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, AsyncMock
from app.main import app

client = TestClient(app)


def test_health():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_webhook_verify_valid():
    with patch("app.api.webhook.settings") as mock_settings:
        mock_settings.verify_token = "test_token"
        mock_settings.is_production = False
        res = client.get("/webhook", params={
            "hub.mode": "subscribe",
            "hub.verify_token": "test_token",
            "hub.challenge": "12345"
        })
    assert res.status_code == 200
    assert res.json() == 12345


def test_webhook_verify_invalid_token():
    with patch("app.api.webhook.settings") as mock_settings:
        mock_settings.verify_token = "test_token"
        mock_settings.is_production = False
        res = client.get("/webhook", params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong_token",
            "hub.challenge": "12345"
        })
    assert res.status_code == 403


def test_webhook_post_returns_ok():
    with patch("app.api.webhook.settings") as mock_settings, \
         patch("app.api.webhook.send_text_message") as mock_send, \
         patch("app.api.webhook.parse_intent") as mock_parse:
        
        mock_settings.is_production = False
        mock_parse.return_value = {
            "intent": "saludo",
            "servicio": None,
            "fecha": None,
            "hora": None,
            "nombre": None,
            "respuesta": "Hola! Soy ReservBot 🤖 ¿En qué te puedo ayudar?"
        }
        
        payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "value": {
                        "messages": [{
                            "id": "msg_001",
                            "from": "5215512345678",
                            "timestamp": "1716800000",
                            "type": "text",
                            "text": {"body": "Hola quiero agendar un corte"}
                        }]
                    }
                }]
            }]
        }
        res = client.post("/webhook", json=payload)
        
        mock_parse.assert_called_once_with(
            "5215512345678",
            "Hola quiero agendar un corte",
            [],
            appointment_data={}
        )
        
        mock_send.assert_called_once_with(
            to="5215512345678",
            message="Hola! Soy ReservBot 🤖 ¿En qué te puedo ayudar?"
        )
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_webhook_interactive_reply_returns_ok():
    with patch("app.api.webhook.settings") as mock_settings, \
         patch("app.api.webhook.send_text_message") as mock_send, \
         patch("app.api.webhook.state_manager") as mock_state_mgr:
         
        mock_settings.is_production = False
        
        # Mock State
        mock_state = MagicMock()
        mock_state.appointment_data = {}
        mock_state_mgr.get_state = AsyncMock(return_value=mock_state)
        mock_state_mgr.save_state = AsyncMock()
        
        payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "value": {
                        "messages": [{
                            "id": "msg_002",
                            "from": "5215512345678",
                            "timestamp": "1716800000",
                            "type": "interactive",
                            "interactive": {
                                "type": "list_reply",
                                "list_reply": {
                                    "id": "corte",
                                    "title": "Corte de cabello"
                                }
                            }
                        }]
                    }
                }]
            }]
        }
        res = client.post("/webhook", json=payload)
        
        # Verificar que el estado se actualizó
        assert mock_state.appointment_data["servicio"] == "Corte de cabello"
        assert mock_state.current_intent == "agendar"
        mock_state_mgr.save_state.assert_called_once_with(mock_state)
        
        mock_send.assert_called_once_with(
            to="5215512345678",
            message="Perfecto, seleccionaste *Corte de cabello*. ¿Qué día te viene mejor?"
        )
        
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_webhook_post_agendar_sends_service_list():
    with patch("app.api.webhook.settings") as mock_settings, \
         patch("app.api.webhook.send_service_list") as mock_send_list, \
         patch("app.api.webhook.parse_intent") as mock_parse, \
         patch("app.api.webhook.state_manager") as mock_state_mgr:
         
        mock_settings.is_production = False
        mock_settings.phone_number_id = "1147614285101997"
        
        # Intent es agendar y el servicio no está seleccionado aún
        mock_parse.return_value = {
            "intent": "agendar",
            "servicio": None,
            "fecha": None,
            "hora": None,
            "nombre": None,
            "respuesta": "Claro, selecciona un servicio."
        }
        
        # Mock State
        mock_state = MagicMock()
        mock_state.messages = []
        mock_state.appointment_data = {}
        mock_state_mgr.get_state = AsyncMock(return_value=mock_state)
        mock_state_mgr.save_state = AsyncMock()
        
        payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "value": {
                        "messages": [{
                            "id": "msg_003",
                            "from": "5215512345678",
                            "timestamp": "1716800000",
                            "type": "text",
                            "text": {"body": "quiero una cita"}
                        }]
                    }
                }]
            }]
        }
        res = client.post("/webhook", json=payload)
        
        # Verificar que se llamó a send_service_list con la lista de servicios del negocio
        mock_send_list.assert_called_once()
        called_kwargs = mock_send_list.call_args[1]
        assert called_kwargs["to"] == "5215512345678"
        assert len(called_kwargs["services"]) == 4
        
    assert res.status_code == 200



