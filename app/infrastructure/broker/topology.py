"""Обменники и очереди сервиса.

Путь сообщения: payments -> payments.new. При ошибке обработчик кладёт его в
payments.retry, откуда по истечении TTL оно возвращается в payments.new.
После исчерпания попыток — в payments.dlq.
"""

from faststream.rabbit import ExchangeType, RabbitExchange, RabbitQueue

PAYMENTS_EXCHANGE_NAME = "payments"
DLX_EXCHANGE_NAME = "payments.dlx"

NEW_ROUTING_KEY = "payment.new"
RETRY_ROUTING_KEY = "payment.retry"
DEAD_ROUTING_KEY = "payment.dead"

payments_exchange = RabbitExchange(PAYMENTS_EXCHANGE_NAME, type=ExchangeType.DIRECT, durable=True)
dlx_exchange = RabbitExchange(DLX_EXCHANGE_NAME, type=ExchangeType.DIRECT, durable=True)

new_queue = RabbitQueue(
    "payments.new",
    durable=True,
    routing_key=NEW_ROUTING_KEY,
    arguments={
        # Страховка: отвергнутое сообщение уйдёт в DLQ, а не пропадёт.
        "x-dead-letter-exchange": DLX_EXCHANGE_NAME,
        "x-dead-letter-routing-key": DEAD_ROUTING_KEY,
    },
)

dlq_queue = RabbitQueue(
    "payments.dlq",
    durable=True,
    routing_key=DEAD_ROUTING_KEY,
)


# Задержку несёт само сообщение (expiration), поэтому TTL очереди — фиксированная
# страховка от сообщения без неё. Из настроек не выводится: иначе api и consumer
# с разными env объявили бы очередь по-разному и получили PRECONDITION_FAILED.
RETRY_QUEUE_TTL_MS = 24 * 60 * 60 * 1000

retry_queue = RabbitQueue(
    "payments.retry",
    durable=True,
    routing_key=RETRY_ROUTING_KEY,
    arguments={
        "x-message-ttl": RETRY_QUEUE_TTL_MS,
        "x-dead-letter-exchange": PAYMENTS_EXCHANGE_NAME,
        "x-dead-letter-routing-key": NEW_ROUTING_KEY,
    },
)
