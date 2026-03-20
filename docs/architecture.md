# Архитектура системы Dating Bot

## Общая схема системы

```mermaid
graph TB
    subgraph TELEGRAM["☁️ Telegram Cloud"]
        TG_API["Telegram Bot API"]
    end

    subgraph DOCKER["🐳 Docker Compose"]

        subgraph SERVICES["⚙️ Микросервисы"]
            BOT["🤖 Bot Service<br/><i>aiogram 3.x</i><br/>─────────<br/>Команды, FSM,<br/>показ анкет, свайпы"]
            PROFILE["👤 Profile Service<br/><i>FastAPI</i><br/>─────────<br/>CRUD анкет,<br/>загрузка фото"]
            RANKING["📊 Ranking Service<br/><i>FastAPI</i><br/>─────────<br/>Рейтинги,<br/>формирование ленты"]
            MATCHING["💘 Matching Service<br/><i>FastAPI</i><br/>─────────<br/>Свайпы, мэтчи,<br/>история"]
            NOTIFY["🔔 Notification Service<br/><i>aio-pika</i><br/>─────────<br/>Уведомления<br/>о мэтчах"]
        end

        subgraph INFRA["🏗️ Инфраструктура"]
            PG[("🐘 PostgreSQL 16<br/>─────────<br/>users, profiles,<br/>swipes, matches,<br/>ratings, referrals")]
            REDIS[("⚡ Redis 7<br/>─────────<br/>Кэш ленты анкет,<br/>сессии, брокер Celery")]
            RMQ["🐇 RabbitMQ 3.12<br/>─────────<br/>swipe_events<br/>match_events<br/>profile_events<br/>rating_events"]
            MINIO["📦 MinIO<br/><i>S3-совместимое</i><br/>─────────<br/>Хранение фото"]
        end

        subgraph WORKERS["⏰ Фоновые задачи"]
            CELERY_W["🔧 Celery Worker<br/>─────────<br/>Пересчёт рейтингов"]
            CELERY_B["⏲️ Celery Beat<br/>─────────<br/>Расписание задач"]
        end

        subgraph MONITORING["📈 Мониторинг"]
            PROM["Prometheus<br/>─────────<br/>Сбор метрик"]
            GRAF["Grafana<br/>─────────<br/>Дашборды"]
        end
    end

    TG_API <-->|"Webhooks /<br/>Long Polling"| BOT

    BOT -->|"REST API"| PROFILE
    BOT -->|"REST API"| RANKING
    BOT -->|"Публикация<br/>свайпов"| RMQ

    PROFILE --> PG
    PROFILE -->|"S3 API"| MINIO
    PROFILE -->|"profile_events"| RMQ

    RANKING --> PG
    RANKING --> REDIS

    RMQ -->|"swipe_events"| MATCHING
    RMQ -->|"swipe_events"| RANKING
    RMQ -->|"match_events"| NOTIFY
    NOTIFY -->|"Отправка<br/>уведомлений"| TG_API

    MATCHING --> PG
    MATCHING -->|"match_events"| RMQ

    CELERY_B -->|"Расписание"| CELERY_W
    CELERY_W --> PG
    CELERY_W --> REDIS

    PROM -.->|"Scrape /metrics"| PROFILE
    PROM -.->|"Scrape /metrics"| RANKING
    PROM -.->|"Scrape /metrics"| MATCHING
    GRAF -.-> PROM

    style TELEGRAM fill:#54a9eb,color:#fff,stroke:#2d8fd5
    style BOT fill:#5b9bd5,color:#fff,stroke:#4178a4
    style PROFILE fill:#70ad47,color:#fff,stroke:#548235
    style RANKING fill:#ed7d31,color:#fff,stroke:#c45d1a
    style MATCHING fill:#e84d8a,color:#fff,stroke:#c43070
    style NOTIFY fill:#a855f7,color:#fff,stroke:#8b3fd4
    style PG fill:#336791,color:#fff,stroke:#264f6d
    style REDIS fill:#dc382d,color:#fff,stroke:#b42e24
    style RMQ fill:#ff6600,color:#fff,stroke:#cc5200
    style MINIO fill:#c72c48,color:#fff,stroke:#a12039
    style CELERY_W fill:#37b24d,color:#fff,stroke:#2d9140
    style CELERY_B fill:#37b24d,color:#fff,stroke:#2d9140
    style PROM fill:#e6522c,color:#fff,stroke:#c4441f
    style GRAF fill:#f2a70a,color:#fff,stroke:#d09000
```

