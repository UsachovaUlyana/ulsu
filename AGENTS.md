# AGENTS.md — Dating Bot (Ulsu)

> Файл для AI-агентов. Вся документация, комментарии в коде и сообщения коммитов ведутся на **русском языке**.

---

## 1. Обзор проекта

Микросервисный Telegram-бот знакомств с прозрачным ранжированием, гео-фильтрацией, реферальной системой и айсбрейкерами после мэтча.

- **Язык**: Python 3.11
- **Архитектура**: 5 микросервисов + общая библиотека `services/_shared/`
- **Взаимодействие**: REST API (синхронно) + RabbitMQ (асинхронно)
- **База данных**: одна PostgreSQL 16 на все сервисы (8 таблиц)
- **Хранилище фото**: MinIO (S3-совместимое)
- **Кэш / FSM / Celery**: Redis 7
- **Мониторинг**: Prometheus + Grafana
- **Контейнеризация**: Docker Compose

---

## 2. Структура репозитория

```
.
├── docs/                          # Архитектурная документация (рус.)
│   ├── architecture.md            # Схемы потоков данных (Mermaid)
│   ├── services.md                # Описание каждого сервиса
│   ├── database.md                # ER-диаграмма, формулы рейтинга
│   └── scoring.md                 # Соответствие ТЗ → файлам
├── infrastructure/
│   ├── grafana/provisioning/      # Автозагрузка datasource + dashboard
│   ├── prometheus/prometheus.yml  # Список scrape-таргетов
│   └── jmeter/                    # Нагрузочный тест (JMX + README)
├── services/
│   ├── _shared/                   # Общая библиотека (logging, rmq, metrics, events, settings)
│   ├── bot-service/               # Telegram-бот (aiogram 3)
│   ├── profile-service/           # CRUD анкет, фото, Alembic-миграции
│   ├── ranking-service/           # Рейтинг, лента, Celery
│   ├── matching-service/          # Свайпы, детект мэтчей
│   └── notification-service/      # Уведомления + айсбрейкеры
├── docker-compose.yml             # Полный стек (infra + app + celery)
├── .env.example                   # Шаблон переменных окружения
├── README.md                      # Человекочитаемое описание
└── SETUP.md                       # Инструкция по запуску
```

---

## 3. Технологический стек

| Компонент | Технология | Где используется |
|:---|:---|:---|
| Язык | Python 3.11 | Все сервисы |
| Telegram Bot | aiogram 3.x | `bot-service` |
| REST API | FastAPI 0.115 | `profile`, `ranking`, `matching` |
| ORM | SQLAlchemy 2.0 (async) | `profile`, `ranking`, `matching` |
| Миграции | Alembic | `profile-service` (единая точка правды) |
| БД | PostgreSQL 16 | Общая на все сервисы |
| Кэш / FSM / Celery broker | Redis 7 | `bot-service` (FSM), `ranking-service` (кэш ленты + Celery) |
| Очереди | RabbitMQ 3.12 | 4 топика: `swipe_events`, `match_events`, `profile_events`, `referral_events` |
| S3-фото | MinIO | `profile-service` |
| Периодические задачи | Celery 5.3 + Beat | `ranking-service` |
| Логирование | structlog (JSON) | Все сервисы через `_shared/logging.py` |
| Метрики | prometheus-client + FastAPI instrumentator | `_shared/metrics.py` |
| Тесты | pytest | `services/*/tests/` |

---

## 4. Как запустить

### 4.1 Подготовка

```bash
cp .env.example .env
# Отредактировать TELEGRAM_BOT_TOKEN (получить у @BotFather)
```

### 4.2 Подъём стека

```bash
docker-compose up -d
docker-compose ps
```

Поднимается:
- PostgreSQL (`:55432`), Redis (`:6379`), RabbitMQ (`:5672` + management `:15672`)
- MinIO (`:9000` + console `:9001`)
- Prometheus (`:9090`), Grafana (`:3000`, admin/admin)
- `profile-service` (`:8001`), `ranking-service` (`:8002`), `matching-service` (`:8003`)
- `bot-service`, `notification-service`
- Celery Worker + Celery Beat

### 4.3 Проверка API

```bash
curl http://localhost:8001/health   # profile
curl http://localhost:8002/health   # ranking
curl http://localhost:8003/health   # matching
```

### 4.4 Остановка

```bash
docker-compose down          # остановить
docker-compose down -v       # остановить и удалить ВСЕ данные (БД, S3, Redis)
```

---

## 5. Архитектура сервисов

### 5.1 Сервисы

| Сервис | Порт | Dockerfile | Назначение |
|:---|:---|:---|:---|
| `bot-service` | — | `services/bot-service/Dockerfile` | UI бота, FSM-регистрация, свайпы, меню |
| `profile-service` | 8001 | `services/profile-service/Dockerfile` | CRUD анкет, фото в MinIO, предпочтения, рефералы |
| `ranking-service` | 8002 | `services/ranking-service/Dockerfile` | 3-уровневый рейтинг, кэш ленты Redis, Celery |
| `matching-service` | 8003 | `services/matching-service/Dockerfile` | Запись свайпов, детект взаимных лайков |
| `notification-service` | — | `services/notification-service/Dockerfile` | Consumer `match_events`, пуши в TG, айсбрейкеры |

