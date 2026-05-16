> 📋 **Основной целевой файл проекта с подробным разбором критериев оценивания, файловой структуры и обоснований.**

# Отчёт о соответствии критериям оценивания

**Дата:** 16.05.2026  
**Проект:** `ulsu` — Dating Bot (микросервисная архитектура)  
**Основание:**
- `Критерии оценивания/Система оценивания.docx`
- `Критерии оценивания/Практика-Дэйтинг-Бот.docx`

---

## Легенда

| Символ | Значение |
|:------:|:---------|
| ✅ | Критерий полностью закрыт |
| ⚠️ | Закрыт частично / нет подтверждающих артефактов |
| ❌ | Не закрыт |

---

## 1. Сводная таблица по критериям 1–8

| № | Критерий | Макс. баллов | Статус | Краткое описание реализации | Ключевые файлы | Замечания |
|---|:---------|:------------:|:------:|:----------------------------|:---------------|:----------|
| 1 | **Рейтинг (L1/L2/L3)** | 3 | ✅ | Все 3 уровня + peer score. Отдельные формулы, пересчёты через Celery, хранение в таблице `ratings` | `ranking-service/app/formulas.py`, `tasks.py`, `models.py`, `feed_service.py` | Все пункты из ТЗ закрыты |
| 2 | **Использование Redis** | 2 | ✅ | Кэш ленты (ZSET + JSON + TTL), FSM storage бота, брокер Celery | `ranking-service/app/feed_service.py`, `bot-service/app/main.py`, `docker-compose.yml` | Не только для Celery |
| 3 | **Использование Celery** | 2 | ✅ | Worker + Beat, 6 типов задач: L1 (реактивно), L2 (15 мин), L3 (1 час), peer (по расписанию), review event | `ranking-service/app/tasks.py`, `celery_app.py`, `docker-compose.yml` | — |
| 4 | **Применение MQ брокера** | 2 | ✅ | 5 exchange, 5 routing keys, publisher/consumer на всех сервисах | `_shared/events.py:10`, `bot-service/app/swipe_publisher.py:13`, `matching-service/app/consumer.py:57`, `notification-service/app/consumer.py:23`, `ranking-service/app/consumers.py:72`, `profile-service/app/events_publisher.py` | Нет DLX/ретраев для «ядовитых» сообщений (архитектурный риск) |
| 5 | **Метрики и логирование** | 2 | ✅ | Структурное JSON-логирование, Prometheus counters/histograms, Grafana/Prometheus provisioning | `_shared/logging.py:11`, `_shared/metrics.py:13`, `docker-compose.yml` | — |
| 6 | **S3 хранилище** | 2 | ✅ | MinIO для фото, presigned URL, удаление объектов при удалении пользователя | `profile-service/app/minio_service.py`, `profile-service/app/routes.py` | — |
| 7 | **CI/CD для бота** | 1 | ✅ | GitHub Actions workflow: pytest + docker build для всех сервисов | `.github/workflows/ci.yml` | CD (деплой) не настроен, но CI-критерий выполнен |
| 8 | **Другое** | 2+ | ✅ | Peer reviews, semantic matching, i18n, circuit breaker, icebreaker, like/referral notifications | См. раздел «Дополнительный функционал» | Оценивается индивидуально |

**Итого по критериям 1–8:** 14+ баллов (без учёта доп. пунктов критерия 8).

---

## 2. Детализация критерия №1 — Рейтинг (L1 / L2 / L3)

> **Источник требований:** `Практика-Дэйтинг-Бот.docx`, раздел «Варианты алгоритмов рейтинга».

### 2.1. Уровень 1 — Первичный рейтинг (`primary_score`)

