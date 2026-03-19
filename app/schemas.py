from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    last_seen: datetime
    is_online: bool = False


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=30)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        username = value.strip()
        if len(username) < 3:
            raise ValueError("Username must be at least 3 characters long")
        return username


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=30)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        username = value.strip()
        if len(username) < 3:
            raise ValueError("Username must be at least 3 characters long")
        return username


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MessageCreate(BaseModel):
    receiver_id: int
    content: str = Field(min_length=1, max_length=4000)
    reply_to_message_id: int | None = None

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        content = value.strip()
        if not content:
            raise ValueError("Message content cannot be empty")
        return content


class MessageReplyPreview(BaseModel):
    id: int
    sender_id: int
    content: str
    message_type: Literal["text", "image", "video", "audio"]


class ReactionSummary(BaseModel):
    emoji: str
    count: int
    reacted_by_me: bool


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sender_id: int
    receiver_id: int
    content: str
    message_type: Literal["text", "image", "video", "audio"]
    media_name: str | None = None
    media_mime_type: str | None = None
    media_size: int | None = None
    media_url: str | None = None
    reply_to_message_id: int | None = None
    reply_to_message: MessageReplyPreview | None = None
    is_deleted: bool = False
    reactions: list[ReactionSummary] = Field(default_factory=list)
    timestamp: datetime
    is_delivered: bool = False
    is_read: bool
    expires_at: datetime


class ConversationResponse(BaseModel):
    participants: list[UserResponse]
    messages: list[MessageResponse]


class MarkReadResponse(BaseModel):
    updated_count: int


class DeleteMessageRequest(BaseModel):
    delete_for_everyone: bool = False


class DeleteMessageResponse(BaseModel):
    deleted_message_id: int
    delete_for_everyone: bool


class ClearChatResponse(BaseModel):
    deleted_count: int


class MessageReactionRequest(BaseModel):
    emoji: str = Field(min_length=1, max_length=16)

    @field_validator("emoji")
    @classmethod
    def normalize_emoji(cls, value: str) -> str:
        emoji = value.strip()
        if not emoji:
            raise ValueError("Emoji cannot be empty")
        return emoji
