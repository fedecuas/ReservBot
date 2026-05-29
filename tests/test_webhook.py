import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from app.main import app

client = TestClient(app)


def test_health():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_webhook_verify_valid():
    with patch("app.routers.webhook.settings") as mock_settings:
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
    with patch("app.routers.webhook.settings") as mock_settings:
        mock_settings.verify_token = "test_token"
        mock_settings.is_production = False
        res = client.get("/webhook", params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong_token",
            "hub.challenge": "12345"
        })
    assert res.status_code == 403


def test_webhook_post_returns_ok():
    with patch("app.routers.webhook.settings") as mock_settings, \
         patch("app.routers.webhook.send_text_message") as mock_send:
        mock_settings.is_production = False
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
        mock_send.assert_called_once_with(
            to="5215512345678",
            message="Hola! Soy ReservBot 🤖 ¿En qué te puedo ayudar?"
        )
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}

