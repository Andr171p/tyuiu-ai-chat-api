from typing import Final

from faststream import FastStream, Logger
from faststream.rabbit import ExchangeType, RabbitBroker, RabbitExchange

from .database import add_messages
from .schemas import Message
from .settings import settings

broker: Final[RabbitBroker] = RabbitBroker(settings.rabbit.url)

message_exchange = RabbitExchange("message-exchange", type=ExchangeType.DIRECT)

faststream_app: Final[FastStream] = FastStream(broker)


@broker.subscriber("messages_persisting")
async def persist_messages(messages: list[Message], logger: Logger) -> None:
    await add_messages(messages)
    logger.info("Successfully persisted %s messages", len(messages))
