# Обзор решения за 5 минут

> Краткая шпаргалка по реализации p3: что где лежит, как устроен тест, какие переменные крутить.
> Полный отчёт с цифрами — `report.md`. Команды демо — `how_to_demo.md`.

## TL;DR

Один и тот же FastAPI-сервис умеет работать в трёх режимах кеширования (`Cache-Aside`, `Write-Through`, `Write-Back`). Стратегия выбирается переменной окружения `CACHE_STRATEGY`. Самописный нагрузочный генератор на `asyncio + httpx` гоняет 3 профиля (`read_heavy`, `balanced`, `write_heavy`) против каждого режима и собирает метрики (rps, latency, db_reads/db_writes, hit rate). Скрипт `scripts/run_all.sh` делает все 9 прогонов подряд.

## Архитектура

```
loadgen (asyncio+httpx, 100 клиентов, Zipf α=1.2)
        │  HTTP GET/PUT /items/{id}
        ▼
┌────────────────────────────────┐
│  app (FastAPI)                 │
│  ┌──────────────────────────┐  │       ┌────────┐
│  │ strategy = ENV-выбор     │──┼──────▶│ Redis  │  (кеш + INFO stats)
│  │  Cache-Aside | WT | WB   │  │       └────────┘
│  └──────────────────────────┘  │
│        │                       │       ┌──────────┐
│        └───── asyncpg ─────────┼──────▶│ Postgres │  (источник истины)
└────────────────────────────────┘       └──────────┘
        ▲
   /metrics — JSON со счётчиками (hits/misses/db_reads/db_writes/wb_*)
   /admin/reset — обнуление между прогонами
```

## Что где лежит

| Путь | Назначение |
|---|---|
| `task.md` | Исходное ТЗ от преподавателя |
| `README.md` | Как запустить, параметры, метрики |
| `report.md` | Итоговый отчёт: таблицы, выводы, скрины |
| `how_to_demo.md` | Чек-лист демонстрации преподу с готовыми curl/psql/redis-cli |
| `overview.md` | (этот файл) краткая навигация |
| `docker-compose.yml` | postgres + redis + app + loadgen, healthchecks |
| `Dockerfile` + `requirements.txt` | Один образ для app и loadgen |
| `scripts/run_all.sh` | Прогон 3 стратегий × 3 профилей подряд |
| `app/main.py` | FastAPI: эндпоинты `/items/{id}`, `/metrics`, `/admin/reset`, `/healthz` |
| `app/db.py` | asyncpg + SQLAlchemy 2.x, инкремент `db_reads`/`db_writes` в `fetch/upsert/bulk_upsert` |
| `app/cache.py` | redis.asyncio: `cache_get/set/delete`, инкремент `cache_hits/misses` + `INFO stats` |
| `app/metrics.py` | Потокобезопасные счётчики + snapshot/reset |
| `app/models.py` | Таблица `items(id PK, payload TEXT, updated_at TIMESTAMPTZ)` |
| `app/strategies/base.py` | Абстрактный `CacheStrategy.get/set/startup/shutdown/reset` |
| `app/strategies/cache_aside.py` | read через кеш, write → БД + `DEL` (write-around) |
| `app/strategies/write_through.py` | read через кеш, write → БД + кеш (синхронно) |
| `app/strategies/write_back.py` | write → только в кеш + dirty-очередь, фоновая `asyncio` корутина flushит батчем |
| `app/strategies/__init__.py` | Фабрика `get_strategy(name)` |
| `loadgen/workload.py` | Профили (80/20, 50/50, 20/80), Zipf-семплер ключей, генератор payload |
| `loadgen/runner.py` | 100 корутин, 60 сек, сбор latency, забор `/metrics`, для WB — таймлайн очереди |
| `loadgen/report.py` | Запись `summary.csv`, `latencies_*.csv`, `wb_timeline_*.csv` |
| `results/summary.csv` | Сводная таблица 9 прогонов (главный артефакт) |
| `results/latencies_*.csv` | Все измерения латентности по каждому прогону |
| `results/wb_timeline_*.csv` | Динамика `wb_queue_size`/`wb_flushes` для Write-Back |
| `results/screenshots/` | Скрины терминала для отчёта |

## Как устроены 3 стратегии (в одном месте)

