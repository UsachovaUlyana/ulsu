# Отчёт по стеку использованных технологий

**Проект:** `ulsu` — микросервисный Dating Bot  
**Дата:** 18.05.2026  
**Основание:** `Критерии оценивания/Практика-Дэйтинг-Бот.docx`, `Критерии оценивания/Система оценивания.docx`

---

## 1. Введение

Проект реализован как микросервисная система на **Python 3.11+**, состоящая из 5 микросервисов и инфраструктурных компонентов, собранных в **Docker Compose**.

| Компонент | Технологии | Назначение |
|:----------|:-----------|:-----------|
| **Bot Service** | aiogram 3.x, aiohttp, redis.asyncio | Telegram-интерфейс, FSM, i18n (ru/en) |
| **Profile Service** | FastAPI, SQLAlchemy 2, MinIO | CRUD анкет, фото, предпочтения, рефералы |
| **Ranking Service** | FastAPI, SQLAlchemy, Redis, Celery | Рейтинги L1/L2/L3 + peer, лента, кэш |
| **Matching Service** | FastAPI, SQLAlchemy, aio-pika | Свайпы, мэтчи, peer reviews (оценки 1.0–5.0) |
| **Notification Service** | aio-pika, aiohttp | Уведомления о мэтчах/лайках/рефералах + icebreaker |

Настоящий отчёт разделяет технологии на две группы:
1. **Технологии по заданию** — прямо указанные в ТЗ практики или в системе оценивания.
2. **Дополнительно подключенные технологии** — выбранные командой для решения конкретных архитектурных задач, с обоснованием выбора.

---

## 2. Технологии по заданию

Все перечисленные технологии либо явно требуются в ТЗ (`Практика-Дэйтинг-Бот.docx`), либо указаны в критериях оценивания (`Система оценивания.docx`).

| № | Технология | Источник в ТЗ / критериях | Назначение в проекте |
|:-:|:-----------|:--------------------------|:---------------------|
| 1 | **Python 3.11+** | Подразумевается (разработка приложения) | Основной язык разработки всех микросервисов |
| 2 | **PostgreSQL 16** | «Создание схемы данных в БД» (Этап 1) | Основное реляционное хранилище (users, profiles, swipes, matches, ratings, referrals, peer_reviews, activity_log) |
| 3 | **Redis 7** | «Использование Redis для кэширования предварительно отранжированных списков анкет» | Кэш ленты (ZSET + JSON + TTL 30 мин), FSM storage бота (aiogram `RedisStorage`), брокер и backend Celery (`redis://redis:6379/1` и `/2`) |
| 4 | **Celery 5.3+** | «Хранение рейтингов в отдельной таблице с регулярными пересчетами через Celery», «Настройка отложенных задач через Celery» (Этап 4) | Периодический пересчёт рейтингов: L2 каждые 15 мин, L3 каждый час, peer score по расписанию; реактивные задачи на событиях |
| 5 | **RabbitMQ 3.12** | «Применение Apache Kafka/RabbitMQ/любой другой mq, для потоковой обработки событий взаимодействия с анкетами и общения сервисов» | Межсервисная шина событий: 5 exchange (swipe_events, match_events, profile_events, referral_events, review_events), publisher/consumer на 4 сервисах |
| 6 | **MinIO (S3)** | «Использование S3 хранилища для изображений. (пример: Minio)» | S3-совместимое хранилище фотографий пользователей, presigned URL для просмотра в Telegram, удаление объектов при удалении пользователя |
| 7 | **Telegram Bot API** | «интеграция с Telegram Bot API», «берем id телеграма юзера при /start команде» (Этап 2) | Интерфейс взаимодействия с пользователем: команды, callback'и, отправка фото-каруселей, уведомления |
| 8 | **Docker + Docker Compose** | «Деплой на сервер или разворачиваем локально и на зачете показываем» (Этап 4) | Контейнеризация 5 микросервисов + 6 инфраструктурных сервисов + Celery Worker/Beat, оркестрация через `docker-compose.yml` |
| 9 | **GitHub Actions (CI/CD)** | Критерий оценивания №7 «CI/CD для бота» | Pipeline: lint (Ruff) → tests (pytest) → docker build для каждого сервиса на push/PR |
| 10 | **Prometheus + Grafana** | «Применение метрик в любых местах приложения, логирование» | Сбор метрик (counters, histograms) со всех FastAPI-сервисов + визуализация в дашбордах |
| 11 | **Логирование** | «логирование» (в паре с метриками) | Структурное JSON-логирование во всех сервисах через единый форматтер |

