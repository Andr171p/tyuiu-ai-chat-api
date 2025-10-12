from typing import Final

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import NonNegativeInt
from sqlalchemy import CheckConstraint, DateTime, Text, func, insert, select
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .exceptions import CreationError, DataConflictError, ReadingError
from .schemas import ChatHistory, Message
from .settings import settings

engine: Final[AsyncEngine] = create_async_engine(url=settings.postgres.sqlalchemy_url, echo=True)

sessionmaker: Final[async_sessionmaker[AsyncSession]] = async_sessionmaker(
        engine, class_=AsyncSession, autoflush=False, expire_on_commit=False
)


class Base(AsyncAttrs, DeclarativeBase):
    __abstract__ = True

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
        server_default=func.gen_random_uuid()
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class MessageModel(Base):
    __tablename__ = "messages"

    chat_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), unique=False)
    role: Mapped[str]
    text: Mapped[str] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint("role IN ('user', 'ai')", name="check_role_values"),
    )


async def add_messages(messages: list[Message]) -> None:
    """Сохраняет сообщения в базу данных.

    :param messages: Сообщения которые нужно сохранить
    """
    try:
        async with sessionmaker() as session:
            stmt = insert(MessageModel)
            values = [message.model_dump() for message in messages]
            await session.execute(stmt, values)
            await session.commit()
    except SQLAlchemyError as e:
        await session.rollback()
        raise CreationError(f"Error occurred while messages adding, error: {e}") from e
    except IntegrityError as e:
        await session.rollback()
        raise DataConflictError(f"Conflict while messages adding, error: {e}") from e


async def read_message(id: UUID) -> Message | None:  # noqa: A002
    """Получает сообщение по его уникальному идентификатору.

    :param id: Уникальный идентификатор сообщения.
    """
    try:
        async with sessionmaker() as session:
            stmt = select(MessageModel).where(MessageModel.id == id)
            result = await session.execute(stmt)
            model = result.scalar_one_or_none()
        return Message.model_validate(model) if model else None
    except SQLAlchemyError as e:
        raise ReadingError(f"Error occurred while reading messages, error: {e}") from e


async def read_chat_history(
        chat_id: UUID, page: NonNegativeInt, limit: NonNegativeInt
) -> ChatHistory:
    try:
        async with sessionmaker() as session:
            stmt = (
                select(MessageModel, func.count(MessageModel.id).over().label("total_count"))
                .where(MessageModel.chat_id == chat_id)
                .order_by(MessageModel.created_at.asc())
                .offset((page - 1) * limit)
                .limit(limit)
            )
            results = await session.execute(stmt)
            rows = results.all()
            if not rows:
                return ChatHistory(
                    total_count=0, page=page, limit=limit, chat_id=chat_id, messages=[]
                )
            total_count = rows[0].total_count
            messages = [Message.model_validate(row[0]) for row in rows]
            return ChatHistory(
                total_count=total_count, page=page, limit=limit, chat_id=chat_id, messages=messages
            )
    except SQLAlchemyError as e:
        raise ReadingError(f"Error occurred while reading chat history, error: {e}") from e