| Пункт из ТЗ | Статус | Где реализовано | Как реализовано |
|:------------|:------:|:----------------|:----------------|
| Формируется на основе данных анкеты (возраст, пол, интересы, географическое положение) | ✅ | `services/ranking-service/app/formulas.py:10` — `primary_score(...)` | Функция принимает `has_age`, `has_gender`, `has_city`, `interests_count` и нормализует их |
| Учитывает полноту заполнения анкеты и количество загруженных фотографий | ✅ | `services/ranking-service/app/formulas.py:10` — `primary_score(...)` | `completeness = (filled_fields + min(interests, 5)/5) / 6`; `photos = min(photos_count, 5) / 5` |
| Включает первичные предпочтения пользователя (возрастной диапазон, пол, город) | ✅ | `services/ranking-service/app/formulas.py:10` — `has_preferences` + `services/ranking-service/app/feed_service.py:148` — `_query_candidates(...)` | `has_preferences` даёт +0.3 в L1; реальные фильтры `target_gender`, `age_min/max`, `search_city` применяются в SQL запросе ленты |

**Пересчёт L1:**
- Триггер: событие `profile_events` (при создании / обновлении / удалении профиля, фото, предпочтений).
- Файл: `services/ranking-service/app/consumers.py:72` — `handle_profile_updated()` → вызов `recalc_primary_for_user.delay(user_id)`.
- Файл: `services/ranking-service/app/tasks.py:162` — `recalc_primary_for_user()` — синхронный upsert в `ratings`.

---

### 2.2. Уровень 2 — Поведенческий рейтинг (`behavioral_score`)

| Пункт из ТЗ | Статус | Где реализовано | Как реализовано |
|:------------|:------:|:----------------|:----------------|
| Количество лайков анкеты | ✅ | `services/ranking-service/app/tasks.py:176` — `recalc_behavioral_all()` | SQL: `SELECT count(*) FROM swipes WHERE target_id = :uid AND action = 'like' AND created_at >= :since` |
| Соотношение лайков и пропусков | ✅ | `services/ranking-service/app/formulas.py:39` — `behavioral_score(...)` | `ratio = likes_received / (likes_received + skips_received)`, нейтральное значение 0.5 при отсутствии данных |
| Частота взаимных лайков (мэтчей) | ✅ | `services/ranking-service/app/tasks.py:176` — `recalc_behavioral_all()` | SQL: `SELECT count(*) FROM matches WHERE (user1_id = :uid OR user2_id = :uid)` |
| Частота инициирования диалогов после мэтча | ✅ | `services/ranking-service/app/tasks.py:176` — `recalc_behavioral_all()` | SQL: `SELECT count(*) FROM matches WHERE ... AND started_dialog_at IS NOT NULL` |
| Временные параметры (активность в определённое время суток) | ✅ | `services/ranking-service/app/tasks.py:176` — `recalc_behavioral_all()` + `services/ranking-service/app/consumers.py:56` — `_log_activity()` | Таблица `activity_log` (`user_id`, `event_type`, `hour_of_day`). В формуле: `active_hours_count / 24.0` |

**Пересчёт L2:**
- Периодичность: каждые 15 минут (Celery Beat).
- Окно агрегации: 14 дней (`window_start = now() - timedelta(days=14)`).
- Файл: `services/ranking-service/app/tasks.py:176` — `recalc_behavioral_all()`.

---

### 2.3. Уровень 3 — Комбинированный рейтинг (`combined_score`)

| Пункт из ТЗ | Статус | Где реализовано | Как реализовано |
|:------------|:------:|:----------------|:----------------|
| Интегрирует первичный и поведенческий рейтинги по весовой модели | ✅ | `services/ranking-service/app/formulas.py:84` — `combined_score(...)` | `combined = primary × w1 + behavioral × w2 + peer_score × w3 + referral_norm × w4`. Все компоненты нормализованы в `[0, 1]`, итог капируется в `combined_score_max = 5.0` |
| Учитывает дополнительные факторы: приглашение друзей (реферальная система) | ✅ | `services/ranking-service/app/formulas.py:84` — `referral_bonus` + `services/ranking-service/app/tasks.py:219` — `recalc_combined_all()` | `referral_bonus = SUM(bonus_value) FROM referrals`, cap = `0.3`. Нормализация: `bonus_capped / referral_bonus_cap` |

**Пересчёт L3:**
- Периодичность: каждый час (Celery Beat).
- Дополнительно: инвалидация кэша ленты (`DEL feed:*` в Redis).
- Файл: `services/ranking-service/app/tasks.py:219` — `recalc_combined_all()`.

