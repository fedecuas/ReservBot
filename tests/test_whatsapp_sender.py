import pytest
from unittest.mock import patch, MagicMock
from app.services.whatsapp_sender import send_text_message


@pytest.mark.anyio
async def test_send_text_message_normalization():
    with patch("app.services.whatsapp_sender.settings") as mock_settings, \
         patch("httpx.AsyncClient.post") as mock_post:
         
        mock_settings.phone_number_id = "12345"
        mock_settings.whatsapp_token = "token"
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        # Caso de prueba: número de 13 dígitos empezando por 521
        result = await send_text_message("5215659155222", "test")
        
        assert result is True
        
        # Verificar que httpx.post se haya llamado con el número normalizado sin el '1'
        called_kwargs = mock_post.call_args[1]
        assert called_kwargs["json"]["to"] == "525659155222"


@pytest.mark.anyio
async def test_send_text_message_no_normalization_needed():
    with patch("app.services.whatsapp_sender.settings") as mock_settings, \
         patch("httpx.AsyncClient.post") as mock_post:
         
        mock_settings.phone_number_id = "12345"
        mock_settings.whatsapp_token = "token"
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        # Caso de prueba: número que no necesita normalización
        result = await send_text_message("525659155222", "test")
        
        assert result is True
        
        # Verificar que el número se mantuvo intacto
        called_kwargs = mock_post.call_args[1]
        assert called_kwargs["json"]["to"] == "525659155222"
