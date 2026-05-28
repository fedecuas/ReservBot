from pydantic import BaseModel
from typing import Optional


class TextMessage(BaseModel):
    body: str


class IncomingMessage(BaseModel):
    id: str
    from_number: str  # número del cliente (ej. 5215512345678)
    timestamp: str
    type: str          # "text", "audio", "image", etc.
    text: Optional[TextMessage] = None

    @property
    def text_body(self) -> str:
        return self.text.body if self.text else ""


class WebhookPayload(BaseModel):
    """Estructura completa del payload de WhatsApp Cloud API."""
    object: str
    entry: list

    def extract_messages(self) -> list[IncomingMessage]:
        messages = []
        for entry in self.entry:
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for msg in value.get("messages", []):
                    try:
                        messages.append(IncomingMessage(
                            id=msg["id"],
                            from_number=msg["from"],
                            timestamp=msg["timestamp"],
                            type=msg.get("type", "text"),
                            text=TextMessage(**msg["text"]) if "text" in msg else None
                        ))
                    except Exception:
                        continue
        return messages
