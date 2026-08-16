# Сервис процессинга платежей

Асинхронная обработка платежей: API принимает запрос, событие уходит в RabbitMQ
через outbox, consumer проводит платёж через эмулятор шлюза и уведомляет клиента
вебхуком.

## Стек

FastAPI, Pydantic v2, SQLAlchemy 2.0 (async), PostgreSQL, RabbitMQ (FastStream),
Alembic, Docker Compose.

## Запуск

```bash
cp .env.example .env
docker compose up -d --build
```

Поднимутся пять сервисов: `postgres`, `rabbitmq`, `migrate` (одноразовый,
накатывает миграции), `api` и `consumer`.

- API — http://localhost:8000, документация http://localhost:8000/docs
- RabbitMQ UI — http://localhost:15672 (guest / guest)

Остановить с удалением данных: `docker compose down -v`.

## API

Все эндпоинты требуют заголовок `X-API-Key` (значение из `API_KEY`).

### Создание платежа

```bash
curl -X POST http://localhost:8000/api/v1/payments \
  -H 'X-API-Key: local-dev-api-key' \
  -H 'Idempotency-Key: order-42' \
  -H 'Content-Type: application/json' \
  -d '{
    "amount": "1500.00",
    "currency": "RUB",
    "description": "Оплата заказа №42",
    "metadata": {"order_id": 42},
    "webhook_url": "https://example.com/hook"
  }'
```

```json
{
  "payment_id": "f3dc65ff-bc90-46e9-b8c9-3931a8bfcf17",
  "status": "pending",
  "created_at": "2026-08-15T15:59:17.842180Z"
}
```

Валюты: `RUB`, `USD`, `EUR`. Сумма — строка с двумя знаками после запятой.

### Получение платежа

```bash
curl http://localhost:8000/api/v1/payments/{payment_id} \
  -H 'X-API-Key: local-dev-api-key'
```

### Коды ответов

| Код | Когда |
|-----|-------|
| 202 | Платёж принят в обработку |
| 200 | Платёж найден |
| 401 | Нет заголовка `X-API-Key` или он неверный |
| 404 | Платёж не найден |
| 409 | `Idempotency-Key` уже использован с другим телом запроса |
| 422 | Тело запроса не прошло валидацию |

### Уведомление

После обработки на `webhook_url` уходит POST:

```json
{
  "payment_id": "f3dc65ff-bc90-46e9-b8c9-3931a8bfcf17",
  "status": "succeeded",
  "amount": "1500.00",
  "currency": "RUB",
  "description": "Оплата заказа №42",
  "metadata": {"order_id": 42},
  "created_at": "2026-08-15T15:59:17.842180+00:00",
  "processed_at": "2026-08-15T15:59:21.115408+00:00"
}
```

## Архитектура

```
app/
  domain/          доменные сущности и правила, без внешних зависимостей
  application/     юзкейсы и порты (репозитории, шлюз, отправка вебхуков)
  infrastructure/  SQLAlchemy, RabbitMQ, httpx, настройки
  presentation/    HTTP API и consumer
```

Зависимости направлены внутрь: `presentation` и `infrastructure` знают про
`application` и `domain`, обратной связи нет.

### Путь платежа

1. `POST /api/v1/payments` — платёж и событие `payment.created` пишутся в
   таблицы `payments` и `outbox` **одной транзакцией**.
2. Outbox relay (фоновая задача в процессе API) выбирает неопубликованные
   события через `FOR UPDATE SKIP LOCKED` и публикует их в обменник `payments`.
3. Consumer читает `payments.new`, проводит платёж через эмулятор шлюза
   (2–5 секунд, 90% успеха), проставляет статус и отправляет вебхук.

### Очереди

```
payments ──payment.new──► payments.new ──отказ──► payments.dlx ──payment.dead──► payments.dlq
                              ▲                        │
                              └──TTL истёк──── payments.retry ◄──payment.retry──┘
```

## Гарантии

**Outbox.** Событие сохраняется в той же транзакции, что и платёж, поэтому
недоступность брокера не теряет событий и не мешает принимать запросы: API
продолжает отвечать 202, а relay доставит накопленное после восстановления.

**Идемпотентность на входе.** Уникальный индекс по `idempotency_key` плюс
проверка до вставки. Повтор с тем же телом возвращает тот же `payment_id` и не
создаёт второго события; с другим телом — 409. Гонка параллельных запросов
разрешается на уровне БД: нарушение уникальности перехватывается и запрос
получает платёж победителя.

**Идемпотентность на выходе.** Доставка at-least-once, поэтому обработчик может
получить сообщение дважды. Повторно платёж не проводится — переход в финальный
статус разрешён только из `pending`, и на уровне БД, и в доменной сущности.
Уведомление при этом отправляется в любом случае: сообщение могло вернуться
именно из-за неудачной доставки вебхука.

**Повторы.** Два независимых механизма:

- отправка вебхука — 3 попытки внутри обработчика с экспоненциальной задержкой;
- обработка сообщения — при ошибке сообщение уходит в `payments.retry` с
  задержкой `RABBITMQ_RETRY_BASE_DELAY_SECONDS × 2^(попытка−1)`, откуда по
  истечении TTL возвращается в `payments.new`. Номер попытки едет в заголовке
  `x-attempt`.

**Dead Letter Queue.** После `RABBITMQ_MAX_DELIVERY_ATTEMPTS` неудачных попыток
сообщение публикуется в `payments.dlq` с заголовками `x-attempt` и `x-error`.

## Переменные окружения

Полный список с значениями по умолчанию — в `.env.example`. Основное:

| Переменная | По умолчанию | Назначение |
|------------|--------------|------------|
| `LOG_LEVEL` | `INFO` | Уровень логов приложения |
| `API_KEY` | `local-dev-api-key` | Ключ для заголовка `X-API-Key` |
| `POSTGRES_*` | | Подключение к БД |
| `RABBITMQ_*` | | Подключение к брокеру |
| `RABBITMQ_MAX_DELIVERY_ATTEMPTS` | `3` | Попыток обработки до DLQ |
| `RABBITMQ_RETRY_BASE_DELAY_SECONDS` | `5.0` | База экспоненциальной задержки |
| `OUTBOX_BATCH_SIZE` | `100` | Событий за один проход relay |
| `OUTBOX_POLL_INTERVAL_SECONDS` | `1.0` | Пауза, когда публиковать нечего |
| `WEBHOOK_MAX_ATTEMPTS` | `3` | Попыток доставки уведомления |
| `GATEWAY_MIN_DELAY_SECONDS` | `2.0` | Нижняя граница задержки шлюза |
| `GATEWAY_MAX_DELAY_SECONDS` | `5.0` | Верхняя граница задержки шлюза |
| `GATEWAY_SUCCESS_RATE` | `0.9` | Доля успешных платежей |

## Разработка

```bash
poetry install
poetry run pytest
poetry run ruff check app tests
poetry run black app tests
poetry run pre-commit install
```

Тесты юнитовые, БД и брокер им не нужны.

Инфраструктуру для ручной проверки удобно поднять из того же compose:

```bash
docker compose up -d postgres rabbitmq
POSTGRES_HOST=localhost poetry run alembic upgrade head
POSTGRES_HOST=localhost RABBITMQ_HOST=localhost \
  poetry run uvicorn app.presentation.api.main:app --reload
POSTGRES_HOST=localhost RABBITMQ_HOST=localhost \
  poetry run faststream run app.presentation.consumer.main:app
```

### Миграции

```bash
poetry run alembic revision --autogenerate -m "описание"
poetry run alembic upgrade head
poetry run alembic check   # расхождения моделей и схемы
```
