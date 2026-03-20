import asyncio
import contextlib
import io
import json
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import and_, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.auth import (
    create_access_token,
    decode_access_token,
    get_current_user,
    get_optional_current_user,
    hash_password,
    password_needs_rehash,
    verify_password,
)
from app.config import settings
from app.crypto import decrypt_bytes, decrypt_message, encrypt_bytes, encrypt_message
from app.database import Base, async_session, engine, get_db
from app.models import Message, User
from app.schemas import (
    ClearChatResponse,
    ConversationResponse,
    DeleteMessageRequest,
    DeleteMessageResponse,
    LoginRequest,
    MarkReadResponse,
    MessageCreate,
    MessageReactionRequest,
    MessageReplyPreview,
    MessageResponse,
    ReactionSummary,
    TokenResponse,
    UserResponse,
)

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
UPLOAD_DIR = Path(settings.UPLOAD_DIR)
if not UPLOAD_DIR.is_absolute():
    UPLOAD_DIR = BASE_DIR / UPLOAD_DIR
MESSAGE_TTL = timedelta(hours=settings.MESSAGE_TTL_HOURS)
MAX_UPLOAD_SIZE = 20 * 1024 * 1024
ALLOWED_MEDIA_TYPES = {"image/", "video/", "audio/"}
login_attempts: dict[str, deque[float]] = defaultdict(deque)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), geolocation=(), microphone=(self)"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com data:; "
            "img-src 'self' data: blob:; "
            "media-src 'self' blob:; "
            "connect-src 'self' ws: wss:; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "frame-ancestors 'none'; "
            "form-action 'self'"
        )
        return response


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: dict[int, set[WebSocket]] = {}

    async def connect(self, user_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.setdefault(user_id, set()).add(websocket)

    def disconnect(self, user_id: int, websocket: WebSocket) -> None:
        sockets = self.active_connections.get(user_id)
        if not sockets:
            return
        sockets.discard(websocket)
        if not sockets:
            self.active_connections.pop(user_id, None)

    async def send_to_user(self, user_id: int, payload: dict) -> None:
        sockets = list(self.active_connections.get(user_id, set()))
        stale: list[WebSocket] = []
        message = json.dumps(payload, default=str)
        for socket in sockets:
            try:
                await socket.send_text(message)
            except RuntimeError:
                stale.append(socket)
        for socket in stale:
            self.disconnect(user_id, socket)

    def is_online(self, user_id: int) -> bool:
        return bool(self.active_connections.get(user_id))


manager = ConnectionManager()


def infer_message_type(mime_type: str | None) -> str:
    if not mime_type:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing media content type")
    if any(mime_type.startswith(prefix) for prefix in ALLOWED_MEDIA_TYPES):
        if mime_type.startswith("image/"):
            return "image"
        if mime_type.startswith("video/"):
            return "video"
        return "audio"
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only images, videos, and audio files are supported")


def cleanup_rate_limit(ip_address: str) -> None:
    now = time.time()
    attempts = login_attempts[ip_address]
    while attempts and now - attempts[0] > settings.LOGIN_WINDOW_SECONDS:
        attempts.popleft()


def check_login_rate_limit(ip_address: str) -> None:
    cleanup_rate_limit(ip_address)
    if len(login_attempts[ip_address]) >= settings.LOGIN_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please wait and try again.",
        )


def record_failed_login(ip_address: str) -> None:
    cleanup_rate_limit(ip_address)
    login_attempts[ip_address].append(time.time())


def clear_login_rate_limit(ip_address: str) -> None:
    login_attempts.pop(ip_address, None)


