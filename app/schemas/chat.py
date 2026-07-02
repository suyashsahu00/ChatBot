"""
Chat request/response schemas.
Migrated from legacy_app.py L92-98.
"""

from pydantic import BaseModel
from typing import List


class Message(BaseModel):
    """A single chat message with role and content."""
    role: str
    content: str


class ChatPayload(BaseModel):
    """Incoming chat request payload."""
    session_id: str
    messages: List[Message]
