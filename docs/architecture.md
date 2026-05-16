# Архитектура системы Dating Bot

## Общая схема системы

```mermaid
graph TB
    subgraph TELEGRAM["☁️ Telegram Cloud"]
        TG_API["Telegram Bot API"]
    end

    subgraph DOCKER["🐳 Docker Compose"]

        subgraph SERVICES["⚙️ Микросервисы"]
            BOT["🤖 Bot Service<br/><i>aiogram 3.x</i><br/>─────────<br/>Команды, FSM, i18n,<br/>показ анкет, свайпы,<br/>peer reviews, лайки"]
            PROFILE["👤 Profile Service<br/><i>FastAPI</i><br/>─────────<br/>CRUD анкет,<br/>загрузка фото,<br/>рефералы"]
            RANKING["📊 Ranking Service<br/><i>FastAPI</i><br/>─────────<br/>Рейтинги, лента,<br/>semantic matching"]
            MATCHING["💘 Matching Service<br/><i>FastAPI</i><br/>─────────<br/>Свайпы, мэтчи,<br/>peer reviews"]
            NOTIFY["🔔 Notification Service<br/><i>aio-pika</i><br/>─────────<br/>Мэтчи, лайки,<br/>рефералы, icebreaker"]
        end

        subgraph INFRA["🏗️ Инфраструктура"]
            PG[("🐘 PostgreSQL 16<br/>─────────<br/>users, profiles,<br/>swipes, matches,<br/>ratings, referrals,<br/>peer_reviews,<br/>activity_log")]
            REDIS[("⚡ Redis 7<br/>─────────<br/>Кэш ленты анкет,<br/>FSM storage,<br/>брокер Celery")]
            RMQ["🐇 RabbitMQ 3.12<br/>─────────<br/>swipe_events<br/>match_events<br/>profile_events<br/>referral_events<br/>review_events")]
            MINIO["📦 MinIO<br/><i>S3-совместимое</i><br/>─────────<br/>Хранение фото")]
        end

        subgraph WORKERS["⏰ Фоновые задачи"]
            CELERY_W["🔧 Celery Worker<br/>─────────<br/>Пересчёт рейтингов,<br/>peer score"]
            CELERY_B["⏲️ Celery Beat<br/>─────────<br/>Расписание задач"]
        end

        subgraph MONITORING["📈 Мониторинг"]
            PROM["Prometheus<br/>─────────<br/>Сбор метрик"]
            GRAF["Grafana<br/>─────────<br/>Дашборды"]
        end
    end

    TG_API <-->|"Long Polling"| BOT

    BOT -->|"REST API"| PROFILE
    BOT -->|"REST API"| RANKING
    BOT -->|"Публикация<br/>свайпов"| RMQ

    PROFILE --> PG
    PROFILE -->|"S3 API"| MINIO
    PROFILE -->|"profile_events<br/>referral_events"| RMQ

    RANKING --> PG
    RANKING --> REDIS

    RMQ -->|"swipe_events"| MATCHING
    RMQ -->|"swipe_events"| RANKING
    RMQ -->|"match_events"| NOTIFY
    RMQ -->|"like.received"| NOTIFY
    RMQ -->|"referral_events"| NOTIFY
    RMQ -->|"review_events"| RANKING

    MATCHING --> PG
    MATCHING -->|"match_events<br/>review_events<br/>like.received"| RMQ

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

    User->>TG: /start [deep_link ref_xxx]
    TG->>Bot: Update (telegram_id)
    Bot->>Profile: POST /api/v1/users/
    Profile->>PG: INSERT INTO users
    PG-->>Profile: OK
    Profile-->>Bot: 201 Created

    Note over Bot,User: FSM: пошаговое заполнение анкеты + i18n

    User->>TG: Имя, возраст, пол, город, bio, интересы...
    TG->>Bot: Данные анкеты
    Bot->>Profile: PUT /api/v1/users/{id}/profile
    Profile->>PG: INSERT INTO profiles
    PG-->>Profile: OK

    User->>TG: 📷 Фото (1–5 шт, media group поддерживается)
    TG->>Bot: Файлы фото
    Bot->>Profile: POST /api/v1/users/{id}/photos
    Profile->>S3: PUT object (photo)
    S3-->>Profile: OK
    Profile->>PG: INSERT INTO photos (s3_key, position)
    Profile-->>Bot: 201 Created

    User->>TG: Предпочтения: пол, возраст, search_city
    TG->>Bot: Данные фильтров
    Bot->>Profile: PUT /api/v1/users/{id}/preferences
    Profile->>PG: INSERT INTO preferences
    PG-->>Profile: OK

    alt Реферальный код был использован
        Bot->>Profile: POST /api/v1/referrals/apply
        Profile->>PG: INSERT INTO referrals
        Profile->>RMQ: 📤 referral_events
    end

    Profile->>RMQ: 📤 profile_events (профиль обновлён)
    RMQ->>Rank: 📥 profile_events
    Rank->>PG: Пересчёт primary_score
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

    Rank->>Cache: ZREVRANGE feed:{user_id} 0 0

    alt Кэш пуст (miss)
        Cache-->>Rank: ∅ (miss)
        Rank->>PG: SELECT кандидаты<br/>(target_gender, age, search_city,<br/>не просмотренные)
        PG-->>Rank: Список профилей
        Rank->>Rank: 🧮 Расчёт semantic_interest_boost<br/>+ peer_count для каждого кандидата
        Rank->>Rank: Сортировка
        Rank->>Cache: ZADD feed:{id} (топ-10 анкет)<br/>TTL: 30 мин
        Rank-->>Bot: Первая анкета (JSON profile)
    else Кэш есть (hit)
        Cache-->>Rank: ✅ (hit)
        Rank-->>Bot: Следующая анкета
    end

    Bot->>Profile: GET /api/v1/users/{profile_id}
    Profile->>PG: SELECT profile
    Profile->>S3: Presigned URL для фото
    Profile-->>Bot: Данные анкеты + URL фото

    alt Несколько фото (≥2)
        Bot->>Bot: Photo Proxy: скачивание фото<br/>из MinIO как InputMediaPhoto
        Bot->>TG: Media Group (карусель)
        Bot->>TG: Caption + кнопки [❤️] [👎] [⏹️]
    else Одно фото
        Bot->>TG: Карточка анкеты + кнопки
    end
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
    participant Notify as 🔔 Notification Service
    actor User2 as 👤 Другой пользователь

    User->>TG: Нажимает ❤️ Лайк
    TG->>Bot: Callback: like
    Bot->>RMQ: 📤 swipe_events<br/>{swiper_id, target_id, action: "like"}

    par Параллельная обработка
        RMQ->>Match: 📥 swipe_events
        Match->>PG: INSERT INTO swipes
        Match->>PG: SELECT * FROM swipes<br/>WHERE swiper = target_id AND target = swiper_id

        alt Взаимный лайк найден! 💕
            Match->>PG: INSERT INTO matches
            Match->>RMQ: 📤 match_events<br/>{user1_id, user2_id}
            RMQ->>Notify: 📥 match_events
            Notify->>Profile: GET профили обоих
            Notify->>Notify: 🧊 pick_topics (icebreaker)
            Notify->>TG: "🎉 У вас мэтч!" + темы + @username
            TG-->>User: Уведомление
            TG-->>User2: Уведомление
        else Нет взаимного лайка
            Match->>RMQ: 📤 like.received<br/>{target_telegram_id}
            RMQ->>Notify: 📥 like.received
            Notify->>TG: "❤️ Кому-то понравилась твоя анкета!"
            TG-->>User2: Уведомление
        end
    and
        RMQ->>Rank: 📥 swipe_events
        Rank->>PG: Обновление behavioral_score<br/>(likes_received, like_ratio)
    end
```

