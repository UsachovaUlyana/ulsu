# Описание сервисов Dating Bot

## Обзор

Система построена на **микросервисной архитектуре**. Сервисы общаются между собой через брокер сообщений (RabbitMQ) и REST API. Каждый сервис выполняет свою чётко определённую задачу.

```mermaid
graph LR
    BOT["🤖 Bot Service"]
    PROF["👤 Profile Service"]
    RANK["📊 Ranking Service"]
    MATCH["💘 Matching Service"]
    NOTIFY["🔔 Notification Service"]

    BOT -->|REST API| PROF
    BOT -->|REST API| RANK
    BOT -->|RabbitMQ| MATCH
    MATCH -->|RabbitMQ| NOTIFY
    MATCH -->|RabbitMQ| RANK
    PROF -->|RabbitMQ| RANK

    style BOT fill:#5b9bd5,color:#fff,stroke:#4178a4
    style PROF fill:#70ad47,color:#fff,stroke:#548235
    style RANK fill:#ed7d31,color:#fff,stroke:#c45d1a
    style MATCH fill:#e84d8a,color:#fff,stroke:#c43070
    style NOTIFY fill:#a855f7,color:#fff,stroke:#8b3fd4
```

> **Сплошная линия** — синхронный REST API &nbsp;|&nbsp; **Пунктирная линия** — асинхронный обмен через RabbitMQ

---

## 1. 🤖 Telegram Bot Service (`bot-service`)

| | |
|:--|:--|
| **Назначение** | Интерфейс пользователя. Принимает команды из Telegram, отображает анкеты, обрабатывает свайпы, уведомляет о мэтчах, управляет фильтрами и оценками |
| **Технологии** | Python, aiogram 3.x, aiohttp, aio-pika, redis.asyncio |
| **Порт** | — (polling Telegram API) |

### Основные функции

- 🚀 Обработка `/start` — регистрация пользователя, deep-link реферальные коды (`?start=ref_...`)
- 🌐 **Многоязычность** (i18n) — переключение между `ru` и `en` через `/lang` или inline-кнопки
- 📝 Заполнение анкеты через **пошаговый диалог (FSM)**:
  - Имя, возраст, пол, город, описание, интересы
  - Загрузка фотографий (1–5 штук, поддержка media group / album middleware)
  - Настройка предпочтений: пол, возрастной диапазон, **город поиска** (`search_city` — свой / любой / произвольный)
- 👀 **Просмотр анкет** — показ карточек с фото-каруселью (media group), рейтингом и совместимостью
- 💕 **Свайп-механика** — кнопки `❤️ Лайк` / `👎 Пропустить` / `⏹️ Стоп`
- 💘 **Лента лайков** — просмотр пользователей, которые лайкнули тебя, с возможностью ответного свайпа
- ⭐ **Оценка мэтчей** (peer rating) — после мэтча можно оценить пользователя 1.0–5.0 (шаг 0.1)
- 🔗 Реферальная система — автоприменение реферального кода при регистрации
- ✏️ **Управление профилем** — просмотр своей анкеты с рейтингом, удаление аккаунта
- 🛡️ **Circuit Breaker** — защита от каскадных отказов при недоступности Profile / Ranking сервисов
- 📸 **Photo Proxy** — скачивание фото из MinIO и отправка в Telegram как `InputMediaPhoto` / `InputFile` для нативной карусели

### Взаимодействие

```mermaid
graph LR
    TG["☁️ Telegram API"]
    BOT["🤖 Bot Service"]
    PROF["👤 Profile Service"]
    RANK["📊 Ranking Service"]
    RMQ["🐇 RabbitMQ"]

    TG <-->|"Long Polling"| BOT
    BOT -->|"CRUD анкет,<br/>загрузка фото"| PROF
    BOT -->|"Получение<br/>ленты анкет"| RANK
    BOT -->|"Отправка<br/>свайпов"| RMQ

    style BOT fill:#5b9bd5,color:#fff
```

---

## 2. 👤 Profile Service (`profile-service`)