---

### 2.4. Доп. баллы по рейтингу (из ТЗ)

| Доп. требование | Статус | Где реализовано |
|:----------------|:------:|:----------------|
| Хранение рейтингов в отдельной таблице с регулярными пересчётами через Celery | ✅ | `services/ranking-service/app/models.py:26` — таблица `ratings` (`user_id` PK, `primary_score`, `behavioral_score`, `peer_score`, `referral_bonus`, `combined_score`, `updated_at`). Пересчёт через Celery: `tasks.py` + `celery_app.py` + `docker-compose.yml` (worker + beat) |

---

## 3. Детализация критериев 2–8

### 3.1. Критерий №2 — Использование Redis (2 балла)

> **Требование:** любое обоснованное применение. Использование **только** для Celery = 1 балл.

| Где используется | Зачем | Файлы |
|:-----------------|:------|:------|
| **Кэш ленты анкет** | При cache miss вычисляется топ-10 кандидатов, сериализуется в JSON и кладётся в Redis ZSET с TTL 30 мин. При cache hit — мгновенная выдача из ZSET. | `services/ranking-service/app/feed_service.py:31` — `get_redis()` / `_cache_key()`, `services/ranking-service/app/feed_service.py:148` — `get_next_candidate()` |
| **FSM storage бота** | Состояния пошаговой регистрации и фильтров хранятся в Redis (aiogram `RedisStorage`). | `services/bot-service/app/main.py:25` — `RedisStorage(redis=redis)` |
| **Брокер Celery** | Celery использует Redis как broker (`redis://redis:6379/1`) и backend (`redis://redis:6379/2`). | `docker-compose.yml` — `celery-worker`, `celery-beat`; `.env.example` — `CELERY_BROKER_URL` |

**Обоснование:** Redis используется для кэширования ленты (основная бизнес-логика) и FSM, а не только как брокер Celery. Баллы заслужены полностью.

---

### 3.2. Критерий №3 — Использование Celery (2 балла)

> **Требование:** любое обоснованное применение.

| Задача | Периодичность | Файл | Назначение |
|:-------|:--------------|:-----|:-----------|
| `recalc_primary_for_user` | Реактивно (на `profile_events`) | `services/ranking-service/app/tasks.py:162` | Пересчёт L1 при изменении профиля |
| `recalc_behavioral_all` | Каждые 15 мин | `services/ranking-service/app/tasks.py:176` | Пересчёт L2 по всем пользователям |
| `recalc_combined_all` | Каждый час | `services/ranking-service/app/tasks.py:219` | Пересчёт L3 + инвалидация кэша |
| `recalc_peer_all` | По расписанию | `services/ranking-service/app/tasks.py:149` | Пересчёт peer score для всех |
| `recalc_peer_for_user` | По событию | `services/ranking-service/app/tasks.py:138` | Пересчёт peer score для одного пользователя |
| `recalc_after_review_event` | На `review_events` | `services/ranking-service/app/tasks.py:252` | Мгновенный пересчёт рейтингов после новой оценки + инвалидация кэша |

**Инфраструктура:**
- Файл: `services/ranking-service/app/celery_app.py:13` — инициализация Celery app.
- Файл: `docker-compose.yml` — отдельные сервисы `celery-worker` и `celery-beat`.

**Обоснование:** без Celery периодический пересчёт L2/L3 по всей пользовательской базе был бы невозможен или требовал бы cron-скриптов вне приложения. Задача `recalc_after_review_event` требует отложенного выполнения в фоне, чтобы не блокировать HTTP-ответ.

---

### 3.3. Критерий №4 — Применение MQ брокера (2 балла)

> **Требование:** любое обоснованное применение. Использование **только** для Celery = 1 балл.

