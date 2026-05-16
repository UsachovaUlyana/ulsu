# Отчёт о соответствии критериям оценивания

Дата проверки: 16.05.2026  
Репозиторий: `ulsu`  
Основание: документы из папки `Критерии оценивания/`:
- `Система оценивания.docx`
- `Практика-Дэйтинг-Бот.docx`

## Легенда статусов
- `✅` — критерий закрыт
- `⚠️` — закрыт частично (есть существенные пробелы/регрессии)
- `❌` — не закрыт

## Сводка по критериям

| № | Критерий | Статус | Что сделано | Что не закрыто / риск |
|---|---|---|---|---|
| 1 | Рейтинг (L1/L2/L3) | ✅ | Есть реализация L1/L2/L3 формул и пересчётов (`ranking-service`) | L3 учитывает `primary + behavioral + referral + peer`; существенных пробелов не выявлено |
| 2 | Redis | ✅ | Redis используется для FSM бота, кэша ленты (ZSET), Celery broker/result | Существенных пробелов не найдено |
| 3 | Celery | ✅ | Есть воркер, beat, периодические задачи пересчётов (15 мин/час) | Существенных пробелов не найдено |
| 4 | MQ брокер | ✅ | RabbitMQ используется межсервисно (swipe/match/profile/referral/review events) | Нет DLX/ретраев на “ядовитые” сообщения (архитектурный риск, но критерий закрывает) |
| 5 | Метрики и логирование | ✅ | Structlog JSON + Prometheus метрики + Grafana/Prometheus provisioning | Рекомендуется добавить метрики бизнес-ошибок по ключевым сценариям |
| 6 | S3 хранилище | ✅ | MinIO для фото, presigned URL, удаление из хранилища | Существенных пробелов не найдено |
| 7 | CI/CD | ❌ | В документации заявлено наличие CI | Файла `.github/workflows/ci.yml` в репозитории нет, `.github/` игнорируется |
| 8 | Другое (доп. пункты) | ✅ | Есть peer-review система, уведомления о лайках/мэтчах, шаблонные айсбрейкеры, мониторинг | Для максимального эффекта стоит добавить E2E и авто-проверки |
| 9 | Этапы продукта | ⚠️ | Этапы 1–4 в целом реализованы, сервисы поднимаются в compose | Есть функциональные регрессии в регистрации и разрывы между документацией и кодом |

## Детализация по пунктам

### 1) Рейтинг (L1/L2/L3) — `✅ закрыт`

**Что есть:**
- L1 (профиль/полнота/фото/префы): `services/ranking-service/app/formulas.py`
- L2 (лайки/скипы/мэтчи/активность): `services/ranking-service/app/formulas.py`, `services/ranking-service/app/tasks.py`
- L3 (combined + referral + peer): `services/ranking-service/app/formulas.py`, `services/ranking-service/app/tasks.py`

**Текущее состояние L3:**
- В `combined_score(...)` учитываются все 4 сигнала: `L1 + L2 + referral + peer`:  
  `services/ranking-service/app/formulas.py`
- Веса L3 выставлены как `0.3/0.5/0.1/0.1` (`L1/L2/referral/peer`):  
  `services/ranking-service/app/config.py`
- Unit-тесты синхронизированы с сигнатурой и проверяют cap referral + влияние L1/peer:  
  `services/ranking-service/tests/test_formulas.py`

### 2) Redis — `✅ закрыт`

Использование обоснованное и не ограничено Celery:
- FSM бота: `services/bot-service/app/main.py`
- Кэш ленты (ZSET + TTL): `services/ranking-service/app/feed_service.py`
- Celery broker/result backend: `docker-compose.yml`, `services/ranking-service/app/config.py`

### 3) Celery — `✅ закрыт`

Есть регулярные и реактивные задачи:
- Настройка Celery + beat расписание: `services/ranking-service/app/celery_app.py`
- Задачи L1/L2/L3 + peer: `services/ranking-service/app/tasks.py`
- Отдельные контейнеры `celery-worker`, `celery-beat`: `docker-compose.yml`

### 4) MQ брокер — `✅ закрыт`

RabbitMQ применён как межсервисная шина событий:
- Канонические exchanges/routing keys: `services/_shared/events.py`
- Публикация свайпов: `services/bot-service/app/swipe_publisher.py`
- Обработка свайпов/мэтчей: `services/matching-service/app/consumer.py`
- Консьюмеры ranking/notification: `services/ranking-service/app/consumers.py`, `services/notification-service/app/consumer.py`

### 5) Метрики и логирование — `✅ закрыт`

- Единый JSON-лог: `services/_shared/logging.py`
- Метрики Prometheus: `services/_shared/metrics.py`
- `/metrics` в FastAPI сервисах + HTTP metrics server в notification-service
- Prometheus/Grafana provisioning: `infrastructure/prometheus/prometheus.yml`, `infrastructure/grafana/provisioning/`

### 6) S3 хранилище — `✅ закрыт`

- MinIO клиент, bucket bootstrap, upload/delete/presigned: `services/profile-service/app/minio_service.py`
- Загрузка фото в profile-service и выдача URL: `services/profile-service/app/routes.py`
- Доставка фото в Telegram через прокси-скачивание: `services/bot-service/app/photo_proxy.py`

### 7) CI/CD — `❌ не закрыт`

Сейчас критерий не выполнен:
- `.github/workflows/ci.yml` отсутствует
- `.github/` исключён из индекса в `.gitignore`

Нужно:
1. Убрать строку с `.github/` из `.gitignore`
2. Добавить workflow (минимум: lint + pytest + docker build)

### 8) Другое (доп. баллы) — `✅ закрыт`

Реализованы дополнительные фичи:
- Peer review после мэтча: `matching-service` + `ranking-service` (peer_score)
- Уведомления о лайках и мэтчах: `notification-service`
- Айсбрейкеры по интересам: `services/notification-service/app/icebreaker.py`
- Нагрузочный сценарий JMeter: `infrastructure/jmeter/`

### 9) Этапы продукта — `⚠️ частично`

**Закрыто:**
- Этап 1 (проектирование): документы `docs/architecture.md`, `docs/services.md`, `docs/database.md`
- Этап 2 (базовая функциональность): bot/profile сервисы, регистрация, CRUD
- Этап 3 (анкеты и ранжирование): feed, ranking, интеграция через REST/MQ
- Этап 4 (дополнительно): Celery, мониторинг, оптимизации, локальный деплой

**Что мешает считать “полностью закрыто”:**
- Регрессия в регистрации (кастомный ввод возраста падает в конце):  
  `services/bot-service/app/handlers/registration.py`
- При выборе пресета возраста в регистрации не сохраняются предпочтения
- Документация местами отстаёт от реального кода

## Проверка тестов на момент отчёта

- `services/bot-service/tests` — passed
- `services/profile-service/tests` — passed
- `services/matching-service/tests` — passed
- `services/notification-service/tests` — passed
- `services/ranking-service/tests` — passed

## Что нужно сделать, чтобы отчёт стал “полностью соответствует критериям”

1. Добавить CI/CD:
   - вернуть `.github/` в версионирование
   - добавить GitHub Actions workflow
2. Актуализировать документацию под текущую реализацию:
   - `README.md`, `SETUP.md`, `docs/scoring.md`, `docs/database.md`

## Итог

Проект находится в состоянии **“почти полностью готов по критериям”**, но до статуса **“полностью соответствует”** не хватает закрытия 2 блоков:  
`(а) CI/CD`, `(б) выравнивание документации`.
