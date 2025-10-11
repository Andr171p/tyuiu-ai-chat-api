from typing import Final

from embeddings_service.langchain import RemoteHTTPEmbeddings
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_core.retrievers import BaseRetriever
from langchain_core.vectorstores import VectorStore
from langchain_gigachat import GigaChat
from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
    TextSplitter,
)
from redis.asyncio import Redis

from .settings import settings
from .websockets import ConnectionManager, InMemoryConnectionManager

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 20
TIMEOUT = 120

redis: Final[Redis] = Redis.from_url(settings.redis.url)

md_splitter: Final[MarkdownHeaderTextSplitter] = MarkdownHeaderTextSplitter(
    headers_to_split_on=[("#", "Заголовок")]
)

text_splitter: Final[TextSplitter] = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    length_function=len,
    separators=["\n#"],
)

embeddings: Final[Embeddings] = RemoteHTTPEmbeddings(
    base_url=settings.embeddings.base_url, normalize_embeddings=False, timeout=TIMEOUT
)

vectorstore: Final[VectorStore] = ...

retriever: Final[BaseRetriever] = ...

llm: Final[BaseChatModel] = GigaChat(
    credentials=settings.gigachat.apikey,
    scope=settings.gigachat.scope,
    model=settings.gigachat.model_name,
    profanity_check=False,
    verify_ssl_certs=False,
    timeout=TIMEOUT,
)


def get_connection_manager() -> ConnectionManager:
    return InMemoryConnectionManager()