> **Примечание:** Redis используется **не только** как брокер Celery (что давало бы 1 балл), а как полноценный кэш ленты и FSM-storage — в точном соответствии с требованием ТЗ о кэшировании предварительно отранжированных списков.

---

## 3. Дополнительно подключенные технологии

Нижеперечисленные технологии **не были прямо указаны** в ТЗ практики, но были выбраны для решения конкретных архитектурных и инженерных задач. Для каждой приведено обоснование: почему именно она, а не альтернатива.

### 3.1. Фреймворки и runtime

#### FastAPI 0.115+
- **Назначение:** REST API для Profile Service, Ranking Service, Matching Service.
- **Обоснование:**
  - **Async-first (ASGI)** — все endpoint'ы работают асинхронно, что критично для IO-bound нагрузки (БД, HTTP, MQ).
  - **Автогенерация OpenAPI/Swagger** — документация API формируется из кода без дополнительных усилий.
  - **Встроенная валидация через Pydantic** — type-safe request/response модели с автоматической сериализацией.
  - **Высокая производительность** — один из самых быстрых Python-фреймворков (бенчмарки TechEmpower).
- **Почему не Flask/Django:** Flask синхронен по умолчанию (требует обёрток для async); Django монолитен и тяжеловат для микросервисной архитектуры.

#### aiogram 3.x
- **Назначение:** Telegram Bot — обработка команд, FSM, middleware, i18n.
- **Обоснование:**
  - **Официальный async фреймворк** для Telegram Bot API, развивается командой, близкой к Telegram.
  - **FSM (Finite State Machine)** — встроенная машина состояний для пошаговой регистрации (`registration.py`) и оценки мэтчей (`RatePeer`).
  - **Middleware-архитектура** — позволяет внедрить `AlbumMiddleware` (приём нескольких фото за раз), i18n-middleware, логирование.
  - **Поддержка media groups** — нативная отправка каруселей фото через `InputMediaPhoto`.
- **Почему не python-telegram-bot:** PTB v20+ тоже async, но aiogram 3.x имеет более удобный API для FSM и middleware, а также лучшую документацию для сложных сценариев.

#### uvicorn 0.34+
- **Назначение:** ASGI-сервер для запуска FastAPI-приложений.
- **Обоснование:** Стандартный production-ready ASGI-сервер, поддерживает HTTP/1.1 и WebSocket. Интегрирован с FastAPI «из коробки». Альтернатива hypericorn — менее распространён.

---

### 3.2. База данных и ORM

#### SQLAlchemy 2.0+
- **Назначение:** ORM для всех сервисов, работающих с PostgreSQL.
- **Обоснование:**
  - **Стандарт де-факто** в Python-экосистеме — самая зрелая ORM, огромное сообщество.
  - **Полная поддержка async** через `sqlalchemy[asyncio]` — критично для микросервисов на FastAPI.
  - **Типизированные модели** — модели объявляются через классы с type hints, IDE подсказывает поля.
  - **Мощный query builder** — сложные запросы (JOIN ratings + peer_reviews, window functions) пишутся декларативно.
- **Почему не Tortoise ORM:** Меньшая экосистема, сложнее интеграция с Alembic, менее зрелая документация для продвинутых сценариев.

#### Alembic 1.14+
- **Назначение:** Миграции схемы БД.
- **Обоснование:** Официальный инструмент миграций для SQLAlchemy. Поддержка autogenerate (генерация миграций по diff моделей), downgrade (откат), branching (ветвление миграций). В проекте используется для 5 миграций (`0001_init_schema` → `0005_peer_review_score_decimal`).

