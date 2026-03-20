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
    BOT -.->|RabbitMQ| MATCH
    MATCH -.->|RabbitMQ| NOTIFY
    MATCH -.->|RabbitMQ| RANK
    PROF -.->|RabbitMQ| RANK

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
| **Назначение** | Интерфейс пользователя. Принимает команды из Telegram, отображает анкеты, обрабатывает свайпы, уведомляет о мэтчах |
| **Технологии** | Python, aiogram 3.x, aiohttp, aio-pika |
| **Порт** | — (общается с Telegram API напрямую) |

### Основные функции

- 🚀 Обработка команды `/start` — регистрация пользователя (Telegram ID)
- 📝 Заполнение анкеты через **пошаговый диалог (FSM)**:
  - Имя, возраст, пол, город, описание, интересы
  - Загрузка фотографий (1–5 штук)
  - Настройка предпочтений (кого ищу: пол, возрастной диапазон, город)
- 👀 Просмотр анкет — показ карточек других пользователей
- 💕 Свайп-механика — кнопки `❤️ Лайк` / `👎 Пропустить` / `⚙️ Настройки`
- 🔔 Получение уведомлений о мэтчах
- ✏️ Редактирование своей анкеты
- 🔗 Реферальная система — команда `/invite` генерирует ссылку

### Взаимодействие

```mermaid
graph LR
    TG["☁️ Telegram API"]
    BOT["🤖 Bot Service"]
    PROF["👤 Profile Service"]
    RANK["📊 Ranking Service"]
    RMQ["🐇 RabbitMQ"]

    TG <-->|"Webhooks"| BOT
    BOT -->|"CRUD анкет,<br/>загрузка фото"| PROF
    BOT -->|"Получение<br/>ленты анкет"| RANK
    BOT -->|"Отправка<br/>свайпов"| RMQ

    style BOT fill:#5b9bd5,color:#fff
```

---

## 2. 👤 Profile Service (`profile-service`)

| | |
|:--|:--|
| **Назначение** | Управление профилями пользователей. Хранение анкет, фотографий, предпочтений. CRUD-операции |
| **Технологии** | Python, FastAPI, SQLAlchemy, PostgreSQL, MinIO (S3), aio-pika |
| **Порт** | `8001` |

### Основные функции

- 📋 Регистрация пользователя по Telegram ID
- ✏️ Создание / обновление / получение / удаление анкеты
- 📷 Загрузка фотографий в S3-хранилище (MinIO)
- 🔗 Генерация presigned URL для доступа к фото
- ⚙️ Управление предпочтениями поиска
- 👥 Реферальная система — учёт приглашённых пользователей
- ✅ Валидация данных анкеты

### API эндпоинты

| Метод | Эндпоинт | Описание |
|:------|:---------|:---------|
| `POST` | `/api/v1/users/` | Регистрация нового пользователя |
| `GET` | `/api/v1/users/{telegram_id}` | Получение профиля |
| `PUT` | `/api/v1/users/{telegram_id}` | Обновление профиля |
| `DELETE` | `/api/v1/users/{telegram_id}` | Удаление профиля |
| `POST` | `/api/v1/users/{telegram_id}/photos` | Загрузка фото |
| `DELETE` | `/api/v1/users/{telegram_id}/photos/{photo_id}` | Удаление фото |
| `GET` | `/api/v1/users/{telegram_id}/preferences` | Получение предпочтений |
| `PUT` | `/api/v1/users/{telegram_id}/preferences` | Обновление предпочтений |
| `POST` | `/api/v1/users/{telegram_id}/referral` | Применение реферального кода |

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
    PROF -->|"profile_events"| RMQ

    style PROF fill:#70ad47,color:#fff