### 5.2 Потоки данных (кратко)

1. **Регистрация**: User → TG → `bot-service` → REST `profile-service` → PostgreSQL. Фото → MinIO. При обновлении профиля публикуется `profile_events` → `ranking-service` пересчитывает L1-рейтинг.
2. **Лента**: `bot-service` → REST `ranking-service`. Если кэш Redis пуст — полный SQL-расчёт + `ZADD` топ-10 в Redis (TTL 30 мин). Если есть — `ZPOPMAX`.
3. **Свайп**: `bot-service` публикует `swipe_events` в RabbitMQ. Параллельно:
   - `matching-service` записывает свайп, проверяет взаимный лайк → при мэтче публикует `match_events`.
   - `ranking-service` обновляет поведенческий рейтинг (L2).
4. **Мэтч**: `match_events` → `notification-service` шлёт обоим уведомление в Telegram + 3 айсбрейкера по общим интересам.
5. **Периодический пересчёт**: Celery Beat каждые 15 мин → `recalc_behavioral_all`, каждый час → `recalc_combined_all` + инвалидация кэша ленты.

### 5.3 RabbitMQ — канонические имена

Импортировать из `shared.events` (`services/_shared/events.py`), не хардкодить строки:

```python
from shared.events import (
    EXCHANGE_SWIPES, EXCHANGE_MATCHES, EXCHANGE_PROFILES, EXCHANGE_REFERRALS,
    RK_SWIPE_CREATED, RK_MATCH_CREATED, RK_PROFILE_UPDATED, RK_REFERRAL_APPLIED,
)
```

Каждый exchange — `durable` + `TOPIC`. Сообщения — `persistent` + JSON.

---

## 6. Общая библиотека `_shared/`

В Docker-образ каждого сервиса `services/_shared/` копируется в `/app/shared` и доступен как пакет `shared`.

- **`shared/settings.py`** — базовый `CommonSettings` (pydantic-settings, `.env`, `extra="ignore"`). Каждый сервис наследует и добавляет свои поля.
- **`shared/logging.py`** — `configure_logging(service_name, level)` + `get_logger(name)`. Структурный JSON-лог через structlog.
- **`shared/metrics.py`** — фабрики Prometheus-метрик (`swipes_total`, `matches_total`, `feed_response_seconds`, …) и `setup_fastapi_metrics(app)`.
- **`shared/events.py`** — константы exchange / routing-key.
- **`shared/rabbitmq.py`** — `RabbitMQPublisher` и `RabbitMQConsumer` поверх `aio-pika`. Robust-коннекшн, reconnect, prefetch=16. При ошибке обработки сообщение **не requeue** — логируется и дропается (нет DLX в текущей конфигурации).

---

## 7. База данных

### 7.1 Схема

8 таблиц: `users`, `profiles`, `photos`, `preferences`, `swipes`, `matches`, `ratings`, `referrals`.

Подробное описание, индексы, constraints — в `docs/database.md`.

### 7.2 Миграции

Единая точка правды — `profile-service`. При старте контейнера выполняется:
```bash
alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8001
```

Инициализационная миграция: `services/profile-service/migrations/versions/0001_init_schema.py` (создаёт все 8 таблиц).

Другие сервисы используют те же таблицы через свои ORM-модели, но **не ведут собственных миграций**.

---

## 8. Рейтинг (3 уровня)

Реализация — `services/ranking-service/app/formulas.py` (чистые функции, без I/O).

| Уровень | Функция | Пересчёт |
|:---|:---|:---|
| L1 — primary | `primary_score(...)` | Реактивно на `profile_events` (Celery task `recalc_primary_for_user`) |
| L2 — behavioral | `behavioral_score(...)` | Celery Beat каждые 15 мин (`recalc_behavioral_all`) |
| L3 — combined | `combined_score(...)` | Celery Beat каждый час (`recalc_combined_all`) + инвалидация `feed:*` в Redis |

Веса настраиваются через `Settings` в `ranking-service/app/config.py`.

Формулы детально расписаны в `docs/database.md`.

---

## 9. Стиль кода и конвенции

### 9.1 Обязательно в каждом файле

```python
from __future__ import annotations
```

### 9.2 Импорты

- Внутри сервиса — относительные (`from .config import settings`).
- Общая библиотека — `from shared.logging import get_logger`.
- Внешние — стандартные библиотеки → third-party → local.

### 9.3 Настройки

Каждый сервис имеет `app/config.py`:
```python
from shared.settings import CommonSettings

class Settings(CommonSettings):
    ...

settings = Settings()
```

`CommonSettings` читает `.env` (`env_file=".env"`, `extra="ignore"`).

### 9.4 Логирование