#### asyncpg 0.30+
- **Назначение:** Async драйвер PostgreSQL.
- **Обоснование:** Необходим для работы async SQLAlchemy 2.0. Является самым производительным async драйвером для PostgreSQL в Python (написан на Cython, поддерживает prepared statements, pipeline mode).

#### psycopg2-binary 2.9+
- **Назначение:** Sync драйвер PostgreSQL.
- **Обоснование:** Используется там, где async невозможен или не нужен: Alembic (команда `alembic upgrade`) и Celery Worker/Beat (Celery не поддерживает async tasks из коробки).

---

### 3.3. Брокер сообщений и HTTP-клиент

#### aio-pika 9.5+
- **Назначение:** Async клиент RabbitMQ для publisher'ов и consumer'ов.
- **Обоснование:**
  - **Native asyncio** — весь API async/await, без callback-адаптеров.
  - **High-level API** — удобные абстракции `connect`, `channel`, `exchange`, `queue`.
  - **Автоматические reconnect'ы** — при разрыве соединения с RabbitMQ клиент переподключается сам.
- **Почему не pika:** Pika — низкоуровневый sync-клиент, для async требует обёрток и имеет проблемы с reconnect'ами.

#### aiohttp 3.11+
- **Назначение:** HTTP-клиент для межсервисного взаимодействия (Bot → Profile/Ranking) и Telegram Bot API (notification service).
- **Обоснование:**
  - **Async-first** — не блокирует event loop при запросах.
  - **Session pooling** — reusable TCP-соединения снижают overhead.
  - **Интеграция с aiogram** — aiogram 3.x использует aiohttp под капотом.

---

### 3.4. Хранилище и кэш

#### MinIO Python SDK (minio 7.2+)
- **Назначение:** Клиент для S3-совместимого хранилища фотографий.
- **Обоснование:** Официальный Python SDK для MinIO. Поддержка presigned URL (временные ссылки для просмотра фото в Telegram), multipart upload, удаление объектов. Альтернатива boto3 — тяжелее и ориентирован на AWS.

#### redis-py 5.2+
- **Назначение:** Клиент Redis.
- **Обоснование:** Официальный клиент, поддержка async (`redis.asyncio`), типизированные команды. Используется для FSM storage aiogram (`RedisStorage`) и кэша ленты (`ZSET` операции).

---

### 3.5. Конфигурация и валидация

#### Pydantic 2.10+
- **Назначение:** Валидация входящих данных, сериализация response моделей.
- **Обоснование:**
  - **Интеграция с FastAPI** — Pydantic-модели используются для request/response схем «из коробки».
  - **Type safety** — валидация на старте, а не в runtime.
  - **Производительность** — Pydantic v2 переписан на Rust (pydantic-core), валидация в 5-50x быстрее v1.

#### pydantic-settings 2.7+
- **Назначение:** Загрузка конфигурации из переменных окружения и `.env` файлов.
- **Обоснование:** Стандартный способ управления настройками в Pydantic v2. Валидация типов при старте приложения (например, `DATABASE_URL` должен быть валидным URL). Поддержка `.env` файлов через `python-dotenv`.

---

### 3.6. Мониторинг и логирование

#### structlog 24.4+
- **Назначение:** Структурное JSON-логирование во всех сервисах.
- **Обоснование:**
  - В распределённой системе plaintext-логи неэффективны — невозможно фильтровать и агрегировать.
  - **Единый JSON-формат** — каждый лог содержит поля `timestamp`, `level`, `logger`, `event`, плюс произвольный контекст (`user_id`, `telegram_id`, `action`).
  - **Совместимость** — JSON-логи можно напрямую отправлять в ELK Stack или Grafana Loki без парсеров.
- **Почему не стандартный logging:** Стандартный `logging` требует ручного форматирования JSON через `python-json-logger`, structlog даёт это из коробки с более удобным API.

#### prometheus-client 0.21+
- **Назначение:** Экспозиция метрик в формате Prometheus.
- **Обоснование:** Де-факто стандарт для Python-приложений. Совместим с Prometheus scrape (`/metrics` endpoint). Поддержка Counter, Histogram, Gauge.