```

---

## 3. 📊 Ranking Service (`ranking-service`)

| | |
|:--|:--|
| **Назначение** | Расчёт и хранение рейтингов. Формирование персонализированной ленты анкет. Кэширование |
| **Технологии** | Python, FastAPI, SQLAlchemy, PostgreSQL, Redis, Celery, aio-pika |
| **Порт** | `8002` |

### Алгоритм рейтинга (3 уровня)

```mermaid
graph TB
    subgraph L1["🟢 Уровень 1 — Первичный рейтинг"]
        A1["Полнота анкеты<br/>(заполненность полей)"]
        A2["Количество фото"]
        A3["Соответствие предпочтениям<br/>(возраст, пол, город)"]
    end

    subgraph L2["🟡 Уровень 2 — Поведенческий рейтинг"]
        B1["Количество полученных<br/>лайков"]
        B2["Соотношение<br/>лайков к пропускам"]
        B3["Частота мэтчей<br/>(взаимных лайков)"]
        B4["Частота инициирования<br/>диалогов после мэтча"]
        B5["Активность по<br/>времени суток"]
    end

    subgraph L3["🔴 Уровень 3 — Комбинированный рейтинг"]
        C1["Взвешенная сумма<br/>primary × 0.3 + behavioral × 0.7"]
        C2["Бонус за рефералов<br/>(до +10 баллов)"]
    end

    L1 -->|"primary_score<br/>(0–100)"| L3
    L2 -->|"behavioral_score<br/>(0–100)"| L3
    L3 -->|"combined_score"| FEED["📱 Лента анкет"]

    style L1 fill:#e8f5e9,stroke:#388e3c
    style L2 fill:#fff3e0,stroke:#f57c00
    style L3 fill:#fce4ec,stroke:#c62828
    style FEED fill:#e3f2fd,stroke:#1976d2
```

### Кэширование (Redis)

> При начале сессии просмотра: первая анкета проходит полный путь ранжирования.
> Одновременно подгружаются **10 следующих анкет** в Redis.
> Следующие 9 отдаются из кэша мгновенно.
> На **10-й анкете** — новый цикл подгрузки.

### Периодический пересчёт (Celery)

| Задача | Периодичность |
|:-------|:--------------|
| Пересчёт поведенческого рейтинга | Каждые **15 минут** |
| Очистка устаревших кэшей | Каждые **30 минут** |
| Полный пересчёт комбинированного рейтинга | Каждый **час** |

### API эндпоинты

| Метод | Эндпоинт | Описание |
|:------|:---------|:---------|
| `GET` | `/api/v1/feed/{telegram_id}` | Получить следующую анкету для показа |
| `GET` | `/api/v1/ratings/{telegram_id}` | Получить текущий рейтинг пользователя |
| `POST` | `/api/v1/ratings/recalculate` | Принудительный пересчёт (admin) |

### Взаимодействие

```mermaid
graph LR
    BOT["🤖 Bot Service"]
    RANK["📊 Ranking Service"]
    PG[("🐘 PostgreSQL")]
    REDIS[("⚡ Redis")]
    RMQ["🐇 RabbitMQ"]
    CELERY["⏰ Celery"]

    BOT -->|"REST API"| RANK
    RANK -->|"Рейтинги"| PG
    RANK <-->|"Кэш ленты"| REDIS
    RMQ -->|"swipe_events<br/>profile_events"| RANK
    CELERY -->|"Пересчёт"| RANK

    style RANK fill:#ed7d31,color:#fff