| | |
|:--|:--|
| **Назначение** | Управление профилями пользователей. Хранение анкет, фотографий, предпочтений. CRUD-операции. Публикация событий |
| **Технологии** | Python, FastAPI, SQLAlchemy 2.0, PostgreSQL, MinIO (S3), aio-pika |
| **Порт** | `8001` |

### Основные функции

- 📋 Регистрация пользователя по Telegram ID (идемпотентная — если пользователь уже есть, возвращает существующего)
- ✏️ Создание / обновление / получение / удаление анкеты
- 📷 Загрузка фотографий в S3-хранилище (MinIO), лимит 5 MB на файл
- 🔗 Генерация presigned URL для доступа к фото
- ⚙️ Управление предпочтениями поиска (включая `search_city`)
- 👥 Реферальная система — применение реферального кода (`/referrals/apply`)
- 🗑️ Каскадное удаление пользователя с очисткой фото из MinIO
- 📤 Публикация событий в RabbitMQ:
  - `profile_events` — при создании / обновлении / удалении профиля
  - `referral_events` — при успешном применении реферального кода

### API эндпоинты

| Метод | Эндпоинт | Описание |
|:------|:---------|:---------|
| `POST` | `/api/v1/users/` | Регистрация нового пользователя |
| `GET` | `/api/v1/users/{telegram_id}` | Полный профиль (user + profile + photos + preferences) |
| `PUT` | `/api/v1/users/{telegram_id}/profile` | Создание / обновление анкеты |
| `PUT` | `/api/v1/users/{telegram_id}/preferences` | Обновление предпочтений поиска |
| `POST` | `/api/v1/users/{telegram_id}/photos` | Загрузка фото (multipart/form-data) |
| `DELETE` | `/api/v1/users/{telegram_id}/photos/{photo_id}` | Удаление фото |
| `POST` | `/api/v1/referrals/apply` | Применение реферального кода |
| `DELETE` | `/api/v1/users/{telegram_id}` | Удаление пользователя и всех данных |
| `GET` | `/api/v1/health` | Health check |

### Взаимодействие

```mermaid
graph LR
    BOT["🤖 Bot Service"]
    PROF["👤 Profile Service"]
    PG[("🐘 PostgreSQL")]
    S3["📦 MinIO (S3)"]
    RMQ["🐇 RabbitMQ"]

    BOT -->|"REST API"| PROF
    PROF -->|"Данные профилей"| PG
    PROF -->|"Фотографии"| S3
    PROF -->|"profile_events<br/>referral_events"| RMQ

    style PROF fill:#70ad47,color:#fff
```

---

## 3. 📊 Ranking Service (`ranking-service`)

| | |
|:--|:--|
| **Назначение** | Расчёт рейтингов, формирование персонализированной ленты анкет, кэширование в Redis, Celery-задачи |
| **Технологии** | Python, FastAPI, SQLAlchemy, PostgreSQL, Redis, Celery, aio-pika |
| **Порт** | `8002` |

### Алгоритм рейтинга (3 уровня + peer)

```mermaid
graph TB
    subgraph L1["🟢 Уровень 1 — Первичный рейтинг"]
        A1["Полнота анкеты<br/>(заполненность полей)"]
        A2["Количество фото"]
        A3["Наличие предпочтений"]
    end

    subgraph L2["🟡 Уровень 2 — Поведенческий рейтинг"]
        B1["Полученные лайки / пропуски"]
        B2["Взаимные мэтчи"]
        B3["Начатые диалоги"]
        B4["Активность по часам<br/>(activity_log)"]
    end

    subgraph PEER["🟣 Peer Score"]
        P1["Оценки от мэтчей<br/>(peer_reviews)"]
        P2["Bayesian smoothing"]
    end

    subgraph L3["🔴 Уровень 3 — Комбинированный рейтинг"]
        C1["Взвешенная сумма<br/>primary + behavioral + peer + referral"]
    end

    L1 -->|"primary_score"| L3
    L2 -->|"behavioral_score"| L3
    PEER -->|"peer_score"| L3
    L3 -->|"combined_score"| FEED["📱 Лента анкет"]

    style L1 fill:#e8f5e9,stroke:#388e3c
    style L2 fill:#fff3e0,stroke:#f57c00
    style PEER fill:#f3e5f5,stroke:#7b1fa2
    style L3 fill:#fce4ec,stroke:#c62828
    style FEED fill:#e3f2fd,stroke:#1976d2
```

