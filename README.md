# Dating Bot 💘

Микросервисный Telegram-бот знакомств с **прозрачным ранжированием**, гео-фильтрацией, реферальной системой и айсбрейкерами после мэтча.

## Что внутри

| Сервис | Стек | Назначение |
|:---|:---|:---|
| 🤖 `bot-service` | aiogram 3 + Redis FSM | UI бота, регистрация, свайпы, меню |
| 👤 `profile-service` | FastAPI + SQLAlchemy + Alembic + MinIO | CRUD анкет, фото, рефералы, REST |
| 📊 `ranking-service` | FastAPI + Celery + Redis + PostgreSQL | 3-уровневый рейтинг, кэш ленты, Haversine |
| 💘 `matching-service` | FastAPI + RabbitMQ consumer | Свайпы, детект мэтчей |
| 🔔 `notification-service` | RabbitMQ consumer + Telegram API | Уведомления о мэтчах + AI-айсбрейкеры |

## Архитектура

```
   Telegram ──► bot-service ──► profile-service (REST)
                    │           ranking-service  (REST)
                    │
                    └─publish──► RabbitMQ (4 топика)
                                       │
              ┌────────────────────────┼─────────────────────┐
              ▼                        ▼                     ▼
         matching-service       ranking-service     notification-service
         (swipe → match)        (consumers + Celery     (match → пуш +
              │                  beat: пересчёты)          айсбрейкер)
              └────publish match_events────► (та же шина)

         PostgreSQL 16    Redis 7    MinIO    Prometheus + Grafana
         (8 таблиц)       (FSM,      (фото)   (метрики + дашборд
                          кэш ленты)           провижионинг)
```

Подробно: [`docs/architecture.md`](docs/architecture.md), [`docs/services.md`](docs/services.md), [`docs/database.md`](docs/database.md).

## Чем отличается от Дайвинчика

1. **Прозрачная лента** — каждой карточке показывается совместимость в %, расстояние и общие интересы.
2. **3-уровневый рейтинг** (анкета → поведение → бонусы), пересчитывается Celery beat каждые 15 мин и каждый час.
3. **Гео-радиус** через Haversine, фильтры 5/10/25/50/100 км или ∞.
4. **Реферальный буст** — пригласил друга, оба получили `+0.05` к combined-скору (cap 0.3).
5. **Айсбрейкеры при мэтче** — бот автоматически шлёт обоим 3 темы для разговора, подобранные по общим интересам (шаблонно, архитектурно готово к подмене на LLM).

## Быстрый старт

```bash
git clone <repo>
cd ulsu

# 1) .env с токеном бота (см. .env.example)
cp .env.example .env
# отредактировать TELEGRAM_BOT_TOKEN

# 2) Поднять весь стек
docker-compose up -d
docker-compose ps   # все Up

# 3) Открыть бота в Telegram → /start → пройти регистрацию
```

Полная инструкция — [`SETUP.md`](SETUP.md).

## Стек

Python 3.11, aiogram 3, FastAPI 0.115, SQLAlchemy 2.0 (async), Alembic, Celery 5,
PostgreSQL 16, Redis 7, RabbitMQ 3.12, MinIO, Prometheus + Grafana,
Docker Compose, GitHub Actions, JMeter.

## Соответствие ТЗ

См. [`docs/scoring.md`](docs/scoring.md) — таблица «пункт ТЗ → где реализовано → ссылки на код».

## Структура

```
.
├── docs/                          # архитектура, БД, scoring
├── infrastructure/
│   ├── grafana/provisioning/      # dashboard.json + datasource (auto-load)
│   ├── prometheus/prometheus.yml
│   └── jmeter/dating_load_test.jmx
├── services/
│   ├── _shared/                   # общая lib: logging, rabbitmq, metrics, events
│   ├── bot-service/               # aiogram 3
│   ├── profile-service/           # CRUD + Alembic + MinIO
│   ├── ranking-service/           # рейтинг + Celery + лента
│   ├── matching-service/          # swipe → match
│   └── notification-service/      # match → push + айсбрейкер
├── docker-compose.yml
├── .github/workflows/ci.yml       # lint + tests + docker build matrix
└── .env.example
```

## Тесты и CI

- Unit-тесты для чистой логики (формулы рейтинга, айсбрейкеры, клавиатуры, реферальные коды) — `services/*/tests/`.
- CI: ruff + pytest + docker build для всех 5 сервисов в матрице.
- Нагрузочный сценарий JMeter — `infrastructure/jmeter/`.

## Лицензия

Учебный проект.