### 4. Peer Review (оценка мэтча)

```mermaid
sequenceDiagram
    actor User as 👤 Пользователь
    participant TG as Telegram
    participant Bot as 🤖 Bot Service
    participant Match as 💘 Matching Service
    participant PG as 🐘 PostgreSQL
    participant RMQ as 🐇 RabbitMQ
    participant Rank as 📊 Ranking Service
    actor User2 as 👤 Другой пользователь

    User->>TG: Нажимает "Оценить" на мэтче
    TG->>Bot: Callback: match:rate
    Bot->>TG: "Оцените от 1.0 до 5.0"
    TG-->>User: Клавиатура с оценками

    User->>TG: Выбирает 4.5
    TG->>Bot: Callback: rate:4.5
    Bot->>Match: POST /api/v1/reviews<br/>{reviewer_tg, reviewee_tg, score: 4.5}
    Match->>PG: VERIFY match EXISTS
    Match->>PG: UPSERT peer_reviews (ON CONFLICT DO UPDATE)
    PG-->>Match: OK
    Match->>RMQ: 📤 review_events<br/>{reviewer_id, reviewee_id, score}
    Match-->>Bot: 200 OK
    Bot->>TG: "Оценка сохранена"
    TG-->>User: Подтверждение

    RMQ->>Rank: 📥 review_events
    Rank->>PG: Пересчёт peer_score (Bayesian smoothing)
    Rank->>PG: Пересчёт combined_score
    Rank->>Cache: DEL feed:* (инвалидация)
```