async def ensure_schema_updates() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS message_type VARCHAR(20) NOT NULL DEFAULT 'text'"))
        await conn.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS media_name VARCHAR(255)"))
        await conn.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS media_mime_type VARCHAR(255)"))
        await conn.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS media_size INTEGER"))
        await conn.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS media_path VARCHAR(500)"))
        await conn.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS reply_to_message_id INTEGER"))
        await conn.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS deleted_for_sender BOOLEAN NOT NULL DEFAULT FALSE"))
        await conn.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS deleted_for_receiver BOOLEAN NOT NULL DEFAULT FALSE"))
        await conn.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS deleted_for_everyone BOOLEAN NOT NULL DEFAULT FALSE"))
        await conn.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS reactions_json TEXT NOT NULL DEFAULT '{}'"))
        await conn.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS is_delivered BOOLEAN NOT NULL DEFAULT FALSE"))


async def sync_fixed_users() -> None:
    async with async_session() as db:
        for user_id, username, password in settings.fixed_users:
            user = await db.get(User, user_id)
            hashed_password = hash_password(password)
            if user is None:
                db.add(User(id=user_id, username=username, password=hashed_password))
                continue

            user.username = username
            if not verify_password(password, user.password) or password_needs_rehash(user.password):
                user.password = hashed_password
            db.add(user)

        await db.commit()


async def cleanup_expired_messages(db: AsyncSession) -> int:
    cutoff = datetime.now(UTC) - MESSAGE_TTL
    result = await db.execute(select(Message).where(Message.timestamp < cutoff))
    expired_messages = result.scalars().all()

    for message in expired_messages:
        if message.media_path:
            with contextlib.suppress(FileNotFoundError):
                Path(message.media_path).unlink()
        await db.delete(message)

    if expired_messages:
        await db.commit()
    return len(expired_messages)


def parse_reactions(message: Message) -> dict[str, list[int]]:
    try:
        raw_reactions = json.loads(message.reactions_json or "{}")
    except json.JSONDecodeError:
        return {}
    reactions: dict[str, list[int]] = {}
    for emoji, user_ids in raw_reactions.items():
        if not isinstance(emoji, str) or not isinstance(user_ids, list):
            continue
        reactions[emoji] = [int(user_id) for user_id in user_ids if isinstance(user_id, int) or str(user_id).isdigit()]
    return reactions


def serialize_reactions(message: Message, current_user_id: int) -> list[ReactionSummary]:
    return [
        ReactionSummary(emoji=emoji, count=len(user_ids), reacted_by_me=current_user_id in user_ids)
        for emoji, user_ids in parse_reactions(message).items()
        if user_ids
    ]


def serialize_message(message: Message, current_user_id: int) -> MessageResponse:
    reply_preview = None
    reply_source = getattr(message, "reply_to_message", None)
    if reply_source is not None:
        reply_content = "This message was deleted" if reply_source.deleted_for_everyone else decrypt_message(reply_source.content)
        reply_preview = MessageReplyPreview(
            id=reply_source.id,
            sender_id=reply_source.sender_id,
            content=reply_content,
            message_type=reply_source.message_type,
        )
    is_deleted = message.deleted_for_everyone
    media_url = f"/api/messages/{message.id}/media" if message.media_path and not is_deleted else None
    return MessageResponse(
        id=message.id,
        sender_id=message.sender_id,
        receiver_id=message.receiver_id,
        content="" if is_deleted else decrypt_message(message.content),
        message_type="text" if is_deleted else message.message_type,
        media_name=None if is_deleted else message.media_name,
        media_mime_type=None if is_deleted else message.media_mime_type,
        media_size=None if is_deleted else message.media_size,
        media_url=media_url,
        reply_to_message_id=message.reply_to_message_id,
        reply_to_message=reply_preview,
        is_deleted=is_deleted,
        reactions=serialize_reactions(message, current_user_id),
        timestamp=message.timestamp,
        is_delivered=message.is_delivered,
        is_read=message.is_read,
        expires_at=message.timestamp + MESSAGE_TTL,
    )