#### prometheus-fastapi-instrumentator 7.0+
- **Назначение:** Автоматическая инструментация FastAPI.
- **Обоснование:** Из коробки собирает `http_request_duration_seconds` (latency histograms) и `http_requests_total` (counter по status code и endpoint) без ручного boilerplate. Экономит десятки строк кода на сервис.

---

### 3.7. NLP / Semantic Matching

#### gensim 4.3+
- **Назначение:** Построение embedding'ов для интересов пользователей (semantic interest boost).
- **Обоснование:** Лёгкая библиотека для NLP без тяжёлых ML-фреймворков (PyTorch/TensorFlow). Позволяет получить векторное представление слов через word2vec/fastText. В проекте используется для вычисления cosine similarity между наборами интересов пользователя и кандидата.

#### numpy 1.24+
- **Назначение:** Векторные операции для semantic matching.
- **Обоснование:** Необходим для эффективного вычисления cosine similarity между векторами интересов. Все векторные операции в `embeddings.py` реализованы через numpy arrays.

#### pymorphy3 + pymorphy3-dicts-ru 2.0+
- **Назначение:** Лемматизация русских слов (приведение интересов к нормальной форме).
- **Обоснование:**
  - Пользователи вводят интересы в разных формах («путешествия», «путешествовать», «путешествиям»).
  - pymorphy3 приводит слова к нормальной форме (лемме) перед построением embedding'ов.
  - Это **повышает качество semantic matching** — пересечение интересов находится точнее.
- **Почему не pymorphy2:** pymorphy3 — актуальная версия с обновлёнными словарями и поддержкой Python 3.11+.

---

### 3.8. Тестирование и качество кода

#### pytest
- **Назначение:** Фреймворк для юнит- и интеграционных тестов.
- **Обоснование:** Стандарт для Python-экосистемы. Богатая экосистема плагинов (`pytest-asyncio` для async тестов, `pytest-cov` для покрытия). Используется в GitHub Actions CI для всех 5 сервисов.

#### Ruff
- **Назначение:** Линтер и форматировщик кода.
- **Обоснование:**
  - Заменяет **flake8 + black + isort** в одном инструменте.
  - Написан на **Rust** — работает в 10-100x быстрее аналогов.
  - Это критично для CI: pipeline проходит за секунды вместо минут.
  - Поддержка правил из flake8, pydocstyle, pyupgrade и многих других.

---

### 3.9. Прочее

#### python-multipart 0.0.18+
- **Назначение:** Парсинг multipart/form-data.
- **Обоснование:** Необходимость для FastAPI при загрузке фотографий через HTTP POST (`UploadFile`). FastAPI использует python-multipart под капотом.

#### Celery Beat
- **Назначение:** Планировщик периодических задач.
- **Обоснование:** Встроен в Celery, не требует отдельного cron-демона. Расписание задач описывается в Python-коде (`celery_app.py`), что упрощает версионирование и деплой. В проекте: L2 каждые 15 мин, L3 каждый час.

---

## 4. Сводная таблица стека

