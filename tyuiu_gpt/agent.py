from typing import Final, TypedDict

import logging
from collections.abc import Sequence

from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from .depends import llm, redis, retriever
from .prompts import SYSTEM_PROMPT, USER_PROMPT

TTL = 3600
MAX_CHAT_HISTORY_LENGTH = 10

logger = logging.getLogger(__name__)


class State(TypedDict):
    """Состояние langgraph агента (FSM)

    Attributes:
        query: Запрос пользователя.
        conversation_history: История сообщений пользователя в рамках диалога.
        documents: Найденные документы по запросу пользователя.
        response: Финальный ответ агента.
    """
    query: str
    conversation_history: list[str]
    documents: list[Document]
    response: str


def format_documents(documents: Sequence[Document]) -> str:
    return "\n\n".join([document.page_content for document in documents])


async def fetch_conversation_history(
        state: State, config: RunnableConfig | None = None  # noqa: ARG001
) -> dict[str, list[str]]:
    """Получение истории диалога пользователя"""
    logger.info("---FETCH CONVERSATION HISTORY---")
    key = f"conversation_history:{config["configurable"]["thread_id"]}"
    messages = await redis.lrange(key, 0, -1)
    return {"conversation_history": [message.decode("utf-8") for message in reversed(messages)]}


async def retrieve(
        state: State, config: RunnableConfig | None = None  # noqa: ARG001
) -> dict[str, list[Document]]:
    """Извлечение документов из базы знаний"""
    logger.info("---RETRIEVE ---")
    documents = await retriever.ainvoke(state["query"])
    return {"documents": documents}


async def generate(
        state: State, config: RunnableConfig | None = None  # noqa: ARG001
) -> dict[str, str]:
    """Генерирует ответ на запрос пользователя"""
    logger.info("---GENERATE ---")
    user_prompt = USER_PROMPT.format(
        conversation_history="\n".join(state["conversation_history"]), query=state["query"]
    )
    chain = ChatPromptTemplate.from_template(SYSTEM_PROMPT) | llm | StrOutputParser()
    response = await chain.ainvoke({
        "user_prompt": user_prompt, "context": format_documents(state["documents"]),
    })
    return {"response": response}


async def store_conversation_history(
        state: State, config: RunnableConfig | None = None
) -> State:
    """Сохраняет истории диалога"""
    logger.info("---STORE CONVERSATION HISTORY---")
    key = f"conversation_history:{config["configurable"]["chat_id"]}"
    messages = [f"User: {state["query"]}", f"AI: {state["response"]}"]
    await redis.lpush(key, *messages)
    await redis.expire(key, TTL)
    await redis.ltrim(key, 0, MAX_CHAT_HISTORY_LENGTH)
    return state


# Инициализация графа
workflow = StateGraph(State)
# Добавление вершин графа
workflow.add_node("fetch_conversation_history", fetch_conversation_history)
workflow.add_node("retrieve", retrieve)
workflow.add_node("generate", generate)
workflow.add_node("store_conversation_history", store_conversation_history)
# Добавление ребёр графа
workflow.add_edge(START, "fetch_conversation_history")
workflow.add_edge("fetch_conversation_history", "retrieve")
workflow.add_edge("retrieve", "generate")
workflow.add_edge("generate", "store_conversation_history")
workflow.add_edge("store_conversation_history", END)
# Компиляция графа
agent: Final[CompiledStateGraph[State]] = workflow.compile()