```python
from shared.logging import configure_logging, get_logger

configure_logging("service-name", settings.log_level)
logger = get_logger(__name__)

logger.info("event_description", key="value")
```

Логи — JSON, stdout.

### 9.5 Метрики

FastAPI-сервисы: `setup_fastapi_metrics(app)` → автоэндпоинт `/metrics`.
`notification-service`: `start_http_server(settings.metrics_port)` (чистый prometheus-client).

---

## 10. Тестирование

### 10.1 Структура

```
services/<service>/tests/
├── conftest.py          # Патчит sys.path для импорта shared/
└── test_*.py
```

### 10.2 Запуск

```bash
# Из корня сервиса (пример для ranking-service)
cd services/ranking-service
python -m pytest tests/
```

Каждый `conftest.py` добавляет `../../_shared` в `sys.path` и вручную регистрирует модуль `shared` через `importlib.util`, потому что `_shared` не является installable-пакетом.

### 10.3 Что тестируется

- **Чистая логика** (без I/O): формулы рейтинга, клавиатуры бота, генерация реферальных кодов, айсбрейкеры, порядок пар в мэтчах.
- Интеграционных / E2E-тестов в репозитории **нет**.

### 10.4 CI/CD

В документации (`docs/scoring.md`, `README.md`) упоминается `.github/workflows/ci.yml` (матрица lint + pytest + docker build).
**Фактически в репозитории `.github/` отсутствует** (директория есть в `.gitignore`). Если добавляешь CI — создай файл заново.

---

## 11. Docker-сборка

Контекст сборки — **корень репозитория** (не папка сервиса):

```yaml
build:
  context: .
  dockerfile: services/<service>/Dockerfile
```

Это необходимо, чтобы скопировать `services/_shared/` в образ.

В Dockerfile всегда:
```dockerfile
COPY services/<service>/requirements.txt /app/requirements.txt
RUN pip install ...
COPY services/_shared /app/shared
COPY services/<service> /app/
ENV PYTHONPATH=/app
```

---

## 12. Мониторинг

- **Prometheus** (`http://localhost:9090`) — скрейпит `/metrics` с `profile-service:8001`, `ranking-service:8002`, `matching-service:8003`, `notification-service:8004`.
- **Grafana** (`http://localhost:3000`, admin/admin) — авто-провижионинг datasource + dashboard из `infrastructure/grafana/provisioning/`.
- **RabbitMQ Management** (`http://localhost:15672`, dating_user/dating_pass).
- **MinIO Console** (`http://localhost:9001`, minio_user/minio_pass).

---

## 13. Безопасность и ограничения

- **RabbitMQ**: при ошибке обработки сообщение дропается (нет DLX). Не отправляй критичные события без дополнительной надёжности.
- **Фото**: бот не отдаёт прямую ссылку на MinIO. `profile-service` генерирует presigned URL, бот скачивает файл и отправляет в Telegram через `BufferedInputFile`.
- **Рефералы**: один пользователь может быть приглашён только один раз (`referrals.referred_id UNIQUE`). Бонус каппирован (`referral_bonus_cap = 0.3` в combined-формуле).
- **Rate limiting**: в `bot-service` на свайпы — `swipe_rate_limit_per_min = 30` (можно настроить через env).
- **Celery**: использует `task_acks_late=True` + `worker_prefetch_multiplier=1` для безопасного перезапуска воркера.

---

## 14. Полезные команды

```bash
# Логи сервиса
docker logs dating-bot-service -f
docker logs dating-profile-service -f
docker logs dating-ranking-service -f
docker logs dating-celery-worker -f

# Перезапуск одного сервиса
docker-compose restart bot-service

# Зайти в БД
docker exec -it dating-postgres psql -U dating_user -d dating_bot

# Зайти в Redis
docker exec -it dating-redis redis-cli

# Alembic (изнутри контейнера profile-service)
docker exec -it dating-profile-service alembic revision --autogenerate -m "msg"
docker exec -it dating-profile-service alembic upgrade head

# pytest локально (пример)
cd services/ranking-service && python -m pytest tests/
```

---

## 15. Что нужно знать при редактировании

1. **Добавляешь новый сервис?** Создай `services/<name>/`, скопируй паттерн `app/config.py`, `app/main.py`, `requirements.txt`, `Dockerfile`. Обязательно добавь копирование `services/_shared` в Dockerfile. Добавь сервис в `docker-compose.yml`.
2. **Меняешь схему БД?** Делай это **только** в `profile-service/migrations/versions/`. Обнови ORM-модели в других сервисах, если они используют изменённые таблицы.
3. **Добавляешь новый RabbitMQ exchange?** Добавь константу в `services/_shared/events.py` и импортируй её во всех publisher/consumer.
4. **Добавляешь метрику?** Используй фабрики из `shared/metrics.py` — Grafana dashboard автоматически подхватит, если имя начинается с `dating_`.
5. **Пишешь тесты?** Добавь `conftest.py` с патчем `sys.path` для `shared/`, как в существующих сервисах. Тестируй чистые функции; для интеграции нужен запущенный Docker Compose.
