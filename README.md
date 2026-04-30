# RabbitMQ vs Redis Streams Benchmark

Практика по сравнению `RabbitMQ` и `Redis Streams` как брокеров сообщений в одинаковых условиях.

## Что реализовано

- Redis транспорт строго как `Redis Streams + Consumer Group + XACK`.
- Фиксированное и одинаковое количество producers/consumers для обоих брокеров.
- Одинаковые лимиты ресурсов (`cpus`, `mem_limit`) для `rabbitmq` и `redis` в `docker-compose.yml`.
- Метрики: `throughput`, `avg/p95/max latency`, `sent`, `consumed`, `lost`, `duplicates`, `errors`, `backlog/queue_depth` (в т.ч. peak).
- Критерии деградации `single instance` (любой критерий срабатывает):
  - backlog растет непрерывно в окне наблюдения;
  - `p95` выше `baseline * multiplier`;
  - стабильные ошибки publish/consume;
  - устойчивые потери (кандидат, подтверждается повторяемостью в матрице).

## Структура

- `benchmark.py` — producer/consumer + runner + matrix + summary.
- `docker-compose.yml` — single-instance брокеры с одинаковыми CPU/RAM лимитами.
- `scripts/run_matrix.sh` — полный прогон матрицы.
- `results/` — сырые результаты (`json`, `results.csv`, `summary.csv`).

## Быстрый запуск

1. Поднять брокеры:

```bash
docker compose up -d rabbitmq redis
```

2. Одиночный прогон (пример, baseline RabbitMQ):

```bash
python benchmark.py run \
  --broker rabbitmq \
  --profile baseline \
  --msg-size 1024 \
  --rate 5000 \
  --duration 120 \
  --producers 2 \
  --consumers 2
```

3. Полная матрица:

```bash
./scripts/run_matrix.sh
```

4. Построить summary (если нужно отдельно):

```bash
python benchmark.py summary --output-dir results
```

## Параметры матрицы

- Размеры: `128B`, `1KB`, `10KB`, `100KB`
- Интенсивности: `1000`, `5000`, `10000 msg/s`
- Профили: `baseline`, `stress`
- Повторы: `3`

## Формула потерь

- `lost_total = sent_total - consumed_unique_total`
- Дубликаты считаются отдельно и не считаются потерями.

## Важная проверка корректности

Если в `baseline` для RabbitMQ получаются аномально большие потери, это трактуется как проблема методики/конфигурации, а не как итоговый вывод. Нужна перепроверка `durable/persistent/manual ack/publisher confirm` и повтор прогона.