```

---

## 4. 💘 Matching Service (`matching-service`)

| | |
|:--|:--|
| **Назначение** | Обработка свайпов, определение мэтчей (взаимных лайков), ведение истории взаимодействий |
| **Технологии** | Python, FastAPI, SQLAlchemy, PostgreSQL, aio-pika |
| **Порт** | `8003` |

### Основные функции

- 📝 Запись свайпа (лайк / пропуск) в базу
- 💕 Проверка на взаимный лайк (мэтч)
- 📤 При мэтче — публикация события в очередь уведомлений
- 📖 Хранение истории просмотренных анкет (чтобы не показывать повторно)
- 📋 Предоставление списка мэтчей пользователя
- 📊 Публикация событий взаимодействия для Ranking Service

### API эндпоинты

| Метод | Эндпоинт | Описание |
|:------|:---------|:---------|
| `POST` | `/api/v1/swipes/` | Записать свайп (like/skip) |
| `GET` | `/api/v1/matches/{telegram_id}` | Список мэтчей пользователя |
| `GET` | `/api/v1/swipes/{telegram_id}/history` | История просмотренных анкет |

### Взаимодействие

```mermaid
graph LR
    RMQ_IN["🐇 RabbitMQ<br/>(swipe_events)"]
    MATCH["💘 Matching Service"]
    PG[("🐘 PostgreSQL")]
    RMQ_OUT["🐇 RabbitMQ<br/>(match_events)"]

    RMQ_IN -->|"Свайпы"| MATCH
    MATCH -->|"Свайпы и мэтчи"| PG
    MATCH -->|"При мэтче"| RMQ_OUT

    style MATCH fill:#e84d8a,color:#fff
```

---

## 5. 🔔 Notification Service (`notification-service`)

| | |
|:--|:--|
| **Назначение** | Отправка уведомлений пользователям. Обрабатывает события из очереди и формирует сообщения |
| **Технологии** | Python, aio-pika, aiohttp |
| **Порт** | — (только консюмер очереди) |

### Основные функции

- 📥 Подписка на очередь событий мэтчей из RabbitMQ
- 📝 Формирование текста уведомления
- 📤 Отправка уведомления **обоим** пользователям при мэтче через Telegram Bot API
- 📋 Логирование отправленных уведомлений
- 🔄 Retry-механизм при ошибках отправки

### Взаимодействие

```mermaid
graph LR
    RMQ["🐇 RabbitMQ<br/>(match_events)"]
    NOTIFY["🔔 Notification Service"]
    TG["☁️ Telegram Bot API"]

    RMQ -->|"События мэтчей"| NOTIFY
    NOTIFY -->|"Уведомления<br/>обоим пользователям"| TG

    style NOTIFY fill:#a855f7,color:#fff
```

---

## 🏗️ Инфраструктурные компоненты

```mermaid
graph TB
    subgraph DB["💾 Хранение данных"]
        PG[("🐘 PostgreSQL 16<br/>Основная БД")]
        REDIS[("⚡ Redis 7<br/>Кэш + брокер Celery")]
        MINIO["📦 MinIO<br/>S3 хранилище фото"]
    end

    subgraph MQ["📨 Обмен сообщениями"]
        RMQ["🐇 RabbitMQ 3.12<br/>Брокер сообщений<br/>────────<br/>swipe_events<br/>match_events<br/>profile_events<br/>rating_events"]
    end

    subgraph TASKS["⏰ Фоновые задачи"]
        CELERY["🔧 Celery 5.3 + Beat<br/>────────<br/>Пересчёт рейтингов<br/>Очистка данных<br/>Отложенные задачи"]
    end

    subgraph MON["📈 Мониторинг"]
        PROM["Prometheus<br/>Сбор метрик"]
        GRAF["Grafana<br/>Визуализация"]
    end

    subgraph DEPLOY["🐳 Развёртывание"]
        DOCKER["Docker + Compose<br/>Контейнеризация"]
        CI["🚀 GitHub Actions<br/>CI/CD pipeline"]
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
| **Redis** | Кэш отранжированных очередей анкет, сессии просмотра, брокер Celery |
| **RabbitMQ** | Асинхронное взаимодействие между сервисами (loose coupling) |
| **Celery + Beat** | Периодический пересчёт рейтингов, очистка данных, отложенные задачи |
| **MinIO** | S3-совместимое хранилище фотографий, presigned URL |
| **Prometheus + Grafana** | Сбор и визуализация метрик (RPS, latency, errors, queue sizes) |
| **Docker Compose** | Контейнеризация всех сервисов, единый запуск |
| **GitHub Actions** | CI/CD: lint, тесты, сборка Docker-образов |
