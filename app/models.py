from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    sender_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    receiver_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    reply_to_message_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("messages.id"), nullable=True, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_type: Mapped[str] = mapped_column(String(20), default="text", nullable=False)
    media_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    media_mime_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    media_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    media_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    deleted_for_sender: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deleted_for_receiver: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deleted_for_everyone: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reactions_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    is_delivered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
