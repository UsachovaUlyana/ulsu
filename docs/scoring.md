# Соответствие ТЗ → реализация (для зачёта)

Источник критериев: `zadanie.md`. Максимум по обязательной части — 33 балла.

## Сводная таблица

| Пункт ТЗ | Балл | Где реализовано |
|---|---:|---|
| **1. Рейтинг — все 3 уровня, все пункты** | **3** | `services/ranking-service/app/formulas.py` (чистые функции), `app/tasks.py` (Celery пересчёт), `app/feed_service.py` (сортировка по `combined_score`) |
| **2. Redis (обоснованно)** | **2** | (а) FSM-storage бота `bot-service/app/main.py:RedisStorage`, (б) кэш ленты `ranking-service/app/feed_service.py:get_redis()` ZSET TTL 30 мин, (в) брокер Celery — `redis://redis:6379/1`. Не только под Celery → 2 балла. |
| **3. Celery (обоснованно)** | **2** | `ranking-service/app/celery_app.py` + `tasks.py`: beat-расписание 15 мин (recalc_behavioral) и 60 мин (recalc_combined + invalidate feed). Также on-demand recalc после `referral_events`. |
| **4. RabbitMQ (обоснованно)** | **2** | 4 топика (`shared/events.py`): swipe_events, match_events, profile_events, referral_events. Реальные publishers и consumers во всех сервисах. Не только под Celery → 2 балла. |
| **5. Метрики + логирование** | **2** | structlog (JSON) везде через `shared/logging.py`. Prometheus FastAPI instrumentator + бизнес-метрики (`shared/metrics.py`): swipes_total, matches_total, feed_response_seconds histogram, recalc_duration_seconds, icebreaker_sent_total. Grafana с авто-провижионингом дашборда `infrastructure/grafana/`. |
| **6. S3 (MinIO)** | **2** | `profile-service/app/minio_service.py` — upload, presigned URLs, delete. Bot скачивает по presigned URL и шлёт в Telegram через `BufferedInputFile` (TG-серверы не достают `minio:9000`). |
| **7. CI/CD** | **1** | `.github/workflows/ci.yml`: матрица 5×{lint(ruff), pytest, docker-build}. Триггер push/PR. |
| **8. Другое (доп. баллы)** | **+8** | См. ниже разбивку. |
| **9. Этапы продукта** | **+19** | См. разбивку. |

**Итого: 3+2+2+2+2+2+1+8+19 = ≈41 балл** (порог 5 — 30+).

---

## Пункт 1 — Рейтинг детально

ТЗ требует «по 1 пункту из каждого уровня — 1 балл, 2 — 2 балла, **все** — 3 балла».

### Уровень 1 (primary) — `formulas.primary_score()`

| Подпункт ТЗ | Реализация |
|---|---|
| Возраст / пол / интересы / гео | Хранятся в `profiles`, попадают в `completeness` (`has_age`, `has_gender`, `interests_count`) |
| Полнота анкеты + кол-во фото | `completeness` (5 текстовых полей) + `photos` (нормирован к 1.0 на 5 фото) |
| Первичные предпочтения | `has_preferences` flag (UPSERT в `preferences` после регистрации) |

Формула: `0.4·completeness + 0.3·photos + 0.3·preferences`. Тригер пересчёта — `profile_events` через RabbitMQ.

### Уровень 2 (behavioral) — `formulas.behavioral_score()`

| Подпункт ТЗ | Реализация |
|---|---|
| Кол-во лайков анкеты | `likes_received` (COUNT swipes WHERE target_id=user AND action='like') |
| Лайки/пропуски ratio | `like_ratio = likes / (likes + skips)` |
| Частота мэтчей | `mutual_matches` (COUNT matches WHERE user участвует) |
| Частота инициирования диалогов | `dialogs_started` (COUNT matches WHERE started_dialog_at IS NOT NULL) |
| Активность по времени суток | `active_hours_count` (DISTINCT hour_of_day FROM activity_log) |

Формула: `0.3·likes + 0.3·ratio + 0.2·mutual + 0.1·dialog + 0.1·activity`. Пересчитывается Celery-beat-задачей `recalc_behavioral_all` каждые 15 минут.

### Уровень 3 (combined) — `formulas.combined_score()`

| Подпункт ТЗ | Реализация |
|---|---|
| Комбинирование L1 + L2 | `0.3·L1 + 0.6·L2` |
| Реферальная система | `+0.1·min(referral_bonus, 0.3)` — суммы из таблицы `referrals` |

Beat-задача `recalc_combined_all` каждый час + `redis DEL feed:*` (инвалидация ленты).

---

## Пункт 8 — Другое

| Дополнение | Баллы | Где |
|---|---:|---|
| Реферальная система с уникальными кодами и анти-фрод (one-shot per invitee) | +2 | `profile-service/app/crud.py:create_referral`, `routes.py:apply_referral`, deep-link `/start ref_<code>` в боте |
| AI-айсбрейкеры (шаблонные, готово к LLM) | +2 | `notification-service/app/icebreaker.py`, ~50 шаблонов под 13 категорий + fallback |
| Гео-фильтрация Haversine (без PostGIS) | +2 | `ranking-service/app/formulas.py:haversine_km`, `feed_service.py:_filter_by_distance` + UI-кнопки 5/10/25/50/100/∞ |
| Shared-библиотека (logging/rmq/metrics/events) | +2 | `services/_shared/` — единый стиль, нет copy-paste между сервисами |

---

## Пункт 9 — Этапы продукта

| Этап | Балл | Чем закрыт |
|---|---:|---|
| 1. Планирование и проектирование | 3 | `docs/architecture.md`, `docs/services.md`, `docs/database.md` (mermaid-диаграммы), 8 таблиц БД спроектированы заранее |
| 2. Базовая функциональность | 3 | bot-service регистрация (8 шагов FSM), profile-service CRUD, MinIO, RabbitMQ events, Postgres via Alembic |
| 3. Анкеты + ранжирование | 3 | CRUD анкет (PUT/POST/DELETE с миграциями), `ranking-service/feed_service.py` (фильтр + ранжирование + кэш Redis ZSET), интеграция бот ↔ ranking через REST + RabbitMQ |
| 4. БД настроена + схема | 3 | PostgreSQL 16 в compose с healthcheck, Alembic-миграция `0001_init_schema.py` создаёт ВСЕ 8 таблиц атомарно при старте profile-service |
| 5. Бот работает + ручные тесты | 3 | Полный E2E: регистрация → лента (если есть кандидаты) → свайп → мэтч → пуш с айсбрейкером |
| 6. JMeter | 1 | `infrastructure/jmeter/dating_load_test.jmx` + README. 70/30 GET feed/ratings, параметризован |
| 7. Доп. этап: notification-service | 3 | Полноценный consumer-сервис с Telegram API клиентом, prometheus metrics на отдельном порту |

---

## Где смотреть на работающую систему

После `docker-compose up -d`:

| Что | URL | Логин/пароль |
|---|---|---|
| Бот в Telegram | t.me/<твой_бот> | — |
| Profile API + Swagger | http://localhost:8001/docs | — |
| Ranking API + Swagger | http://localhost:8002/docs | — |
| Matching API + Swagger | http://localhost:8003/docs | — |
| MinIO console | http://localhost:9001 | minio_user / minio_pass |
| RabbitMQ management | http://localhost:15672 | dating_user / dating_pass |
| Prometheus | http://localhost:9090 | — |
| Grafana | http://localhost:3000 | admin / admin |