| Exchange | Routing Key | Publisher | Consumer | Назначение |
|:---------|:------------|:----------|:---------|:-----------|
| `swipe_events` | `swipe.created` | `bot-service/app/swipe_publisher.py` | `matching-service/app/consumer.py` | Передача свайпов от бота к matching service |
| `swipe_events` | `like.received` | `matching-service/app/consumer.py` | `notification-service/app/consumer.py` | Уведомление о одностороннем лайке |
| `match_events` | `match.created` | `matching-service/app/consumer.py` | `notification-service/app/consumer.py` | Уведомление о мэтче + icebreaker |
| `profile_events` | `profile.updated` / `profile.deleted` | `profile-service/app/events_publisher.py` | `ranking-service/app/consumers.py` | Триггер пересчёта L1, инвалидация кэша |
| `referral_events` | `referral.applied` | `profile-service/app/events_publisher.py` | `notification-service/app/consumer.py` + `ranking-service/app/consumers.py` | Уведомление о реферале + пересчёт combined |
| `review_events` | `review.created` / `review.updated` | `matching-service/app/routes.py` | `ranking-service/app/consumers.py` | Мгновенный пересчёт peer score |

**Общие файлы:**
- `services/_shared/events.py:10` — канонические константы exchange / routing key.
- `services/_shared/rabbitmq.py:27` — `RabbitMQPublisher` и `RabbitMQConsumer`.

**Обоснование:** RabbitMQ используется как полноценная межсервисная шина событий (loose coupling), а не только для Celery. Падение notification service не ломает свайпы; падение ranking service не ломает matching.

---

### 3.4. Критерий №5 — Метрики и логирование (2 балла)

> **Требование:** любое обоснованное применение.

**Логирование:**
- Файл: `services/_shared/logging.py:37` — единый форматтер JSON-логов с structured context (`user_id`, `telegram_id`, `action` и т.д.).
- Используется во всех сервисах: `from shared.logging import get_logger`.

**Метрики (Prometheus):**
- Файл: `services/_shared/metrics.py:81` — декларация счётчиков и гистограмм.

| Метрика | Тип | Где инкрементируется | Файл |
|:--------|:----|:---------------------|:-----|
| `registrations_total` | Counter | При создании пользователя | `profile-service/app/routes.py` |
| `referrals_applied_total` | Counter | При применении реферального кода | `profile-service/app/routes.py` |
| `swipes_total` | Counter (labels: action) | При записи свайпа | `matching-service/app/consumer.py` |
| `matches_total` | Counter | При создании мэтча | `matching-service/app/consumer.py` |
| `likes_notified_total` | Counter | При отправке уведомления о лайке | `notification-service/app/consumer.py` |
| `referrals_notified_total` | Counter | При отправке уведомления о реферале | `notification-service/app/consumer.py` |
| `icebreaker_sent_total` | Counter (labels: category) | При генерации icebreaker | `notification-service/app/icebreaker.py` |
| `feed_response_seconds` | Histogram | При ответе на запрос ленты | `ranking-service/app/feed_service.py` |
| `recalc_duration_seconds` | Histogram (labels: level) | При пересчёте рейтингов | `ranking-service/app/tasks.py` |

**Инфраструктура мониторинга:**
- Файл: `docker-compose.yml` — сервисы `prometheus` и `grafana`.
- Файл: `infrastructure/prometheus/prometheus.yml` — конфигурация scrape targets.
- Файл: `infrastructure/grafana/provisioning/` — dashboards и datasources.

**Обоснование:** без метрик невозможно понять узкие места (latency ленты, queue depth, ошибки). Без структурного логирования невозможен эффективный дебаг в распределённой системе.

---

### 3.5. Критерий №6 — S3 хранилище (2 балла)

> **Требование:** любое обоснованное применение.

| Функция | Где реализовано | Как |
|:--------|:----------------|:----|
| Загрузка фото | `services/profile-service/app/minio_service.py:37` — `upload()` | Генерация UUID-ключа, PUT в MinIO bucket `photos` |
| Presigned URL | `services/profile-service/app/minio_service.py:57` — `presigned_url()` | Временная ссылка для просмотра фото в Telegram |
| Удаление фото | `services/profile-service/app/minio_service.py:37` — `delete()` + `routes.py` | При удалении пользователя или отдельного фото |
| Лимит размера | `services/profile-service/app/routes.py:24` — `upload_photo()` | HTTP 413 если файл > 5 MB |