### 5. Просмотр полученных лайков

```mermaid
sequenceDiagram
    actor User as 👤 Пользователь
    participant TG as Telegram
    participant Bot as 🤖 Bot Service
    participant Match as 💘 Matching Service
    participant PG as 🐘 PostgreSQL
    participant Profile as 👤 Profile Service

    User->>TG: "Кто меня лайкнул?"
    TG->>Bot: Callback
    Bot->>Match: GET /api/v1/likes/{telegram_id}
    Match->>PG: SELECT swiper_id<br/>WHERE target_id = user<br/>AND нет обратного свайпа<br/>ORDER BY created_at DESC
    PG-->>Match: Список лайков
    Match->>PG: JOIN ratings + peer_reviews<br/>для enriched данных
    Match-->>Bot: {telegram_id, combined_score, peer_avg, peer_count}

    loop Для каждого лайка
        Bot->>Profile: GET /api/v1/users/{telegram_id}
        Profile->>PG: SELECT profile + photos
        Profile-->>Bot: Данные анкеты
        Bot->>Bot: 🧮 semantic_interest_boost<br/>для compatibility
        Bot->>TG: Карточка + [❤️] [👎]
    end
    TG-->>User: 📱 Лента лайков
```

### 6. Периодический пересчёт рейтингов (Celery)

```mermaid
sequenceDiagram
    participant Beat as ⏲️ Celery Beat
    participant Worker as 🔧 Celery Worker
    participant PG as 🐘 PostgreSQL
    participant Cache as ⚡ Redis

    Note over Beat: Каждые 15 мин

    Beat->>Worker: 🔄 recalc_behavioral_all
    Worker->>PG: SELECT свайпы, мэтчи, диалоги<br/>за окно 14 дней
    Worker->>PG: SELECT active_hours FROM activity_log
    Worker->>Worker: 🧮 behavioral_score<br/>для каждого пользователя
    Worker->>PG: BULK UPDATE ratings<br/>SET behavioral_score = ...

    Note over Beat: Каждый час

    Beat->>Worker: 🔄 recalc_combined_all
    Worker->>PG: SELECT ratings + referrals + peer_reviews
    Worker->>Worker: 🧮 combined =<br/>primary × w1<br/>+ behavioral × w2<br/>+ peer_score × w3<br/>+ referral × w4
    Worker->>PG: BULK UPDATE ratings<br/>SET combined_score = ...
    Worker->>Cache: DEL feed:* (инвалидация)

    Note over Beat: По расписанию

    Beat->>Worker: 🔄 recalc_peer_all
    Worker->>PG: AVG(score), COUNT(*) FROM peer_reviews
    Worker->>Worker: 🧮 peer_score с Bayesian smoothing
    Worker->>PG: BULK UPDATE ratings<br/>SET peer_score = ...
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
| ⚡ Кэш | **Redis** | 7.x | Кэширование ленты, FSM storage, брокер Celery |
| 🐇 Очереди | **RabbitMQ** | 3.12+ | Брокер сообщений между сервисами |
| ⏰ Задачи | **Celery** | 5.3+ | Периодические и отложенные задачи |
| 📦 S3 | **MinIO** | latest | S3-совместимое хранилище фотографий |
| 📈 Метрики | **Prometheus** | latest | Сбор метрик |
| 📊 Дашборды | **Grafana** | latest | Визуализация метрик |
| 🐳 Контейнеры | **Docker + Compose** | latest | Контейнеризация и оркестрация |

---

## Принципы архитектуры

| Принцип | Описание |
|:--------|:---------|
| 🔗 **Слабая связанность** | Сервисы общаются через RabbitMQ — падение одного не ломает другие |
| ⚡ **Асинхронная обработка** | Свайпы, мэтчи, рефералы, reviews — через очередь, не блокируя UI |
| 💾 **Кэширование** | Redis убирает нагрузку с БД при частых запросах к ленте (ZSET + JSON) |
| 👁️ **Наблюдаемость** | Prometheus + Grafana + структурное JSON-логирование |
| 📐 **Горизонтальное масштабирование** | Каждый сервис масштабируется независимо |
| 🔄 **Идемпотентность** | Повторная обработка события (swipe, match, review) не ломает состояние |
| 🛡️ **Circuit Breaker** | Защита от каскадных отказов при недоступности downstream-сервисов |
| 🌍 **Интернационализация** | i18n на уровне Bot Service (ru/en), расширяемая архитектура |
