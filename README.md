# Dating Bot 💘

Telegram-бот для знакомств с микросервисной архитектурой и системой рейтинга.

## Статус реализации

| Сервис | Статус | Описание |
|:-------|:-------|:---------|
| 🤖 **Bot Service** | ✅ **Готово** | FSM регистрация, главное меню, клавиатуры |
| 👤 **Profile Service** | ✅ **Готово** | CRUD профилей, загрузка фото в MinIO, предпочтения |
| 📊 **Ranking Service** | 🚧 Заглушка | В разработке |
| 💘 **Matching Service** | 🚧 Заглушка | В разработке |
| 🔔 **Notification Service** | 🚧 Заглушка | В разработке |

> 📖 **Подробная инструкция по запуску:** [`SETUP.md`](SETUP.md)

## Стек технологий

| Компонент | Технология |
|:---------:|:----------:|
| 🤖 Telegram Bot | aiogram 3.x |
| 🌐 REST API | FastAPI |
| 🐘 БД | PostgreSQL 16 |
| ⚡ Кэш | Redis 7 |
| 🐇 Очереди | RabbitMQ 3.12 |
| ⏰ Задачи | Celery 5 |
| 📦 S3 | MinIO |
| 📈 Метрики | Prometheus + Grafana |
| 🐳 Контейнеры | Docker Compose |
| 🚀 CI/CD | GitHub Actions |

## Архитектура

Система состоит из 5 микросервисов:

- **Bot Service** — интерфейс пользователя (Telegram)
- **Profile Service** — CRUD анкет, загрузка фото
- **Ranking Service** — 3-уровневая система рейтинга, кэширование ленты
- **Matching Service** — обработка свайпов, определение мэтчей
- **Notification Service** — уведомления о мэтчах

> Подробнее: [`docs/architecture.md`](docs/architecture.md)

## Документация

| Документ | Описание |
|:---------|:---------|
| [`docs/services.md`](docs/services.md) | Описание всех сервисов, API эндпоинты |
| [`docs/architecture.md`](docs/architecture.md) | Схема архитектуры, потоки данных |
| [`docs/database.md`](docs/database.md) | Схема БД, ER-диаграмма, формулы рейтинга |

## Быстрый старт

```bash
# Клонировать репозиторий
git clone https://github.com/UsachovaUlyana/ulsu.git
cd ulsu

# Скопировать переменные окружения
cp .env.example .env
# Заполнить TELEGRAM_BOT_TOKEN в .env

# Запустить все сервисы
docker-compose up -d
```

## Структура проекта

```
├── docs/                          # Документация
│   ├── services.md                # Описание сервисов
│   ├── architecture.md            # Архитектура системы
│   └── database.md                # Схема БД
├── services/
│   ├── bot-service/               # Telegram Bot
│   ├── profile-service/           # Управление профилями
│   ├── ranking-service/           # Рейтинги и лента
│   ├── matching-service/          # Свайпы и мэтчи
│   └── notification-service/      # Уведомления
├── infrastructure/
│   ├── prometheus/                # Конфиг Prometheus
│   └── grafana/                   # Конфиг Grafana
├── .github/workflows/ci.yml      # CI/CD pipeline
├── docker-compose.yml             # Оркестрация контейнеров
└── .env.example                   # Шаблон переменных окружения
```