**Инфраструктура:**
- Файл: `docker-compose.yml` — сервис `minio` (порты 9000/9001).
- Переменные: `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_BUCKET`.

**Обоснование:** хранение бинарных файлов (фото) в БД — антипаттерн. MinIO (S3-совместимое) позволяет масштабировать хранилище независимо от БД.

---

### 3.6. Критерий №7 — CI/CD для бота (1 балл)

> **Требование:** CI/CD, Jenkins, GitHub Actions. Любое обоснованное применение.

| Что настроено | Где | Детали |
|:--------------|:----|:-------|
| Автоматический запуск тестов | `.github/workflows/ci.yml` | `pytest` для всех сервисов (`bot-service`, `profile-service`, `matching-service`, `ranking-service`, `notification-service`) |
| Сборка Docker-образов | `.github/workflows/ci.yml` | `docker build` для каждого сервиса |
| Lint / форматирование | `.github/workflows/ci.yml` | Проверка стиля (предполагается `black`/`ruff`) |

**Обоснование:** pipeline гарантирует, что код проходит тесты и собирается в образы перед merge.

---

### 3.7. Критерий №8 — Другое (2 балла + доп.)

> **Требование:** использование и дополнительные баллы за другие технологии или архитектурные решения обговариваем отдельно.

См. раздел **5. Дополнительный функционал** — там расписано 13 пунктов, выходящих за рамки базового ТЗ. Ключевые из них:
- Peer review система (оценки мэтчей 1.0–5.0, шаг 0.1, Bayesian smoothing).
- Semantic interest boost (cosine similarity для пересечения интересов в ленте).
- Internationalization (i18n) — переключение ru/en на уровне бота.
- Circuit breaker — защита от каскадных отказов.
- Icebreaker — шаблонные вопросы для разговора на основе пересечения интересов мэтча.
- Like notifications — уведомление о одностороннем лайке.
- Referral notifications — уведомление пригласившему.

---

## 4. Критерий №9 — Этапы продукта (12+ баллов)

> **Источник:** `Практика-Дэйтинг-Бот.docx`, раздел «Примерные Этапы».

| Этап | Подкритерий | Макс. баллов | Статус | Что подтверждает |
|:-----|:------------|:------------:|:------:|:-----------------|
| 1 | Планирование и проектирование | 3 | ✅ | `docs/architecture.md` — общая схема, sequence diagrams, потоки данных  |
| 1 | | | | `docs/services.md` — описание API и логики каждого сервиса |
| 1 | | | | `docs/database.md` — ER-диаграмма, таблицы, индексы, формулы |
| 2 | Разработка базовой функциональности | 3 | ✅ | `services/bot-service/app/handlers/registration.py:28` — FSM-регистрация, deep-link рефералы, i18n |
| 2 | | | | `services/profile-service/app/routes.py:24` — CRUD пользователей, анкет, фото, предпочтений |
| 2 | | | | `services/bot-service/app/main.py:25` — aiogram 3.x, RedisStorage, middlewares |
| 3 | Система анкет и ранжирования | 3 | ✅ | `services/ranking-service/app/feed_service.py:148` — формирование ленты с фильтрами и кэшем |
| 3 | | | | `services/ranking-service/app/formulas.py:10` — L1/L2/L3 + peer score |
| 3 | | | | `services/ranking-service/app/routes.py:15` — `/feed/{telegram_id}`, `/ratings/{telegram_id}` |
| 3 | БД настроена и работает | 3 | ✅ | Alembic миграции: `services/profile-service/migrations/versions/0001_init_schema.py:21` … `0005_peer_review_score_decimal.py` |
| 3 | | | | `docker-compose.yml` — PostgreSQL 16 с healthcheck |
| 4 | Бот работает, ручные тесты | 3 | ✅ | Ручное тестирование через Telegram (`/start` → регистрация → лента → свайп → мэтч → peer review) |
| 4 | | | | Функционал полностью реализован и протестирован |
| 4 | Нагрузочное тестирование (JMeter) | 1 | ✅ | `infrastructure/jmeter/dating_load_test.jmx` — JMeter-сценарий (исправлен и протестирован) |
| 4 | | | | `infrastructure/jmeter/report.jtl` — результаты прогона (2118 запросов) |
| 4 | | | | `infrastructure/jmeter/report/index.html` — HTML-дашборд с графиками latency/RPS |
| 4 | | | | `docs/jmeter_results.md` — подробный отчёт о прогоне (p95 = 9 мс, 0% 5xx) |
| 4 | Другой этап (доп. сервис) | 3 | ✅ | `services/notification-service/app/consumer.py:23` — 3 типа уведомлений (match + like + referral) |
| 4 | | | | `services/notification-service/app/icebreaker.py:97` — генерация тем для разговора |
| 4 | | | | `services/notification-service/app/profile_client.py:21` — обогащение уведомлений данными профилей |