```python
# app/strategies/cache_aside.py
async def get(self, item_id):                         # Lazy Loading
    cached = await cache.cache_get(item_id)
    if cached: return cached
    row = await db.fetch_item(item_id)
    if row: await cache.cache_set(item_id, row)
    return row
async def set(self, item_id, payload):                # Write-Around
    await db.upsert_item(item_id, payload)
    await cache.cache_delete(item_id)

# app/strategies/write_through.py
async def set(self, item_id, payload):
    await db.upsert_item(item_id, payload)            # БД
    await cache.cache_set(item_id, {...payload...})   # потом кеш

# app/strategies/write_back.py
async def set(self, item_id, payload):
    await cache.cache_set(item_id, {...payload...})   # только кеш
    self._dirty[item_id] = payload                     # помечаем «грязным»
# фоновая корутина:
#   await asyncio.wait_for(self._wakeup.wait(), timeout=WB_FLUSH_INTERVAL)
#   await db.bulk_upsert(self._dirty.items())          # один INSERT … ON CONFLICT
```

read-путь у всех трёх одинаков (через кеш + подтяжка из БД на miss). Различия только на write.

## Как устроен тест (loadgen)

`loadgen/runner.py` для каждой пары `(стратегия × профиль)`:

1. `POST /admin/reset` — обнулить счётчики приложения, `FLUSHDB` Redis, очистить dirty-очередь WB.
2. Поднять 100 корутин, каждая 60 секунд в цикле:
   - `pick_op(read_ratio)` → `read` или `write`,
   - `keys.next_key()` → id из Zipf α=1.2 (есть «горячие» ключи → реалистичный hit rate),
   - HTTP запрос через общий `httpx.AsyncClient`,
   - локально измерить latency.
3. Для `write_back` — отдельная корутина каждую секунду снимает `/metrics` (таймлайн `wb_queue_size`).
4. После прогона: для WB — ждать `WB_TAIL_WAIT=10` сек чтобы фоновый flusher дренировал очередь, затем забрать финальные `/metrics`.
5. Записать строку в `summary.csv`, отдельно `latencies_*.csv` и `wb_timeline_*.csv`.

Главное: **один и тот же `runner.py` гоняет все три стратегии** — меняется только `CACHE_STRATEGY` у контейнера app. Это и обеспечивает «одинаковые условия» из ТЗ.

## Как считаются метрики

| Метрика | Где |
|---|---|
| `throughput` | `requests_done / actual_duration` в loadgen |
| `avg/p50/p95/p99 latency` | `statistics.fmean` + сортировка локального массива в loadgen |
| `db_reads` / `db_writes` | `metrics.incr` в `app/db.py:fetch_item/upsert_item/bulk_upsert` (одна транзакция = +1) |
| `cache_hits` / `cache_misses` | `metrics.incr` в `app/cache.py:cache_get` |
| `hit_rate` | `cache_hits / (cache_hits + cache_misses)` |
| `redis_keyspace_hits/misses` | `INFO stats` Redis — независимая контрольная цифра |
| `wb_queue_size` / `wb_flushes` / `wb_flushed_rows` | счётчики в `app/strategies/write_back.py` |

## Ключевые ENV-переменные

| Переменная | По умолчанию | Что меняет |
|---|---|---|
| `CACHE_STRATEGY` | `cache_aside` | стратегия app: `cache_aside` / `write_through` / `write_back` |
| `SEED_ITEMS` | 10000 | сколько строк сидируем в БД на старте |
| `CACHE_TTL` | 300 | TTL ключей в Redis (сек) |
| `WB_FLUSH_INTERVAL` | 1.0 | интервал фонового flush'а Write-Back (сек) |
| `WB_FLUSH_BATCH` | 500 | размер очереди, при котором flush триггерится досрочно |
| `DURATION` | 60 | длительность одного прогона (сек) |
| `CONCURRENCY` | 100 | параллельных корутин в loadgen |
| `N_KEYS` | 10000 | размер ключевого пространства для Zipf-семплинга |
| `ZIPF_ALPHA` | 1.2 | «горячесть» распределения |
| `WB_TAIL_WAIT` | 10 | сколько ждать после нагрузки чтобы дренировать WB-очередь |

## Запуск за 30 секунд

```bash
# поднять инфру и прогнать всё
bash scripts/run_all.sh

# посмотреть результат
column -s, -t < results/summary.csv | less -S
```

Дальше — `report.md` для финальной таблицы и выводов, `how_to_demo.md` для пошаговой демонстрации.