async def build_conversation(db: AsyncSession, current_user: User) -> ConversationResponse:
    await cleanup_expired_messages(db)
    other_user = await db.scalar(
        select(User).where(User.id != current_user.id, User.username.in_(settings.fixed_usernames))
    )
    participants = [
        UserResponse(
            id=current_user.id,
            username=current_user.username,
            last_seen=current_user.last_seen,
            is_online=manager.is_online(current_user.id),
        )
    ]

    if other_user is None:
        return ConversationResponse(participants=participants, messages=[])

    participants.append(
        UserResponse(
            id=other_user.id,
            username=other_user.username,
            last_seen=other_user.last_seen,
            is_online=manager.is_online(other_user.id),
        )
    )
    result = await db.execute(
        select(Message)
        .where(
            or_(
                and_(Message.sender_id == current_user.id, Message.receiver_id == other_user.id),
                and_(Message.sender_id == other_user.id, Message.receiver_id == current_user.id),
            )
        )
        .order_by(Message.timestamp.asc())
    )
    messages = []
    for message in result.scalars().all():
        if message.sender_id == current_user.id and message.deleted_for_sender:
            continue
        if message.receiver_id == current_user.id and message.deleted_for_receiver:
            continue
        if message.reply_to_message_id:
            message.reply_to_message = await db.get(Message, message.reply_to_message_id)
        messages.append(message)
    return ConversationResponse(
        participants=participants,
        messages=[serialize_message(message, current_user.id) for message in messages],
    )


async def broadcast_message(message: Message) -> None:
    await manager.send_to_user(
        message.sender_id,
        {"type": "message.created", "message": serialize_message(message, message.sender_id).model_dump(mode="json")},
    )
    await manager.send_to_user(
        message.receiver_id,
        {"type": "message.created", "message": serialize_message(message, message.receiver_id).model_dump(mode="json")},
    )


async def broadcast_message_update(message: Message) -> None:
    await manager.send_to_user(
        message.sender_id,
        {"type": "message.updated", "message": serialize_message(message, message.sender_id).model_dump(mode="json")},
    )
    await manager.send_to_user(
        message.receiver_id,
        {"type": "message.updated", "message": serialize_message(message, message.receiver_id).model_dump(mode="json")},
    )


async def update_last_seen(user_id: int) -> datetime:
    async with async_session() as db:
        user = await db.get(User, user_id)
        if user is None:
            return datetime.now(UTC)
        user.last_seen = datetime.now(UTC)
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user.last_seen


async def broadcast_presence(user_id: int, is_online: bool) -> None:
    last_seen = await update_last_seen(user_id) if not is_online else datetime.now(UTC)
    payload = {
        "type": "presence.updated",
        "user_id": user_id,
        "is_online": is_online,
        "last_seen": last_seen.isoformat(),
    }
    for peer_id, _, _ in settings.fixed_users:
        await manager.send_to_user(peer_id, payload)


async def mark_messages_delivered_for_user(user_id: int) -> None:
    async with async_session() as db:
        result = await db.execute(select(Message).where(Message.receiver_id == user_id, Message.is_delivered.is_(False)))
        pending_messages = result.scalars().all()
        if not pending_messages:
            return

        sender_message_ids: dict[int, list[int]] = defaultdict(list)
        for message in pending_messages:
            message.is_delivered = True
            sender_message_ids[message.sender_id].append(message.id)
            db.add(message)

        await db.commit()

    delivered_ids: list[int] = []
    for sender_id, message_ids in sender_message_ids.items():
        delivered_ids.extend(message_ids)
        payload = {"type": "messages.delivered", "message_ids": message_ids, "receiver_id": user_id}
        await manager.send_to_user(sender_id, payload)
    if delivered_ids:
        await manager.send_to_user(user_id, {"type": "messages.delivered", "message_ids": delivered_ids, "receiver_id": user_id})