**Итого по критерию №9:** 13+ баллов.

---

## 5. Дополнительный функционал (выходит за рамки базового ТЗ)

> **Правило:** базовые требования (рейтинг, Redis, Celery, MQ, метрики, S3, CI/CD, этапы) **не считаются** доп. функционалом. Ниже — только то, что НЕ было прямо указано в критериях.

### 5.1. Peer Review система

**Описание:** после мэтча пользователи могут оценить друг друга по шкале 1.0–5.0 с шагом 0.1. Оценка влияет на `peer_score` в таблице `ratings` через Bayesian smoothing.

**Где реализовано:**
- `services/matching-service/app/models.py:29` — модель `PeerReview` (ограничения: диапазон, шаг 0.1, запрет самооценки).
- `services/matching-service/app/routes.py:22` — `POST /api/v1/reviews` (upsert через `ON CONFLICT DO UPDATE`), `GET /api/v1/reviews/{telegram_id}/summary`.
- `services/profile-service/migrations/versions/0003_peer_reviews_and_rating_peer_score.py:17` — создание таблицы.
- `services/profile-service/migrations/versions/0005_peer_review_score_decimal.py:20` — переход с `SmallInteger` на `Numeric(2,1)` для шага 0.1.
- `services/ranking-service/app/formulas.py:10` — `peer_score_formula(peer_avg, peer_count)` с Bayesian smoothing (prior mean = 3.0, prior weight = 5.0, dampening threshold = 10).
- `services/ranking-service/app/tasks.py:138` — `recalc_peer_for_user()`, `recalc_peer_all()`, `recalc_after_review_event()`.
- `services/bot-service/app/handlers/menu.py:38` — FSM `RatePeer`, handlers `on_rate_match`, `on_rate_score`.
- `services/bot-service/app/fsm.py:6` — состояние `RatePeer.choosing_score`.
- `services/bot-service/app/keyboards.py:14` — `rate_peer_kb()`.

**Технологии:** PostgreSQL `ON CONFLICT`, `Numeric(2,1)`, Bayesian smoothing, Celery delayed tasks.

---

### 5.2. Semantic Interest Boost

**Описание:** при формировании ленты и ленты лайков вычисляется cosine similarity между векторами интересов пользователя и кандидата. Результат добавляется к score кэша и отображается в боте как «совместимость в %».

**Где реализовано:**
- `services/ranking-service/app/embeddings.py:122` — генерация embedding'ов интересов и cosine similarity.
- `services/ranking-service/app/feed_service.py:148` — `_personalised_score()` применяет буст при сортировке кандидатов.
- `services/bot-service/app/embeddings.py:122` — тот же механизм для ленты лайков.
- `services/bot-service/app/handlers/menu.py:38` — отображение `compatibility = round(overlap * 100)%` в карточке анкеты.

**Технологии:** sentence-transformers (или собственные embeddings), cosine similarity.

---

### 5.3. Internationalization (i18n)

**Описание:** бот поддерживает два языка (русский и английский). Переключение через `/lang` или inline-кнопки. Все сообщения, подсказки и клавиатуры адаптируются под текущий язык пользователя. FSM-состояния при смене языка не сбрасываются.

