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


def test_webhook_post_confirmar_creates_calendar_event():
    with patch("app.api.webhook.settings") as mock_settings, \
         patch("app.api.webhook.send_text_message") as mock_send, \
         patch("app.api.webhook.parse_intent") as mock_parse, \
         patch("app.api.webhook.state_manager") as mock_state_mgr, \
         patch("app.api.webhook.create_calendar_event") as mock_create_event:
         
        mock_settings.is_production = False
        
        # Intent es confirmar con todos los datos completos
        mock_parse.return_value = {
            "intent": "confirmar",
            "servicio": "Corte de cabello",
            "fecha": "2026-06-01",
            "hora": "15:00",
            "nombre": "Juan",
            "respuesta": "¡Perfecto Juan! Tu cita para Corte de cabello el 2026-06-01 a las 15:00 ha sido agendada."
        }
        
        # Mock State
        mock_state = MagicMock()
        mock_state.messages = []
        mock_state.appointment_data = {
            "nombre": "Juan",
            "servicio": "Corte de cabello",
            "fecha": "2026-06-01",
            "hora": "15:00"
        }
        mock_state_mgr.get_state = AsyncMock(return_value=mock_state)
        mock_state_mgr.save_state = AsyncMock()
        
        payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "value": {
                        "messages": [{
                            "id": "msg_004",
                            "from": "5215512345678",
                            "timestamp": "1716800000",
                            "type": "text",
                            "text": {"body": "sí, está bien"}
                        }]
                    }
                }]
            }]
        }
        res = client.post("/webhook", json=payload)
        
        # Verificar que se llamó a create_calendar_event
        mock_create_event.assert_called_once_with({
            "nombre": "Juan",
            "servicio": "Corte de cabello",
            "fecha": "2026-06-01",
            "hora": "15:00"
        })
        
        mock_send.assert_called_once_with(
            to="5215512345678",
            message="¡Perfecto Juan! Tu cita para Corte de cabello el 2026-06-01 a las 15:00 ha sido agendada."
        )
        
    assert res.status_code == 200


def test_webhook_interactive_hour_selection_creates_event():
    with patch("app.api.webhook.settings") as mock_settings, \
         patch("app.api.webhook.send_text_message") as mock_send, \
         patch("app.api.webhook.state_manager") as mock_state_mgr, \
         patch("app.api.webhook.create_calendar_event") as mock_create_event:

        mock_settings.is_production = False

        # Mock State
        mock_state = MagicMock()
        mock_state.appointment_data = {
            "nombre": "Juan",
            "servicio": "Corte de cabello",
            "fecha": "2026-06-01"
        }
        mock_state_mgr.get_state = AsyncMock(return_value=mock_state)
        mock_state_mgr.save_state = AsyncMock()

        payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "value": {
                        "messages": [{
                            "id": "msg_005",
                            "from": "5215512345678",
                            "timestamp": "1716800000",
                            "type": "interactive",
                            "interactive": {
                                "type": "list_reply",
                                "list_reply": {
                                    "id": "hora_1500",
                                    "title": "15:00"
                                }
                            }
                        }]
                    }
                }]
            }]
        }
        res = client.post("/webhook", json=payload)

        # Verificaciones
        assert mock_state.appointment_data["hora"] == "15:00"
        assert mock_state.current_intent == "confirmar"
        mock_state_mgr.save_state.assert_called_once_with(mock_state)

        mock_create_event.assert_called_once()
        mock_send.assert_called_once_with(
            to="5215512345678",
            message="¡Perfecto Juan! 🎉 Confirmamos tu cita:\n\n✂️ *Servicio:* Corte de cabello\n📅 *Fecha:* lunes 1 de junio\n⏰ *Hora:* 15:00\n\n¡Te esperamos! Si necesitas cambiar algo, escríbeme 😊"
        )
    assert res.status_code == 200


def test_webhook_post_sends_time_slots_list():
    with patch("app.api.webhook.settings") as mock_settings, \
         patch("app.api.webhook.send_text_message") as mock_send, \
         patch("app.api.webhook.parse_intent") as mock_parse, \
         patch("app.api.webhook.state_manager") as mock_state_mgr, \
         patch("app.api.webhook.get_business_by_phone") as mock_get_biz, \
         patch("app.api.webhook.check_availability") as mock_check, \
         patch("app.api.webhook._get_credentials") as mock_get_creds, \
         patch("app.api.webhook.send_time_slots_list") as mock_send_slots:

        mock_get_creds.return_value = None
        mock_settings.is_production = False
        mock_settings.google_calendar_id = "test_cal"

        mock_parse.return_value = {
            "intent": "confirmar",
            "servicio": "Corte de cabello",
            "fecha": "2026-06-01",
            "hora": None,
            "nombre": "Juan",
            "respuesta": "Excelente, aquí están los horarios para el 2026-06-01:"
        }

        # Mock State
        mock_state = MagicMock()
        mock_state.messages = []
        mock_state.appointment_data = {
            "nombre": "Juan",
            "servicio": "Corte de cabello",
            "fecha": "2026-06-01"
        }
        mock_state_mgr.get_state = AsyncMock(return_value=mock_state)
        mock_state_mgr.save_state = AsyncMock()

        # Mock Business
        mock_business = MagicMock()
        mock_business.services = [{"name": "Corte de cabello", "duration_min": 30}]
        mock_get_biz.return_value = mock_business

        # Mock Slots
        mock_check.return_value = ["09:00", "09:30"]

        payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "value": {
                        "messages": [{
                            "id": "msg_006",
                            "from": "5215512345678",
                            "timestamp": "1716800000",
                            "type": "text",
                            "text": {"body": "quiero agendar mañana"}
                        }]
                    }
                }]
            }]
        }
        res = client.post("/webhook", json=payload)

        # Verificaciones
        mock_check.assert_called_once_with(
            date_str="2026-06-01",
            duration_min=30,
            calendar_id="test_cal",
            credentials=None
        )
        mock_send_slots.assert_called_once_with(
            to="5215512345678",
            slots=["09:00", "09:30"],
            date_str="2026-06-01",
            service_name="Corte de cabello"
        )
        mock_send.assert_called_once_with(
            to="5215512345678",
            message="Excelente, aquí están los horarios para el 2026-06-01:"
        )

    assert res.status_code == 200