async def cleanup_loop() -> None:
    while True:
        try:
            async with async_session() as db:
                await cleanup_expired_messages(db)
        except Exception:
            pass
        await asyncio.sleep(settings.CLEANUP_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(_: FastAPI):
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    await ensure_schema_updates()
    await sync_fixed_users()
    cleanup_task = asyncio.create_task(cleanup_loop())
    try:
        yield
    finally:
        cleanup_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await cleanup_task
        await engine.dispose()


app = FastAPI(title="WokChat", version="4.0.0", lifespan=lifespan)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.TRUSTED_HOSTS,
)
if settings.FORCE_HTTPS:
    app.add_middleware(HTTPSRedirectMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
async def frontend() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> FileResponse:
    return FileResponse(STATIC_DIR / "favicon.svg", media_type="image/svg+xml")


@app.get("/api/health", tags=["system"])
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/config", tags=["system"])
async def client_config() -> dict[str, int | str | bool]:
    return {
        "message_ttl_hours": settings.MESSAGE_TTL_HOURS,
        "app_name": "WokChat",
        "allow_registration": False,
        "read_receipts": True,
        "max_upload_size_mb": MAX_UPLOAD_SIZE // (1024 * 1024),
    }


@app.post("/api/register", tags=["auth"])
async def register_disabled() -> None:
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account creation is disabled for this app")


@app.post("/api/login", response_model=TokenResponse, tags=["auth"])
async def login(
    payload: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    await cleanup_expired_messages(db)
    client_ip = request.client.host if request.client else "unknown"
    check_login_rate_limit(client_ip)

    if payload.username not in settings.fixed_usernames:
        record_failed_login(client_ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    result = await db.execute(select(User).where(User.username == payload.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(payload.password, user.password):
        record_failed_login(client_ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if password_needs_rehash(user.password):
        user.password = hash_password(payload.password)
        db.add(user)
        await db.commit()
        await db.refresh(user)

    clear_login_rate_limit(client_ip)
    token = create_access_token({"sub": str(user.id), "username": user.username})
    return TokenResponse(access_token=token)


@app.get("/api/me", response_model=UserResponse, tags=["users"])
async def get_me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(current_user)


@app.get("/api/messages", response_model=ConversationResponse, tags=["messages"])
async def get_messages(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)) -> ConversationResponse:
    return await build_conversation(db, current_user)


@app.get("/api/messages/search", response_model=list[MessageResponse], tags=["messages"])
async def search_messages(
    q: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[MessageResponse]:
    conversation = await build_conversation(db, current_user)
    query = q.strip().lower()
    if not query:
        return []
    return [message for message in conversation.messages if query in message.content.lower()]


@app.post("/api/messages", response_model=MessageResponse, status_code=status.HTTP_201_CREATED, tags=["messages"])
async def send_message(
    payload: MessageCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MessageResponse:
    await cleanup_expired_messages(db)
    if payload.receiver_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot message yourself")

    receiver = await db.get(User, payload.receiver_id)
    if not receiver or receiver.username not in settings.fixed_usernames:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Receiver not found")

    reply_to_message = None
    if payload.reply_to_message_id is not None:
        reply_to_message = await db.get(Message, payload.reply_to_message_id)
        if reply_to_message is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reply target not found")

    message = Message(
        sender_id=current_user.id,
        receiver_id=payload.receiver_id,
        content=encrypt_message(payload.content),
        message_type="text",
        reply_to_message_id=payload.reply_to_message_id,
        is_delivered=manager.is_online(payload.receiver_id),
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)
    message.reply_to_message = reply_to_message
    await broadcast_message(message)
    return serialize_message(message, current_user.id)


@app.post("/api/messages/media", response_model=MessageResponse, status_code=status.HTTP_201_CREATED, tags=["messages"])
async def send_media_message(
    receiver_id: int = Form(...),
    content: str = Form(""),
    reply_to_message_id: int | None = Form(default=None),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MessageResponse:
    await cleanup_expired_messages(db)
    if receiver_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot message yourself")

    receiver = await db.get(User, receiver_id)
    if not receiver or receiver.username not in settings.fixed_usernames:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Receiver not found")

    reply_to_message = None
    if reply_to_message_id is not None:
        reply_to_message = await db.get(Message, reply_to_message_id)
        if reply_to_message is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reply target not found")

    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty")
    if len(raw_bytes) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File is too large")

    message_type = infer_message_type(file.content_type)
    encrypted_path = UPLOAD_DIR / f"{uuid4().hex}.bin"
    encrypted_path.write_bytes(encrypt_bytes(raw_bytes))

    message = Message(
        sender_id=current_user.id,
        receiver_id=receiver_id,
        content=encrypt_message(content.strip()),
        message_type=message_type,
        media_name=(file.filename or f"{message_type}.bin")[:255],
        media_mime_type=file.content_type,
        media_size=len(raw_bytes),
        media_path=str(encrypted_path),
        reply_to_message_id=reply_to_message_id,
        is_delivered=manager.is_online(receiver_id),
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)
    message.reply_to_message = reply_to_message
    await broadcast_message(message)
    return serialize_message(message, current_user.id)


@app.delete("/api/messages/{message_id}", response_model=DeleteMessageResponse, tags=["messages"])
async def delete_message(
    message_id: int,
    payload: DeleteMessageRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DeleteMessageResponse:
    message = await db.get(Message, message_id)
    if not message:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    if current_user.id not in {message.sender_id, message.receiver_id}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to delete this message")

    if payload.delete_for_everyone:
        if current_user.id != message.sender_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the sender can delete for everyone")
        if message.media_path:
            with contextlib.suppress(FileNotFoundError):
                Path(message.media_path).unlink()
        message.content = encrypt_message("")
        message.message_type = "text"
        message.media_name = None
        message.media_mime_type = None
        message.media_size = None
        message.media_path = None
        message.deleted_for_everyone = True
        message.reactions_json = "{}"
        db.add(message)
    else:
        if current_user.id == message.sender_id:
            message.deleted_for_sender = True
        else:
            message.deleted_for_receiver = True
        db.add(message)

    await db.commit()
    if payload.delete_for_everyone:
        await broadcast_message_update(message)
    else:
        event = {
            "type": "message.deleted",
            "deleted_message_id": message_id,
            "delete_for_everyone": payload.delete_for_everyone,
            "deleted_by": current_user.id,
        }
        await manager.send_to_user(message.sender_id, event)
        await manager.send_to_user(message.receiver_id, event)
    return DeleteMessageResponse(deleted_message_id=message_id, delete_for_everyone=payload.delete_for_everyone)


@app.delete("/api/messages", response_model=ClearChatResponse, tags=["messages"])
async def clear_chat(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ClearChatResponse:
    other_user = await db.scalar(
        select(User).where(User.id != current_user.id, User.username.in_(settings.fixed_usernames))
    )
    if other_user is None:
        return ClearChatResponse(deleted_count=0)

    result = await db.execute(
        select(Message).where(
            or_(
                and_(Message.sender_id == current_user.id, Message.receiver_id == other_user.id),
                and_(Message.sender_id == other_user.id, Message.receiver_id == current_user.id),
            )
        )
    )
    messages = result.scalars().all()
    for message in messages:
        if message.sender_id == current_user.id:
            message.deleted_for_sender = True
        if message.receiver_id == current_user.id:
            message.deleted_for_receiver = True
        db.add(message)
    await db.commit()

    event = {"type": "chat.cleared", "cleared_by": current_user.id}
    await manager.send_to_user(current_user.id, event)
    return ClearChatResponse(deleted_count=len(messages))


@app.post("/api/messages/{message_id}/reactions", response_model=MessageResponse, tags=["messages"])
async def toggle_message_reaction(
    message_id: int,
    payload: MessageReactionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MessageResponse:
    message = await db.get(Message, message_id)
    if not message:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    if current_user.id not in {message.sender_id, message.receiver_id}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to react to this message")
    if message.deleted_for_everyone:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Deleted messages cannot be reacted to")

    reactions = parse_reactions(message)
    user_ids = reactions.get(payload.emoji, [])
    if current_user.id in user_ids:
        user_ids = [user_id for user_id in user_ids if user_id != current_user.id]
    else:
        user_ids.append(current_user.id)
    if user_ids:
        reactions[payload.emoji] = sorted(set(user_ids))
    else:
        reactions.pop(payload.emoji, None)

    message.reactions_json = json.dumps(reactions, separators=(",", ":"))
    db.add(message)
    await db.commit()
    await db.refresh(message)
    await broadcast_message_update(message)
    return serialize_message(message, current_user.id)


@app.get("/api/messages/{message_id}/media", tags=["messages"])
async def get_media(
    message_id: int,
    token: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
) -> StreamingResponse:
    await cleanup_expired_messages(db)
    if current_user is None and token:
        try:
            payload = decode_access_token(token)
            current_user = await db.get(User, int(payload["sub"]))
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid media token") from exc
    if current_user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    message = await db.get(Message, message_id)
    if not message:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media not found")
    if current_user.id not in {message.sender_id, message.receiver_id}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to access this media")
    if message.deleted_for_everyone:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This message was deleted")
    if message.sender_id == current_user.id and message.deleted_for_sender:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This message was deleted")
    if message.receiver_id == current_user.id and message.deleted_for_receiver:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This message was deleted")
    if not message.media_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This message has no attachment")

    media_path = Path(message.media_path)
    if not media_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stored media file is missing")

    decrypted = decrypt_bytes(media_path.read_bytes())
    headers = {
        "Content-Disposition": f'inline; filename="{message.media_name or "attachment"}"',
        "Cache-Control": "private, no-store",
        "Content-Length": str(len(decrypted)),
    }
    return StreamingResponse(
        io.BytesIO(decrypted),
        media_type=message.media_mime_type or "application/octet-stream",
        headers=headers,
    )


@app.post("/api/messages/read", response_model=MarkReadResponse, tags=["messages"])
async def mark_messages_read(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MarkReadResponse:
    await cleanup_expired_messages(db)
    result = await db.execute(select(Message).where(Message.receiver_id == current_user.id, Message.is_read.is_(False)))
    unread_messages = result.scalars().all()
    sender_ids = {message.sender_id for message in unread_messages}
    message_ids = [message.id for message in unread_messages]

    for message in unread_messages:
        message.is_delivered = True
        message.is_read = True

    await db.commit()

    if message_ids:
        payload = {"type": "messages.read", "message_ids": message_ids, "reader_id": current_user.id}
        for sender_id in sender_ids:
            await manager.send_to_user(sender_id, payload)
        await manager.send_to_user(current_user.id, payload)

    return MarkReadResponse(updated_count=len(unread_messages))


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    host = websocket.headers.get("host", "").split(":", 1)[0]
    if host and host not in settings.TRUSTED_HOSTS:
        await websocket.close(code=4403)
        return

    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4401)
        return

    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
    except Exception:
        await websocket.close(code=4401)
        return

    await manager.connect(user_id, websocket)
    await mark_messages_delivered_for_user(user_id)
    await broadcast_presence(user_id, True)
    try:
        await websocket.send_json({"type": "session.ready", "user_id": user_id})
        while True:
            raw_message = await websocket.receive_text()
            with contextlib.suppress(json.JSONDecodeError):
                payload = json.loads(raw_message)
                if payload.get("type") == "typing" and "receiver_id" in payload:
                    await manager.send_to_user(
                        int(payload["receiver_id"]),
                        {
                            "type": "typing.updated",
                            "user_id": user_id,
                            "is_typing": bool(payload.get("is_typing", False)),
                        },
                    )
    except WebSocketDisconnect:
        manager.disconnect(user_id, websocket)
        await broadcast_presence(user_id, False)


@app.options("/{rest_of_path:path}", include_in_schema=False)
async def preflight(_: str) -> Response:
    return Response(status_code=status.HTTP_204_NO_CONTENT)