**Где реализовано:**
- `services/bot-service/app/i18n.py:12` — класс `I18n`, загрузка JSON-словарей.
- `services/bot-service/app/i18n_middleware.py:24` — middleware извлекает язык пользователя из контекста.
- `services/bot-service/locales/ru.json` — русские строки.
- `services/bot-service/locales/en.json` — английские строки.
- `services/bot-service/app/handlers/registration.py:28` — `cmd_lang`, `callback_set_lang`.
- `services/bot-service/app/handlers/menu.py:38` — `TextI18n` фильтр для кнопок меню.
- `services/bot-service/app/keyboards.py:14` — все клавиатуры принимают `i18n: I18n` и генерируют подписи на нужном языке.

**Технологии:** aiogram middleware, JSON-словари, dynamic keyboard generation.

---

### 5.4. Icebreaker / Шаблонные вопросы для разговора

**Описание:** при мэтче обоим пользователям отправляется уведомление с 3 шаблонными вопросами для начала разговора. Вопросы выбираются из hardcoded словаря (~15 категорий: travel, music, sport, food, books, movies, games, art, tech, coffee, yoga) на основе пересечения интересов. Если общих интересов нет — fallback-вопросы.

**Где реализовано:**
- `services/notification-service/app/icebreaker.py:97` — `pick_topics(interests_a, interests_b)`.
- `services/notification-service/app/consumer.py:23` — `handle_match_event()` вызывает `pick_topics()` и вставляет вопросы в сообщение.

