from typing import Final

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    HTTPException,
    Query,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import JSONResponse
from langchain_core.documents import Document
from langchain_core.runnables import RunnableConfig
from pydantic import NonNegativeInt

from .agent import agent
from .broker import broker, faststream_app, message_exchange
from .database import read_chat_history, read_message
from .depends import get_connection_manager, retriever
from .exceptions import AppError
from .indexing import indexing_chain, open_temp_file
from .schemas import ChatHistory, Message, Role
from .websockets import ConnectionManager

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
    await faststream_app.broker.start()
    logger.info("Broker started")
    yield
    await faststream_app.broker.stop()
    logger.info("Broker stopped")


app: Final[FastAPI] = FastAPI(lifespan=lifespan)

api_router = APIRouter(prefix="/api/v1", tags=["REST API"])

ws_router = APIRouter(prefix="/ws", tags=["Websockets"])


@api_router.post(
    path="/chat/completions",
    status_code=status.HTTP_200_OK,
    response_model=Message,
    summary="Чат с AI агентом",
)
async def answer(user_message: Message, background_tasks: BackgroundTasks) -> Message:
    config = RunnableConfig(configurable={"chat_id": user_message.chat_id})
    state = await agent.ainvoke({"query": user_message.text}, config=config)
    ai_message = Message(
        chat_id=user_message.chat_id, role=Role.AI, text=state["response"]
    )
    background_tasks.add_task(
        broker.publish,
        [user_message, ai_message],
        queue="messages_persisting",
        exchange=message_exchange,
    )
    return ai_message


@api_router.get(
    path="chat-history/messages/{id}",
    status_code=status.HTTP_200_OK,
    response_model=Message,
    summary="Получение сообщения"
)
async def get_message(id: UUID) -> Message:  # noqa: A002
    message = await read_message(id)
    if message is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Message with id {id} not found"
        )
    return message


@api_router.get(
    path="/chat-history/{chat_id}",
    status_code=status.HTTP_200_OK,
    response_model=ChatHistory,
    summary="Получение истории чата"
)
async def get_chat_history(
        chat_id: UUID,
        page: NonNegativeInt = Query(...),
        limit: NonNegativeInt = Query(...),
) -> ChatHistory:
    return await read_chat_history(chat_id, page, limit)


@api_router.post(
    path="/documents/upload",
    status_code=status.HTTP_201_CREATED,
    response_model=list[Document],
    summary="Загружает документы в базу знаний"
)
async def upload_documents(file: UploadFile = File(...)) -> list[Document]:
    data = await file.read()
    async with open_temp_file(data) as temp_file:
        return await indexing_chain.ainvoke(temp_file)


@api_router.get(
    path="/documents/search",
    status_code=status.HTTP_200_OK,
    response_model=list[Document],
    summary="Поиск релевантных запросу документов"
)
async def search_documents(query: str = Query(...)) -> list[Document]:
    return await retriever.ainvoke(query)


@ws_router.websocket("/chat/{chat_id}")
async def chat(
        chat_id: UUID,
        websocket: WebSocket,
        background_tasks: BackgroundTasks,
        connection_manager: ConnectionManager = Depends(get_connection_manager)
) -> None:
    await connection_manager.connect(websocket, chat_id)
    try:
        data = await websocket.receive_json()
        user_message = Message.model_validate(data)
        config = RunnableConfig(configurable={"chat_id": chat_id})
        state = await agent.ainvoke({"query": user_message.text}, config=config)
        ai_message = Message(chat_id=chat_id, role=Role.AI, text=state["response"])
        await connection_manager.send(chat_id, ai_message)
        background_tasks.add_task(
            broker.publish,
            [user_message, ai_message],
            queue="messages_persisting",
            exchange=message_exchange
        )
    except WebSocketDisconnect:
        await connection_manager.disconnect(chat_id)


@app.exception_handler(AppError)
def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    logger.error(exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content={"detail": str(exc)}
    )


@app.exception_handler(ValueError)
def handle_value_error(request: Request, exc: ValueError) -> JSONResponse:
    logger.error(exc)
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST, content={"detail": str(exc)}
    )


app.include_router(api_router)
app.include_router(ws_router)