def test_webhook_interactive_multiday_hour_selection_creates_event():
    with patch("app.api.webhook.settings") as mock_settings, \
         patch("app.api.webhook.send_text_message") as mock_send, \
         patch("app.api.webhook.state_manager") as mock_state_mgr, \
         patch("app.api.webhook.create_calendar_event") as mock_create_event:

        mock_settings.is_production = False

        # Mock State
        mock_state = MagicMock()
        mock_state.appointment_data = {
            "nombre": "Juan",
            "servicio": "Corte de cabello",
            "fechas_candidatas": ["2026-06-02", "2026-06-03"]
        }
        mock_state_mgr.get_state = AsyncMock(return_value=mock_state)
        mock_state_mgr.save_state = AsyncMock()

        payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "value": {
                        "messages": [{
                            "id": "msg_007",
                            "from": "5215512345678",
                            "timestamp": "1716800000",
                            "type": "interactive",
                            "interactive": {
                                "type": "list_reply",
                                "list_reply": {
                                    "id": "hora_20260602_1500",
                                    "title": "15:00"
                                }
                            }
                        }]
                    }
                }]
            }]
        }
        res = client.post("/webhook", json=payload)

        # Verificaciones
        assert mock_state.appointment_data["fecha"] == "2026-06-02"
        assert "fechas_candidatas" not in mock_state.appointment_data
        assert mock_state.appointment_data["hora"] == "15:00"
        assert mock_state.current_intent == "confirmar"
        mock_state_mgr.save_state.assert_called_once_with(mock_state)

        mock_create_event.assert_called_once()
        mock_send.assert_called_once_with(
            to="5215512345678",
            message="¡Perfecto Juan! 🎉 Confirmamos tu cita:\n\n✂️ *Servicio:* Corte de cabello\n📅 *Fecha:* martes 2 de junio\n⏰ *Hora:* 15:00\n\n¡Te esperamos! Si necesitas cambiar algo, escríbeme 😊"
        )
    assert res.status_code == 200


def test_webhook_post_sends_multiday_time_slots_list():
    with patch("app.api.webhook.settings") as mock_settings, \
         patch("app.api.webhook.send_text_message") as mock_send, \
         patch("app.api.webhook.parse_intent") as mock_parse, \
         patch("app.api.webhook.state_manager") as mock_state_mgr, \
         patch("app.api.webhook.get_business_by_phone") as mock_get_biz, \
         patch("app.api.webhook.check_availability") as mock_check, \
         patch("app.api.webhook._get_credentials") as mock_get_creds, \
         patch("app.api.webhook.send_time_slots_list") as mock_send_slots:

        mock_get_creds.return_value = None
        mock_settings.is_production = False
        mock_settings.google_calendar_id = "test_cal"

        mock_parse.return_value = {
            "intent": "consultar",
            "servicio": "Corte de cabello",
            "fecha": None,
            "fechas_candidatas": ["2026-06-02", "2026-06-03"],
            "hora": None,
            "nombre": "Juan",
            "respuesta": "Claro! Aquí te muestro los horarios disponibles para ambos días 😊"
        }

        # Mock State
        mock_state = MagicMock()
        mock_state.messages = []
        mock_state.appointment_data = {
            "nombre": "Juan",
            "servicio": "Corte de cabello",
            "fechas_candidatas": ["2026-06-02", "2026-06-03"]
        }
        mock_state_mgr.get_state = AsyncMock(return_value=mock_state)
        mock_state_mgr.save_state = AsyncMock()

        # Mock Business
        mock_business = MagicMock()
        mock_business.services = [{"name": "Corte de cabello", "duration_min": 30}]
        mock_get_biz.return_value = mock_business

        # Mock Slots
        mock_check.return_value = ["09:00", "09:30"]

        payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "value": {
                        "messages": [{
                            "id": "msg_008",
                            "from": "5215512345678",
                            "timestamp": "1716800000",
                            "type": "text",
                            "text": {"body": "¿qué horarios tienes?"}
                        }]
                    }
                }]
            }]
        }
        res = client.post("/webhook", json=payload)

        # Verificaciones
        assert mock_check.call_count == 2
        mock_check.assert_any_call(
            date_str="2026-06-02",
            duration_min=30,
            calendar_id="test_cal",
            credentials=None
        )
        mock_check.assert_any_call(
            date_str="2026-06-03",
            duration_min=30,
            calendar_id="test_cal",
            credentials=None
        )
        
        assert mock_send_slots.call_count == 2
        mock_send_slots.assert_any_call(
            to="5215512345678",
            slots=["09:00", "09:30"],
            date_str="2026-06-02",
            service_name="Corte de cabello",
            id_prefix="hora_20260602_"
        )
        mock_send_slots.assert_any_call(
            to="5215512345678",
            slots=["09:00", "09:30"],
            date_str="2026-06-03",
            service_name="Corte de cabello",
            id_prefix="hora_20260603_"
        )

    assert res.status_code == 200