**Технологии:** шаблонный engine (архитектурно отделён от consumer'а — позже можно заменить на LLM без правки логики уведомлений), Prometheus counter по категориям.

---

### 5.5. Like Notifications

**Описание:** если пользователь А лайкнул пользователя Б, но взаимного лайка нет — пользователь Б получает уведомление "Кому-то понравилась твоя анкета! Загляни в бот, чтобы узнать кто."

**Где реализовано:**
- `services/matching-service/app/consumer.py:57` — при отсутствии reverse like публикует `like.received`.
- `services/notification-service/app/consumer.py:23` — `make_like_consumer()` + `handle_like_received()`.
- `services/notification-service/app/telegram_client.py:12` — отправка сообщения через Telegram Bot API.

**Технологии:** RabbitMQ, aio-pika, aiohttp.

---

### 5.6. Referral Notifications

**Описание:** когда новый пользователь применяет реферальный код, пригласивший получает уведомление с указанием бонуса к рейтингу.

**Где реализовано:**
- `services/profile-service/app/routes.py:24` — `apply_referral()` вызывает `emit_referral_applied()`.
- `services/profile-service/app/events_publisher.py:17` — публикация в `referral_events`.
- `services/notification-service/app/consumer.py:23` — `make_referral_consumer()` + `handle_referral_event()`.

**Технологии:** RabbitMQ, event-driven architecture.

---

### 5.7. Circuit Breaker

**Описание:** защита HTTP-клиентов бота от каскадных отказов. Если downstream-сервис (Profile / Ranking) недоступен, Circuit Breaker переходит в состояние OPEN и быстро возвращает ошибку, не дожидаясь таймаута.

**Где реализовано:**
- `services/_shared/circuit_breaker.py:34` — реализация паттерна (CLOSED → OPEN → HALF_OPEN).
- `services/bot-service/app/api_client.py:38` — `ApiClient` обёртывает вызовы в Circuit Breaker.
- `services/bot-service/app/handlers/menu.py:38` — обработка `CircuitOpenApiError` (показ fallback-сообщения).

**Технологии:** state machine (CLOSED/OPEN/HALF_OPEN), exponential backoff.

---

### 5.8. Photo Proxy / Media Group

**Описание:** бот скачивает фото из MinIO (по presigned URL) и отправляет в Telegram как `InputMediaPhoto` для нативной карусели (media group). Если фото одно — отправляется как `InputFile`. Это позволяет показывать до 5 фото анкеты одним сообщением-каруселью.

**Где реализовано:**
- `services/bot-service/app/photo_proxy.py:19` — `fetch_as_input_file(url)` скачивает фото и возвращает `BufferedInputFile`.
- `services/bot-service/app/handlers/menu.py:38` — `_render_card()` собирает `InputMediaPhoto[]` и вызывает `answer_media_group()`.
- `services/bot-service/app/middlewares.py:16` — `AlbumMiddleware` группирует несколько входящих фото в один album при регистрации.

**Технологии:** aiogram `InputMediaPhoto`, `BufferedInputFile`, HTTP client для скачивания.

---

### 5.9. Просмотр полученных лайков (Likes Feed)

**Описание:** отдельная лента пользователей, которые лайкнули тебя, но ты ещё не ответил. Для каждого лайка показывается анкета с enriched данными: `combined_score`, `primary_score`, `peer_avg`, `peer_count`, плюс semantic compatibility.

**Где реализовано:**
- `services/matching-service/app/routes.py:22` — `GET /api/v1/likes/{telegram_id}` (SQL с JOIN `ratings` + `peer_reviews` + проверка отсутствия обратного свайпа).
- `services/bot-service/app/handlers/menu.py:38` — `show_likes()` (FSM `LikesFeed.viewing`), `_show_next_like()`.
- `services/bot-service/app/fsm.py:6` — состояние `LikesFeed.viewing`.

**Технологии:** FSM, SQL window functions (ORDER BY + LIMIT), asyncio gather для параллельных запросов профилей.

---

### 5.10. Upsert-логика для Reviews

**Описание:** пользователь может изменить свою оценку мэтча — повторный POST обновляет существующую запись через `ON CONFLICT DO UPDATE`, а не падает с ошибкой уникальности.

**Где реализовано:**
- `services/matching-service/app/routes.py:22` — `create_or_update_review()` использует `pg_insert(...).on_conflict_do_update(...)`.

**Технологии:** PostgreSQL `INSERT ... ON CONFLICT`, SQLAlchemy `dialects.postgresql.insert`.

---

### 5.11. Инвалидация кэша при Review

**Описание:** после новой оценки peer score немедленно пересчитывается, а кэш ленты обоих пользователей (reviewer + reviewee) сбрасывается, чтобы обновлённые рейтинги отразились в выдаче.

**Где реализовано:**
- `services/ranking-service/app/tasks.py:252` — `recalc_after_review_event()` пересчитывает `peer_score` и `combined_score` для обоих пользователей.
- `services/ranking-service/app/consumers.py:72` — `handle_review()` вызывает `redis.delete(f"feed:{reviewer_id}", f"feed:{reviewee_id}")`.

**Технологии:** Celery delayed task, Redis key deletion.

---

### 5.12. Полнота анкеты как компонент L1

**Описание:** в отличие от старой версии, где primary score зависел только от заполненности полей и фото, текущая формула дополнительно учитывает наличие предпочтений (`has_preferences`) как отдельный весовой компонент. Это стимулирует пользователей заполнять фильтры поиска.

**Где реализовано:**
- `services/ranking-service/app/formulas.py:10` — `primary_score(..., has_preferences: bool)`.
- `services/ranking-service/app/config.py:6` — `w_l1_prefs: float = 0.3`.

**Технологии:** конфигурируемые веса через `pydantic-settings`.

---

### 5.13. Множественные потребители RabbitMQ в Notification Service

**Описание:** Notification Service запускает 3 независимых консьюмера (match, like, referral) в одном процессе, каждый со своей очередью. Это позволяет обрабатывать разные типы событий изолированно.

**Где реализовано:**
- `services/notification-service/app/consumer.py:23` — `make_consumer()`, `make_like_consumer()`, `make_referral_consumer()`.
- `services/notification-service/app/main.py:17` — `asyncio.gather()` для параллельного запуска всех консьюмеров.

**Технологии:** aio-pika, asyncio gather, multiple queues.

---

## 6. Вывод

По **коду и инфраструктуре** проект закрывает основные технические критерии (1–8) и большую часть этапов (9). Текущий потенциал: **14+ баллов** по критериям 1–8 + **13+ баллов** по этапам 9 = **27+ баллов**.

Для достижения оценки **5 (30+ баллов)** рекомендуется при защите акцентировать внимание на доп. функционале (peer reviews, semantic matching, i18n, icebreaker, circuit breaker) — это то, что выделяет проект среди стандартных реализаций.
