from pydantic import BaseModel
from typing import Optional


class TextMessage(BaseModel):
    body: str


class IncomingMessage(BaseModel):
    id: str
    from_number: str  # número del cliente (ej. 5215512345678)
    timestamp: str
    type: str          # "text", "interactive", etc.
    text: Optional[TextMessage] = None
    interactive_reply_id: str = ""
    interactive_reply_title: str = ""

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
                        msg_type = msg.get("type", "text")
                        interactive_id = ""
                        interactive_title = ""
                        
                        if msg_type == "interactive" and "interactive" in msg:
                            interactive_data = msg["interactive"]
                            reply_type = interactive_data.get("type")
                            if reply_type == "list_reply" and "list_reply" in interactive_data:
                                interactive_id = interactive_data["list_reply"].get("id", "")
                                interactive_title = interactive_data["list_reply"].get("title", "")
                            elif reply_type == "button_reply" and "button_reply" in interactive_data:
                                interactive_id = interactive_data["button_reply"].get("id", "")
                                interactive_title = interactive_data["button_reply"].get("title", "")

                        messages.append(IncomingMessage(
                            id=msg["id"],
                            from_number=msg["from"],
                            timestamp=msg["timestamp"],
                            type=msg_type,
                            text=TextMessage(**msg["text"]) if "text" in msg else None,
                            interactive_reply_id=interactive_id,
                            interactive_reply_title=interactive_title
                        ))
                    except Exception:
                        continue
        return messages