| Категория | Технология | Тип | Назначение |
|:----------|:-----------|:---:|:-----------|
| Язык | Python 3.11+ | Задание | Основной язык разработки |
| База данных | PostgreSQL 16 | Задание | Реляционное хранилище |
| ORM | SQLAlchemy 2.0 | Доп | Работа с БД декларативно |
| Миграции | Alembic 1.14 | Доп | Миграции схемы БД |
| Драйвер БД | asyncpg 0.30 | Доп | Async драйвер PostgreSQL |
| Драйвер БД | psycopg2-binary 2.9 | Доп | Sync драйвер (Celery, Alembic CLI) |
| Кэш | Redis 7 | Задание | Кэш ленты, FSM, брокер Celery |
| Клиент Redis | redis-py 5.2 | Доп | Python-клиент для Redis |
| MQ брокер | RabbitMQ 3.12 | Задание | Межсервисная шина событий |
| Клиент MQ | aio-pika 9.5 | Доп | Async клиент RabbitMQ |
| Фоновые задачи | Celery 5.3+ | Задание | Пересчёт рейтингов |
| Планировщик | Celery Beat | Доп | Расписание периодических задач |
| S3 хранилище | MinIO | Задание | Хранение фото |
| Клиент S3 | minio 7.2 | Доп | Python SDK для MinIO |
| REST API | FastAPI 0.115 | Доп | HTTP API 4 сервисов |
| ASGI сервер | uvicorn 0.34 | Доп | Запуск FastAPI |
| Telegram | aiogram 3.x | Доп | Фреймворк для бота |
| HTTP клиент | aiohttp 3.11 | Доп | Межсервисные запросы |
| Валидация | Pydantic 2.10 | Доп | Валидация данных |
| Конфиги | pydantic-settings 2.7 | Доп | Загрузка настроек из env |
| Логирование | structlog 24.4 | Доп | Структурные JSON-логи |
| Метрики | prometheus-client 0.21 | Доп | Экспозиция метрик |
| Инструментация | prometheus-fastapi-instrumentator 7.0 | Доп | Авто-сбор метрик FastAPI |
| Визуализация | Grafana | Задание | Дашборды метрик |
| Сбор метрик | Prometheus | Задание | Хранение временных рядов |
| NLP | gensim 4.3 | Доп | Embedding'и интересов |
| NLP | numpy 1.24 | Доп | Векторные операции |
| NLP | pymorphy3 + dicts-ru | Доп | Лемматизация русских слов |
| Тестирование | pytest | Доп | Юнит- и интеграционные тесты |
| Линтинг | Ruff | Доп | Линтер + форматировщик |
| Upload | python-multipart | Доп | Загрузка файлов в FastAPI |
| CI/CD | GitHub Actions | Задание | Автотесты + сборка Docker |
| Контейнеризация | Docker + Compose | Задание | Деплой и оркестрация |
| Telegram API | Telegram Bot API | Задание | Интерфейс пользователя |

---

## 5. Сводная таблица дополнительного функционала

| Фича | Технологии / Паттерны | Ключевые файлы | Зачем добавлено |
|:-----|:----------------------|:---------------|:----------------|
| **Peer Reviews** | PostgreSQL `ON CONFLICT`, `Numeric(2,1)`, Bayesian smoothing, Celery | `matching-service/routes.py`, `ranking-service/formulas.py` | Доверие к рейтингу через оценки реальных пользователей |
| **Semantic Interest Boost** | gensim, numpy, cosine similarity, pymorphy3 | `ranking-service/embeddings.py`, `bot-service/embeddings.py` | Лучшее качество ленты по общим интересам |
| **i18n (ru/en)** | aiogram middleware, JSON-словари, dynamic keyboards | `bot-service/i18n.py`, `locales/*.json` | Расширение аудитории за пределы ru |
| **Icebreaker** | Шаблонный engine, Prometheus counter | `notification-service/icebreaker.py` | Снижение порога входа в диалог |
| **Like Notifications** | RabbitMQ `like.received`, aio-pika, aiohttp | `matching-service/consumer.py`, `notification-service/consumer.py` | Повышение engagement |
| **Referral Notifications** | RabbitMQ `referral_events` | `profile-service/routes.py`, `notification-service/consumer.py` | Вирусный рост через рефералов |
| **Circuit Breaker** | Паттерн CB (CLOSED/OPEN/HALF_OPEN), exponential backoff | `_shared/circuit_breaker.py`, `bot-service/api_client.py` | Защита от каскадных отказов |
| **Photo Proxy / Media Group** | aiogram `InputMediaPhoto`, `BufferedInputFile` | `bot-service/photo_proxy.py`, `bot-service/handlers/menu.py` | Нативный UX — карусель фото |
| **Album Middleware** | aiogram middleware, album grouping | `bot-service/middlewares.py` | Быстрая загрузка 5 фото за раз |
| **Инвалидация кэша при review** | Celery delayed task, Redis `DEL feed:*` | `ranking-service/tasks.py`, `ranking-service/consumers.py` | Консистентность рейтингов в ленте |
| **Likes Feed** | FastAPI, SQL window functions, asyncio gather, FSM | `matching-service/routes.py`, `bot-service/handlers/menu.py` | Просмотр полученных лайков |

