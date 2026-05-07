# Отчёт: сравнение типов кеширования

## 1. Описание системы

```
┌────────────┐      HTTP       ┌────────────┐    Redis    ┌────────────┐
│ load-gen   │ ───────────────▶│  FastAPI   │◀───────────▶│ Redis   │
│ asyncio +  │                 │  (app/)    │             │            │
│ httpx      │                 │            │             └────────────┘
│ 100 client │                 │  стратегия │    asyncpg
│ Zipf α=1.2 │                 │  по ENV    │◀─────────────┐
└────────────┘                 └────────────┘              ▼
                                                    ┌────────────┐
                                                    │ PostgreSQL │
                                                    │   items    │
                                                    └────────────┘
```

Все три стратегии — это один и тот же FastAPI-сервис; нужная стратегия выбирается переменной окружения `CACHE_STRATEGY ∈ {cache_aside, write_through, write_back}` (см. `app/strategies/__init__.py:get_strategy`). Это даёт идентичные тестовые условия (один и тот же loadgen, один и тот же набор данных, одинаковая длительность).

## 2. Реализованные стратегии

### Cache-Aside (Lazy Loading + Write-Around)
Файл: `app/strategies/cache_aside.py`.
- `read`: смотрим в кеш; на miss — читаем БД и кладём в кеш с TTL.
- `write`: пишем в БД, кеш инвалидируем (`DEL`) — write-around.

### Write-Through
Файл: `app/strategies/write_through.py`.
- `read`: как у cache-aside (через кеш с подгрузкой из БД на miss).
- `write`: синхронно пишем в БД, затем обновляем кеш — на чтении сразу попадаем в кеш.

### Write-Back
Файл: `app/strategies/write_back.py`.
- `read`: как у cache-aside.
- `write`: пишем только в кеш, помечаем ключ «грязным» в локальной очереди.
- Фоновая задача (`asyncio`) сбрасывает очередь в БД одним `INSERT … ON CONFLICT DO UPDATE` либо по интервалу `WB_FLUSH_INTERVAL`, либо когда очередь дойдёт до `WB_FLUSH_BATCH`.

## 3. Описание тестов

| Параметр | Значение |
|---|---|
| Длительность одного прогона | 60 сек |
| Параллельных клиентов | 100 (asyncio + httpx, общий `AsyncClient`) |
| Ключевое пространство | 10 000 предсидированных строк в `items` |
| Распределение ключей | Zipf, α=1.2 (есть «горячие» ключи — реалистичный hit rate) |
| Размер payload | 256 байт |
| Профили нагрузки | `read_heavy` 80/20, `balanced` 50/50, `write_heavy` 20/80 |
| Между прогонами | `POST /admin/reset` обнуляет счётчики, `FLUSHDB` чистит кеш, у write-back чистится dirty-очередь |
| Параметры Write-Back | `WB_FLUSH_INTERVAL=1s`, `WB_FLUSH_BATCH=500` |
| После write-back прогона | дополнительные 10 сек ожидания + сэмплинг очереди для таймлайна |

Один и тот же `loadgen/runner.py` используется для всех трёх стратегий — меняется только ENV у контейнера `app`. Скрипт `scripts/run_all.sh` прогоняет все 9 комбинаций подряд.

## 4. Сводная таблица результатов

Источник: `results/summary.csv`. Прогон 60 сек × 100 клиентов × 10 000 ключей × Zipf α=1.2.

| strategy | profile | rps | avg ms | p50 ms | p95 ms | p99 ms | DB reads | DB writes | hit rate |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| cache_aside   | read_heavy   | 399.7 | 249.7 | 142.9 |  795.8 | 1715.3 | 5836 | 4830 | 69.7% |
| cache_aside   | balanced     | 222.2 | 449.2 | 259.5 | 1559.3 | 2755.6 | 3851 | 6813 | 41.8% |
| cache_aside   | write_heavy  | 157.6 | 630.5 | 369.2 | 2152.3 | 3441.5 | 1623 | 7669 | 15.6% |
| write_through | read_heavy   | 450.5 | 221.1 | 118.2 |  749.3 | 1920.6 | 2412 | 5439 | 89.0% |
| write_through | balanced     | 244.0 | 407.0 | 242.7 | 1352.0 | 2352.6 | 1063 | 7362 | 85.9% |
| write_through | write_heavy  | 174.6 | 569.0 | 329.1 | 2000.7 | 3405.9 |  333 | 8496 | 84.2% |
| write_back    | read_heavy   | 665.1 | 150.2 |  94.1 |  420.5 |  971.6 | 3023 |   60 | 90.6% |
| write_back    | balanced     | 608.5 | 164.2 | 111.9 |  481.5 |  822.7 | 1752 |   60 | 90.3% |
| write_back    | write_heavy  | 392.5 | 254.3 | 153.2 |  843.8 | 1503.9 |  582 |   61 | 87.8% |

Полный набор колонок (errors, redis keyspace stats, wb_flushes/wb_flushed_rows) — в `results/summary.csv`.

### Замечания к сравнению