### Формирование ленты (Feed)

- **Кэш:** Redis ZSET с JSON-сериализованными объектами профилей (`feed:{user_id}`)
- **Miss path:** SQL-запрос с фильтрами (`target_gender`, `age_min`/`age_max`, `search_city`) + исключением уже просмотренных
- **Сортировка:** по `peer_count` (количество оценок) + семантическому overlap интересов (`semantic_interest_boost`)
- **TTL:** 30 минут, размер батча: 10 профилей
- **Compatibility:** семантический буст на основе пересечения интересов (cosine similarity над embedding'ами)

### Периодический пересчёт (Celery)

| Задача | Периодичность | Назначение |
|:-------|:--------------|:-----------|
| `recalc_primary_for_user` | Реактивно (на `profile_events`) | Первичный рейтинг |
| `recalc_behavioral_all` | Каждые **15 минут** | Поведенческий рейтинг по окну 14 дней |
| `recalc_combined_all` | Каждый **час** | Комбинированный рейтинг + инвалидация кэша |
| `recalc_peer_all` | По расписанию | Пересчёт peer score для всех пользователей |
| `recalc_after_review_event` | На событие `review_events` | Мгновенный пересчёт peer score после новой оценки |

### API эндпоинты

| Метод | Эндпоинт | Описание |
|:------|:---------|:---------|
| `GET` | `/api/v1/feed/{telegram_id}?exclude_telegram_id=` | Следующая анкета для показа |
| `GET` | `/api/v1/ratings/{telegram_id}` | Текущий рейтинг пользователя (primary, behavioral, peer, referral, combined) |
| `GET` | `/api/v1/health` | Health check |

### Консьюмеры RabbitMQ

| Exchange | Routing Key | Действие |
|:---------|:------------|:---------|
| `profile_events` | `profile.updated` | Пересчёт primary score |
| `swipe_events` | `swipe.created` | Учёт свайпа в behavioral score |
| `review_events` | `review.created` / `review.updated` | Мгновенный пересчёт peer + combined score |

### Взаимодействие

```mermaid
graph LR
    BOT["🤖 Bot Service"]
    RANK["📊 Ranking Service"]
    PG[("🐘 PostgreSQL")]
    REDIS[("⚡ Redis")]
    RMQ["🐇 RabbitMQ"]
    CELERY["⏰ Celery Workers"]

    BOT -->|"REST API"| RANK
    RANK -->|"Рейтинги"| PG
    RANK <-->|"Кэш ленты"| REDIS
    RMQ -->|"profile_events<br/>swipe_events<br/>review_events"| RANK
    CELERY -->|"Пересчёт"| RANK

    style RANK fill:#ed7d31,color:#fff
```

---

## 4. 💘 Matching Service (`matching-service`)

| | |
|:--|:--|
| **Назначение** | Обработка свайпов, определение мэтчей, ведение истории, **peer reviews**, список полученных лайков |
| **Технологии** | Python, FastAPI, SQLAlchemy, PostgreSQL, aio-pika |
| **Порт** | `8003` |

### Основные функции

- 📝 Запись свайпа (лайк / пропуск) в базу. Идемпотентность через `UNIQUE(swiper_id, target_id)`
- 💕 Проверка на взаимный лайк (мэтч). При мэтче — публикация `match_events`
- 📤 При одностороннем лайке — публикация `like.received` для уведомления
- 📖 Хранение истории просмотренных анкет
- 📋 Предоставление списка мэтчей и **полученных лайков** (с рейтингом и peer-оценками)
- ⭐ **Peer Reviews** — создание / обновление оценки мэтча (1.0–5.0, шаг 0.1). Публикация `review_events`
- 📊 Сводка peer-оценок пользователя (`/reviews/{telegram_id}/summary`)

### API эндпоинты

| Метод | Эндпоинт | Описание |
|:------|:---------|:---------|
| `GET` | `/api/v1/matches/{telegram_id}` | Список мэтчей пользователя |
| `GET` | `/api/v1/swipes/{telegram_id}/history` | История просмотренных анкет |
| `GET` | `/api/v1/likes/{telegram_id}` | Пользователи, которые лайкнули тебя (с `combined_score`, `peer_avg`, `peer_count`) |
| `POST` | `/api/v1/reviews` | Создать / обновить оценку мэтча |
| `GET` | `/api/v1/reviews/{telegram_id}/summary` | Средняя оценка и количество peer reviews |
| `GET` | `/api/v1/health` | Health check |

### Правила peer reviews

- Оценивать можно **только мэтчей** (проверка `SELECT FROM matches`)
- Одна оценка на пару (`reviewer_id`, `reviewee_id`) — upsert
- Диапазон: 1.0 – 5.0, шаг 0.1
- Запрещена самооценка

### Консьюмер RabbitMQ

| Exchange | Queue | Routing Key | Действие |
|:---------|:------|:------------|:---------|
| `swipe_events` | `matching.swipe_events` | `swipe.created` | Запись свайпа, проверка mutual like |

### Публикации в RabbitMQ

| Exchange | Routing Key | Триггер |
|:---------|:------------|:--------|
| `match_events` | `match.created` | Взаимный лайк |
| `swipe_events` | `like.received` | Односторонний лайк |
| `review_events` | `review.created` / `review.updated` | Новая / изменённая оценка |

### Взаимодействие

```mermaid
graph LR
    RMQ_IN["🐇 RabbitMQ<br/>(swipe_events)"]
    MATCH["💘 Matching Service"]
    PG[("🐘 PostgreSQL")]
    RMQ_OUT1["🐇 RabbitMQ<br/>(match_events)"]
    RMQ_OUT2["🐇 RabbitMQ<br/>(like.received)"]
    RMQ_OUT3["🐇 RabbitMQ<br/>(review_events)"]

    RMQ_IN -->|"Свайпы"| MATCH
    MATCH -->|"Свайпы, мэтчи,<br/>peer_reviews"| PG
    MATCH -->|"При мэтче"| RMQ_OUT1
    MATCH -->|"При лайке"| RMQ_OUT2
    MATCH -->|"При оценке"| RMQ_OUT3

    style MATCH fill:#e84d8a,color:#fff
```

---

## 5. 🔔 Notification Service (`notification-service`)

| | |
|:--|:--|
| **Назначение** | Отправка уведомлений пользователям через Telegram Bot API. Обрабатывает события из очереди |
| **Технологии** | Python, aio-pika, aiohttp |
| **Порт** | — (только консьюмеры очередей) |

### Основные функции

- 📥 Подписка на три типа событий:
  - **`match.created`** — уведомление обоим пользователям о мэтче
  - **`like.received`** — уведомление "Кому-то понравилась твоя анкета!"
  - **`referral.applied`** — уведомление пригласившему о новом реферале
- 💡 **Icebreaker** — при мэтче подбирает до 3 тем для разговора на основе общих интересов (шаблонный механизм, заменяемый на LLM в будущем)
- 👤 **Profile Client** — запрашивает профили обоих пользователей для формирования персонализированного сообщения
- 🔗 Добавляет `@username` в уведомление о мэтче для быстрого перехода в диалог
- 📊 Метрики: счётчики отправленных уведомлений по категориям

### Icebreaker — темы для разговора

Логика `pick_topics(interests_a, interests_b)`:
1. Находит пересечение интересов двух пользователей
2. Если есть общие интересы — выбирает случайную категорию и до 3 вопросов из шаблонов (`travel`, `music`, `sport`, `food`, `books`, `movies`, `games`, `art`, `tech`, `coffee`, `yoga`)
3. Если общих интересов нет — 3 случайных fallback-вопроса

### Консьюмеры RabbitMQ

| Exchange | Queue | Routing Key | Назначение |
|:---------|:------|:------------|:-----------|
| `match_events` | `notification.match_events` | `match.created` | Уведомление о мэтче + icebreaker |
| `swipe_events` | `notification.like_events` | `like.received` | Уведомление о лайке |
| `referral_events` | `notification.referral_events` | `referral.applied` | Уведомление о реферале |

### Взаимодействие

```mermaid
graph LR
    RMQ1["🐇 RabbitMQ<br/>(match_events)"]
    RMQ2["🐇 RabbitMQ<br/>(swipe_events)"]
    RMQ3["🐇 RabbitMQ<br/>(referral_events)"]
    NOTIFY["🔔 Notification Service"]
    PROF["👤 Profile Service"]
    TG["☁️ Telegram Bot API"]

    RMQ1 -->|"Мэтчи"| NOTIFY
    RMQ2 -->|"Лайки"| NOTIFY
    RMQ3 -->|"Рефералы"| NOTIFY
    NOTIFY -->|"Получение профилей"| PROF
    NOTIFY -->|"Уведомления"| TG

    style NOTIFY fill:#a855f7,color:#fff
```

---

## 🏗️ Инфраструктурные компоненты

```mermaid
graph TB
    subgraph DB["💾 Хранение данных"]
        PG[("🐘 PostgreSQL 16<br/>Основная БД")]
        REDIS[("⚡ Redis 7<br/>Кэш ленты + брокер Celery")]
        MINIO["📦 MinIO<br/>S3 хранилище фото"]
    end

    subgraph MQ["📨 Обмен сообщениями"]
        RMQ["🐇 RabbitMQ 3.12<br/>Брокер сообщений<br/>────────<br/>swipe_events<br/>match_events<br/>profile_events<br/>referral_events<br/>review_events"]
    end

    subgraph TASKS["⏰ Фоновые задачи"]
        CELERY["🔧 Celery 5.3 + Beat<br/>────────<br/>Пересчёт рейтингов<br/>Peer score<br/>Инвалидация кэша"]
    end

    subgraph MON["📈 Мониторинг"]
        PROM["Prometheus<br/>Сбор метрик"]
        GRAF["Grafana<br/>Визуализация"]
    end

    subgraph DEPLOY["🐳 Развёртывание"]
        DOCKER["Docker + Compose<br/>Контейнеризация"]
    end

    CELERY --> REDIS
    PROM --> GRAF

    style DB fill:#e3f2fd,stroke:#1976d2
    style MQ fill:#fff3e0,stroke:#f57c00
    style TASKS fill:#e8f5e9,stroke:#388e3c
    style MON fill:#fce4ec,stroke:#c62828
    style DEPLOY fill:#f3e5f5,stroke:#7b1fa2
```

| Компонент | Назначение |
|:----------|:-----------|
| **PostgreSQL** | Основная БД для всех сервисов |
| **Redis** | Кэш отранжированных очередей анкет (ZSET), брокер Celery |
| **RabbitMQ** | Асинхронное взаимодействие между сервисами (loose coupling) |
| **Celery + Beat** | Периодический пересчёт рейтингов, peer score, инвалидация кэша |
| **MinIO** | S3-совместимое хранилище фотографий, presigned URL |
| **Prometheus + Grafana** | Сбор и визуализация метрик (RPS, latency, errors, queue sizes, icebreaker categories) |
| **Docker Compose** | Контейнеризация всех сервисов, единый запуск |

---

## 🔗 Общие библиотеки (`services/_shared`)

| Модуль | Назначение |
|:-------|:-----------|
| `circuit_breaker.py` | Circuit Breaker для защиты HTTP-клиентов от каскадных отказов |
| `events.py` | Канонические имена exchange / routing key (single source of truth) |
| `logging.py` | Структурированное JSON-логирование |
| `metrics.py` | Prometheus-метрики: счётчики регистраций, свайпов, мэтчей, уведомлений, времени ответа ленты |
| `rabbitmq.py` | Утилиты для публикации и потребления сообщений RabbitMQ |
| `settings.py` | Общие настройки окружения |