---

## 6. Дополнительный функционал — детальный разбор

Ниже приведён подробный разбор каждой из 11 фич, выходящих за рамки базового ТЗ. Для каждой фичи указаны: суть, использованные технологии/паттерны, ключевые файлы и обоснование добавления.

---

| Фича | Технологии / Паттерны | Ключевые файлы | Обоснование |
|:-----|:----------------------|:---------------|:------------|
| **Peer Reviews**<br>Оценка мэтчей 1.0–5.0 (шаг 0.1), Bayesian smoothing | PostgreSQL `ON CONFLICT DO UPDATE`, `Numeric(2,1)`<br>Bayesian smoothing (prior mean = 3.0, prior weight = 5.0)<br>Celery delayed task | `matching-service/routes.py`<br>`ranking-service/formulas.py`<br>`ranking-service/tasks.py`<br>`profile-service/migrations/0005_peer_review_score_decimal.py` | Социальное доказательство в рейтинге. Алгоритмический L1/L2 не отражает реальное качество коммуникации. Bayesian smoothing защищает от шума при малом числе оценок. |
| **Semantic Interest Boost**<br>Cosine similarity для пересечения интересов | gensim (word2vec/fastText embeddings)<br>numpy (векторные операции)<br>pymorphy3 (лемматизация)<br>Redis ZSET (буст в кэше ленты) | `ranking-service/embeddings.py`<br>`ranking-service/feed_service.py`<br>`bot-service/embeddings.py`<br>`bot-service/handlers/menu.py` | Пользователи с общими интересами чаще находят темы для разговора. Алгоритмическая выдача по рейтингу игнорирует семантику — semantic boost добавляет этот слой. |
| **i18n (ru/en)**<br>Полная многоязычность | aiogram middleware<br>JSON-словари (`locales/ru.json`, `locales/en.json`)<br>Dynamic keyboard generation<br>FSM persistence в Redis | `bot-service/i18n.py`<br>`bot-service/i18n_middleware.py`<br>`locales/*.json`<br>`bot-service/handlers/registration.py`<br>`bot-service/keyboards.py` | Расширяет аудиторию за пределы ru. JSON-словари позволяют добавлять языки (de, es, fr) без пересборки бота. |
| **Icebreaker**<br>Шаблонные вопросы при мэтче | Шаблонный engine (~15 категорий)<br>Отделён от consumer'а (заменим на LLM)<br>Prometheus counter по категориям<br>RabbitMQ `match_events` | `notification-service/icebreaker.py`<br>`notification-service/consumer.py` | Снижает порог входа в диалог. Fallback-вопросы работают без общих интересов. Отделение engine от consumer'а позволит заменить шаблоны на LLM за 1 день. |
| **Like Notifications**<br>Уведомление о одностороннем лайке | RabbitMQ `like.received`<br>aio-pika (async consumer)<br>aiohttp (Telegram Bot API) | `matching-service/consumer.py`<br>`notification-service/consumer.py`<br>`notification-service/telegram_client.py` | Повышает engagement — получивший лайк чаще возвращается в бот, увеличивая количество свайпов и мэтчей. |
| **Referral Notifications**<br>Уведомление пригласившему | RabbitMQ `referral_events`<br>Event-driven architecture<br>PostgreSQL (`referrals` таблица) | `profile-service/routes.py`<br>`profile-service/events_publisher.py`<br>`notification-service/consumer.py` | Стимулирует вирусный рост. Пользователь видит immediate feedback (уведомление + бонус к рейтингу) и мотивирован приглашать друзей. |
| **Circuit Breaker**<br>Защита от каскадных отказов | Паттерн CB: CLOSED → OPEN → HALF_OPEN<br>Exponential backoff<br>State machine (счётчик ошибок) | `_shared/circuit_breaker.py`<br>`bot-service/api_client.py`<br>`bot-service/handlers/menu.py` | Предотвращает «лавину» ошибок при падении downstream-сервиса. Пользователь получает понятное fallback-сообщение вместо зависшего бота. |
| **Photo Proxy / Media Group**<br>Карусель из 5 фото | aiogram `InputMediaPhoto`<br>`BufferedInputFile` (без сохранения на диск)<br>aiohttp (скачивание)<br>MinIO presigned URL | `bot-service/photo_proxy.py`<br>`bot-service/handlers/menu.py` | Нативный UX Telegram — карусель выглядит профессионально, занимает меньше места, чем 5 отдельных сообщений. Фото не сохраняются локально. |
| **Album Middleware**<br>Приём нескольких фото за раз | aiogram middleware<br>Message grouping по `media_group_id` | `bot-service/middlewares.py` | Ускоряет регистрацию в 5x — пользователь отправляет альбом из галереи одним действием вместо 5 отдельных отправок. Критично для retention на onboarding. |
| **Инвалидация кэша при review**<br>Мгновенный пересчёт + сброс Redis | Celery delayed task (`recalc_after_review_event`)<br>Redis `DEL feed:*`<br>RabbitMQ `review_events` | `ranking-service/tasks.py`<br>`ranking-service/consumers.py` | Гарантирует консистентность — новые рейтинги сразу отражаются в ленте. Без инвалидации пользователь видел бы устаревшие данные до истечения TTL (30 мин). |
| **Likes Feed**<br>Лента тех, кто тебя лайкнул | FastAPI endpoint<br>SQL window functions (ORDER BY + LIMIT)<br>asyncio gather (параллельные запросы)<br>FSM (`LikesFeed.viewing`) | `matching-service/routes.py`<br>`bot-service/handlers/menu.py`<br>`bot-service/fsm.py` | Повышает engagement — пользователь видит, кто проявил интерес, и может быстро ответить взаимным лайком. Без фичи лайки остаются незамеченными. |