- На read_heavy у `cache_aside` hit rate всего 69.7% против 89.0% у `write_through` — это эффект write-around: записанные ключи инвалидируются, и следующее чтение уходит в БД.
- На `write_through` hit rate ≥ 84% на всех трёх профилях — записи сразу прогревают кеш.
- `write_back` даёт 87–90% hit rate и в **80–140 раз** меньше `db_writes`: 18 883 «логических» записей за 60 сек схлопываются в 61 батч (`WB_FLUSH_INTERVAL=1s`).

## 5. Write-Back: что происходит при накоплении

`results/wb_timeline_write_back_<profile>.csv` содержит сэмплы каждую секунду в течение прогона и ещё 10 секунд после.

Колонки таймлайна:
- `wb_queue_size` — количество «грязных» ключей в локальной очереди приложения.
- `wb_flushes` — сколько раз сработал фоновый сброс (по интервалу или по `WB_FLUSH_BATCH`).
- `wb_flushed_rows` — суммарное число строк, реально записанных в Postgres.

Фактические итоги по последнему прогону:

| profile | write_total (логических) | wb_flushes | wb_flushed_rows | db_writes | wb_queue_size_end |
|---|---:|---:|---:|---:|---:|
| read_heavy  |  7 858 | 60 | 3 774 | 60 | 0 |
| balanced    | 18 410 | 60 | 7 586 | 60 | 0 |
| write_heavy | 18 883 | 61 | 7 625 | 61 | 0 |

Что видно:

1. Под write_heavy за 60 сек прилетело 18 883 PUT-запроса, но **в БД ушло всего 61 батчевая транзакция** (`db_writes`). Это и есть эффект Write-Back: одна и та же горячая запись по одному `id` в течение секунды объединяется в одно `INSERT … ON CONFLICT DO UPDATE`.
2. `wb_flushed_rows` (≈ количество уникальных «грязных» ключей за весь прогон) меньше `write_total` за счёт схлопывания: на write_heavy 18 883 PUT → 7 625 уникальных ключей в батчах.
3. `wb_queue_size_end = 0` во всех трёх профилях — фоновый flusher успевает дренировать очередь за дополнительные 10 сек после остановки нагрузки (`WB_TAIL_WAIT=10`).
4. Между двумя соседними flush'ами `db_writes` не растёт — БД получает нагрузку всплесками, в среднем 1 раз в `WB_FLUSH_INTERVAL=1s`.

Графики `wb_queue_size(t)` можно построить из `results/wb_timeline_*.csv` (любым plotter'ом).

## 6. Выводы

Цифры из таблицы выше:

**Лучшее для чтения (`read_heavy`):**
- по rps: **Write-Back 665** > Write-Through 451 > Cache-Aside 400.
- по avg latency: **Write-Back 150 ms** < Write-Through 221 ms < Cache-Aside 250 ms.
- по hit rate: **Write-Back 90.6%** ≈ Write-Through 89.0% > Cache-Aside 69.7%.
- Cache-Aside проигрывает из-за write-around: даже при 20% записей он стабильно инвалидирует горячие ключи, и следующий read даёт miss.

**Лучшее для записи (`write_heavy`):**
- по rps: **Write-Back 393** > Write-Through 175 ≈ Cache-Aside 158 (Write-Back в **2.5× быстрее**).
- по p95: Write-Back **844 ms** против 2001 ms у Write-Through и 2152 ms у Cache-Aside.
- по обращениям в БД: **Write-Back делает 61 запись** против 8 496 у Write-Through (схлопывание ~140×).
- Write-Through даёт стабильный hit rate 84%, но каждая запись синхронно идёт в Postgres — БД становится бутылочным горлышком.
- Cache-Aside на write_heavy — худший вариант: write-around обнуляет кеш, hit rate проседает до 15.6%, БД получает и записи, и miss-чтения.

**Смешанная нагрузка (`balanced`):**
- по rps: **Write-Back 609** > Write-Through 244 > Cache-Aside 222.
- Write-Through — разумный дефолт без особых требований к durability: даёт 86% hit rate без сложной логики «грязной» очереди.
- Write-Back побеждает по всем метрикам, но цена — потеря durability (между flush'ами писанные данные живут только в Redis) и необходимость WAL/recovery при падении.

**Итог:** на любом профиле в этом тесте Write-Back лидирует по rps и latency, Write-Through держится «золотой серединой» по балансу простоты и стабильности, Cache-Aside проигрывает везде, кроме сценариев с минимумом записей и/или строгими требованиями к консистентности (write-around гарантирует, что в кеше не залежится устаревшее значение).

## 7. Скрины консоли

Лежат в `results/screenshots/`.

- `results/screenshots/run_all.png` — финальная таблица `scripts/run_all.sh` со всеми 9 строками.
- `results/screenshots/cache_aside.png` — лог одного прогона стратегии Cache-Aside.
- `results/screenshots/write_through.png` — лог Write-Through.
- `results/screenshots/write_back.png` — лог Write-Back с динамикой `wb_queue_size`/`wb_flushes`.

> Снять скриншоты после прогона и положить файлы по этим путям; ссылки тогда станут рабочими:
>
> ![run_all](results/screenshots/run_all.png)