---

## Потоки данных

### 1. Регистрация и заполнение анкеты

```mermaid
sequenceDiagram
    actor User as 👤 Пользователь
    participant TG as Telegram
    participant Bot as 🤖 Bot Service
    participant Profile as 👤 Profile Service
    participant PG as 🐘 PostgreSQL
    participant S3 as 📦 MinIO (S3)
    participant RMQ as 🐇 RabbitMQ
    participant Rank as 📊 Ranking Service

    User->>TG: /start
    TG->>Bot: Update (telegram_id)
    Bot->>Profile: POST /api/v1/users/
    Profile->>PG: INSERT INTO users
    PG-->>Profile: OK
    Profile-->>Bot: 201 Created

    Note over Bot,User: FSM: пошаговое заполнение анкеты

    User->>TG: Имя, возраст, пол, город...
    TG->>Bot: Данные анкеты
    Bot->>Profile: PUT /api/v1/users/{id}
    Profile->>PG: INSERT INTO profiles
    PG-->>Profile: OK

    User->>TG: 📷 Фото
    TG->>Bot: Файл фото
    Bot->>Profile: POST /api/v1/users/{id}/photos
    Profile->>S3: PUT object (photo)
    S3-->>Profile: OK
    Profile->>PG: INSERT INTO photos (s3_key)
    Profile-->>Bot: 201 Created

    Profile->>RMQ: 📤 profile_events (профиль обновлён)
    RMQ->>Rank: 📥 profile_events
    Rank->>PG: Пересчёт первичного рейтинга
    Rank->>PG: UPDATE ratings SET primary_score = ...
```

### 2. Просмотр анкет (Feed)

```mermaid
sequenceDiagram
    actor User as 👤 Пользователь
    participant TG as Telegram
    participant Bot as 🤖 Bot Service
    participant Rank as 📊 Ranking Service
    participant Cache as ⚡ Redis
    participant PG as 🐘 PostgreSQL
    participant Profile as 👤 Profile Service
    participant S3 as 📦 MinIO

    User->>TG: "Смотреть анкеты"
    TG->>Bot: Callback
    Bot->>Rank: GET /api/v1/feed/{telegram_id}

    Rank->>Cache: GET feed:{telegram_id}

    alt Кэш пуст
        Cache-->>Rank: ∅ (miss)
        Rank->>PG: SELECT кандидаты<br/>(пол, возраст, город, не просмотренные)
        PG-->>Rank: Список профилей
        Rank->>Rank: 🧮 Расчёт combined_score<br/>для каждого кандидата
        Rank->>Rank: Сортировка по рейтингу
        Rank->>Cache: ZADD feed:{id} (топ-10 анкет)<br/>TTL: 30 мин
        Rank-->>Bot: Первая анкета (profile_id)
    else Кэш есть
        Cache-->>Rank: ✅ (hit)
        Rank->>Cache: ZPOPMAX feed:{id}
        Rank-->>Bot: Следующая анкета (profile_id)
    end

    Bot->>Profile: GET /api/v1/users/{profile_id}
    Profile->>PG: SELECT profile
    Profile->>S3: Presigned URL для фото
    Profile-->>Bot: Данные анкеты + URL фото

    Bot->>TG: Карточка анкеты + кнопки [❤️ Лайк] [👎 Пропустить]
    TG-->>User: 📱 Отображение анкеты
```

### 3. Свайп и мэтч

