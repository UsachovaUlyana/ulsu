# Практическая работа №3 — Сравнительный анализ стратегий кеширования

**Усачева Ульяна, К0709-23/3**

---

## О проекте

Проект представляет собой единую систему, которая поддерживает три различных подхода к кешированию данных:

| Стратегия | Модуль |
|---|---|
| Cache-Aside (Lazy Loading / Write-Around) | `app/strategies/cache_aside.py` |
| Write-Through | `app/strategies/write_through.py` |
| Write-Back | `app/strategies/write_back.py` |

**Используемые технологии:** FastAPI, SQLAlchemy (async) с asyncpg, redis.asyncio.  
**Инфраструктура:** PostgreSQL 16, Redis 7.  
**Нагрузочное тестирование:** собственный генератор на базе `asyncio` и `httpx`.

## Структура проекта

```
app/                Приложение на FastAPI: модули для работы с БД и кешем, реализация стратегий
loadgen/            Генератор нагрузки (распределение Zipf, три профиля нагрузки)
scripts/run_all.sh  Скрипт для последовательного запуска всех комбинаций (3 стратегии × 3 профиля)
docker-compose.yml  Конфигурация контейнеров: postgres + redis + app + loadgen
report.md           Отчёт с результатами, таблицами и выводами
results/            Каталог с CSV-результатами и скриншотами
```

## Как запустить

**Необходимо:** Docker + `docker compose` v2.

```bash
# Запуск конкретной стратегии с тремя профилями нагрузки
CACHE_STRATEGY=cache_aside docker compose up -d --force-recreate app
docker compose run --rm loadgen --strategy cache_aside

# Запуск полного набора тестов (3 × 3 — рекомендуется)
bash scripts/run_all.sh
```

### Результаты после прогона

- `results/summary.csv` — сводка по всем 9 комбинациям (3 стратегии × 3 профиля).
- `results/latencies_<strategy>_<profile>.csv` — полные замеры задержек.
- `results/wb_timeline_*.csv` — динамика очереди для Write-Back.
- `results/screenshots/` — скриншоты терминала для отчёта.

## Настройки тестирования

| Параметр | Значение по умолчанию | Где изменить |
|---|---|---|
| Длительность прогона | 60 секунд | `DURATION` |
| Количество клиентов | 100 | `CONCURRENCY` |
| Объём ключевого пространства | 10 000 | `N_KEYS` / `SEED_ITEMS` |
| Распределение запросов | Zipf, α = 1.2 | `ZIPF_ALPHA` |
| Профили нагрузки | 80/20, 50/50, 20/80 | `loadgen/workload.py` |
| Интервал flush / размер батча WB | 1 сек / 500 | `WB_FLUSH_INTERVAL`, `WB_FLUSH_BATCH` |

## Собираемые метрики

| Метрика | Источник |
|---|---|
| `throughput` (запросов/сек) | loadgen: `requests_total / duration` |
| `avg / p50 / p95 / p99 latency` | loadgen: локальные замеры |
| Количество обращений к БД | `app/db.py` — счётчики `db_reads` / `db_writes` при каждом запросе к Postgres |
| Hit rate кеша | `app/cache.py` — счётчики `cache_hits` / `cache_misses`; дополнительно контролируется через `INFO stats` Redis |
| Динамика Write-Back | `wb_queue_size`, `wb_flushes`, `wb_flushed_rows` + таймлайн в `results/wb_timeline_*.csv` |

## Демонстрация

Подробные шаги для показа — в файле `how_to_demo.md`.
