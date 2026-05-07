# Демонстрация (чек-лист)

## 1. Поднять инфраструктуру

```bash
docker compose up -d postgres redis
docker compose ps
```

Оба контейнера должны быть `healthy`.

## 2. Показать стратегию Cache-Aside

```bash
CACHE_STRATEGY=cache_aside docker compose up -d --force-recreate app
curl -s :8000/healthz | jq
curl -s :8000/items/1 | jq          # miss → читает БД, кладёт в кеш
curl -s :8000/items/1 | jq          # hit
curl -s :8000/metrics | jq '{cache_hits, cache_misses, db_reads, db_writes}'
curl -s -X PUT :8000/items/1 -H 'Content-Type: application/json' -d '{"payload":"new"}'
docker exec p3-redis redis-cli GET item:1   # пусто (write-around)
```

## 3. Показать стратегию Write-Through

```bash
CACHE_STRATEGY=write_through docker compose up -d --force-recreate app
curl -s -X POST :8000/admin/reset
curl -s -X PUT :8000/items/2 -H 'Content-Type: application/json' -d '{"payload":"wt"}'
docker exec p3-redis redis-cli GET item:2   # значение в кеше
docker exec p3-postgres psql -U postgres -d cachebench -c "SELECT id, payload FROM items WHERE id=2"
```

## 4. Показать стратегию Write-Back

```bash
CACHE_STRATEGY=write_back WB_FLUSH_INTERVAL=5 docker compose up -d --force-recreate app
curl -s -X POST :8000/admin/reset
for i in 100 101 102; do
  curl -s -X PUT :8000/items/$i -H 'Content-Type: application/json' -d "{\"payload\":\"wb-$i\"}"
done
curl -s :8000/metrics | jq '{wb_queue_size, wb_flushes, db_writes}'
# ждём интервал — фоновая задача делает batch upsert
sleep 6
curl -s :8000/metrics | jq '{wb_queue_size, wb_flushes, wb_flushed_rows, db_writes}'
docker exec p3-postgres psql -U postgres -d cachebench -c "SELECT id, payload FROM items WHERE id IN (100,101,102)"
```

## 5. Полный бенчмарк

```bash
bash scripts/run_all.sh
column -s, -t < results/summary.csv | less -S
```

Снять скриншот терминала с финальной таблицей и положить в `results/screenshots/`.

## 6. Открыть отчёт

`report.md` — таблицы, выводы, ссылки на скрины.