---

## 7. Вывод

Все технологии, **прямо указанные в задании**, полностью реализованы:
- ✅ Рейтинговая система L1/L2/L3 с пересчётами через Celery
- ✅ Redis для кэширования ленты (ZSET + TTL) и FSM
- ✅ RabbitMQ как полноценная межсервисная шина событий (не только для Celery)
- ✅ MinIO (S3) для хранения фотографий
- ✅ Prometheus + Grafana для метрик и визуализации
- ✅ Структурное логирование
- ✅ GitHub Actions для CI
- ✅ Docker Compose для деплоя

**Дополнительно подключенные технологии** выбраны для решения конкретных инженерных задач:
- **FastAPI + SQLAlchemy 2.0 + asyncpg** — обеспечивают высокопроизводительный async стек для микросервисов.
- **aiogram 3.x** — даёт современный Telegram-интерфейс с FSM и middleware.
- **aio-pika + aiohttp** — закрывают потребность в async коммуникациях (MQ и HTTP).
- **Pydantic + pydantic-settings** — гарантируют type safety и валидацию конфигурации.
- **structlog + prometheus-client** — обеспечивают наблюдаемость распределённой системы.
- **gensim + numpy + pymorphy3** — реализуют semantic interest boost для улучшения качества ленты.
- **Ruff** — ускоряет CI pipeline в 10-100x.

**Дополнительный функционал (11 фич)** выходит за рамки базового ТЗ и добавлен для улучшения пользовательского опыта, надёжности системы и вирусного роста:
- **Peer Reviews + Bayesian smoothing** — социальное доказательство в рейтинге.
- **Semantic Interest Boost** — умная лента по общим интересам.
- **i18n (ru/en)** — многоязычность без пересборки.
- **Icebreaker** — снижение порога входа в диалог.
- **Like / Referral Notifications** — повышение engagement и вирусности.
- **Circuit Breaker** — защита от каскадных отказов.
- **Photo Proxy + Album Middleware** — нативный UX Telegram и быстрая регистрация.
- **Инвалидация кэша** — консистентность данных.
- **Likes Feed** — просмотр полученных лайков.

Все дополнительные технологии и фичи имеют чёткое обоснование, решают конкретную задачу и не являются избыточными при текущей архитектуре.