```mermaid
sequenceDiagram
    actor User as 👤 Пользователь
    participant TG as Telegram
    participant Bot as 🤖 Bot Service
    participant RMQ as 🐇 RabbitMQ
    participant Match as 💘 Matching Service
    participant PG as 🐘 PostgreSQL
    participant Rank as 📊 Ranking Service
    participant Notify as 🔔 Notification
    actor User2 as 👤 Другой пользователь

    User->>TG: Нажимает ❤️ Лайк
    TG->>Bot: Callback: like
    Bot->>RMQ: 📤 swipe_events<br/>{swiper_id, swiped_id, action: "like"}

    par Параллельная обработка
        RMQ->>Match: 📥 swipe_events
        Match->>PG: INSERT INTO swipes
        Match->>PG: SELECT * FROM swipes<br/>WHERE swiper = swiped_id AND swiped = swiper_id

        alt Взаимный лайк найден! 💕
            Match->>PG: INSERT INTO matches
            Match->>RMQ: 📤 match_events<br/>{user1_id, user2_id}
            RMQ->>Notify: 📥 match_events
            Notify->>TG: "🎉 У вас мэтч!"
            TG-->>User: Уведомление
            Notify->>TG: "🎉 У вас мэтч!"
            TG-->>User2: Уведомление
        else Нет взаимного лайка
            Match-->>Match: Ожидание ответного свайпа
        end
    and
        RMQ->>Rank: 📥 swipe_events
        Rank->>PG: Обновление поведенческого рейтинга<br/>(likes_received, like_ratio)
    end
```

### 4. Периодический пересчёт рейтингов (Celery)

```mermaid
sequenceDiagram
    participant Beat as ⏲️ Celery Beat
    participant Worker as 🔧 Celery Worker
    participant PG as 🐘 PostgreSQL
    participant Cache as ⚡ Redis

    Note over Beat: Каждые 15 мин

    Beat->>Worker: 🔄 recalculate_behavioral_ratings
    Worker->>PG: SELECT все свайпы за период
    Worker->>PG: SELECT все мэтчи за период
    Worker->>Worker: 🧮 Пересчёт behavioral_score<br/>для каждого активного пользователя
    Worker->>PG: BULK UPDATE ratings<br/>SET behavioral_score = ...
    Worker->>Cache: DEL feed:* (инвалидация кэшей)

    Note over Beat: Каждый час

    Beat->>Worker: 🔄 recalculate_combined_ratings
    Worker->>PG: SELECT ratings + referrals
    Worker->>Worker: 🧮 combined = primary×0.3 + behavioral×0.7 + bonus
    Worker->>PG: BULK UPDATE ratings<br/>SET combined_score = ...
    Worker->>Cache: DEL feed:* (инвалидация)
```

---

## Стек технологий

| Компонент | Технология | Версия | Назначение |
|:---------:|:----------:|:------:|:-----------|
| 🐍 Язык | **Python** | 3.11+ | Основной язык разработки |
| 🤖 Telegram Bot | **aiogram** | 3.x | Асинхронный фреймворк для Telegram Bot API |
| 🌐 REST API | **FastAPI** | 0.100+ | HTTP API для сервисов |
| 🗄️ ORM | **SQLAlchemy** | 2.0+ | Работа с БД |
| 📋 Миграции | **Alembic** | 1.12+ | Миграции схемы БД |
| 🐘 БД | **PostgreSQL** | 16 | Основное хранилище данных |
| ⚡ Кэш | **Redis** | 7.x | Кэширование, брокер Celery |
| 🐇 Очереди | **RabbitMQ** | 3.12+ | Брокер сообщений между сервисами |
| ⏰ Задачи | **Celery** | 5.3+ | Периодические и отложенные задачи |
| 📦 S3 | **MinIO** | latest | S3-совместимое хранилище фотографий |
| 📈 Метрики | **Prometheus** | latest | Сбор метрик |
| 📊 Дашборды | **Grafana** | latest | Визуализация метрик |
| 🐳 Контейнеры | **Docker + Compose** | latest | Контейнеризация и оркестрация |
| 🚀 CI/CD | **GitHub Actions** | — | Автоматизация сборки и тестов |

---

## Принципы архитектуры

| Принцип | Описание |
|:--------|:---------|
| 🔗 **Слабая связанность** | Сервисы общаются через RabbitMQ — падение одного не ломает другие |
| ⚡ **Асинхронная обработка** | Свайпы обрабатываются через очередь, не блокируя UI |
| 💾 **Кэширование** | Redis убирает нагрузку с БД при частых запросах к ленте |
| 👁️ **Наблюдаемость** | Prometheus + Grafana + структурное логирование |
| 📐 **Горизонтальное масштабирование** | Каждый сервис масштабируется независимо |
| 🔄 **Идемпотентность** | Повторная обработка события не ломает состояние |
