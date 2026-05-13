# Нагрузочное тестирование (JMeter)

`dating_load_test.jmx` — план нагрузочного теста ranking-сервиса (горячий
путь — `GET /feed`, плюс `GET /ratings`). 70/30 распределение запросов,
параметры задаются через `-J` флаги.

## Запуск

Нужен установленный Apache JMeter 5.6+ ([download](https://jmeter.apache.org/download_jmeter.cgi)).

```bash
# 1) Поднять стенд
docker-compose up -d

# 2) (опционально) посеять тестовых пользователей через REST profile-service
#    или просто прогнать тест на пустой БД — большинство запросов ответят
#    200 с `{"profile": null}` (cache-miss path всё равно отрабатывает).

# 3) Запустить
jmeter -n \
  -t infrastructure/jmeter/dating_load_test.jmx \
  -l results.jtl \
  -e -o report \
  -Jhost=localhost -Jusers=50 -Jduration=120 -Jramp=30
```

Параметры:

| флаг            | дефолт | назначение                       |
|-----------------|-------:|----------------------------------|
| `-Jhost`        | localhost | DNS / IP до ranking-service   |
| `-Jranking_port`| 8002   | Порт ranking-service              |
| `-Jusers`       | 50     | Виртуальных пользователей         |
| `-Jduration`    | 120 с  | Длительность теста                |
| `-Jramp`        | 30 с   | Ramp-up                           |

После прогона `report/index.html` содержит p50/p95/p99 latency и RPS.

## Целевые показатели

- p95 `/feed` < 500 ms при 50 RPS на пустом стенде (M1/Ryzen).
- 0 ошибок 5xx.
- Cache hit-rate в Grafana дашборде после прогона должен быть >50% — это
  индикатор того, что Redis ZSET ленты работает.

## Интерпретация результатов

JMeter HTML-отчёт:
- **Statistics → Average / 95th Pct** — основной KPI.
- **Throughput** — фактический RPS, должен быть близок к `users / avg_response_time`.
- **Errors** — должно быть 0%; 4xx (404 для несуществующих telegram_id) считается допустимым и не должен блокировать.

В Grafana во время прогона смотрим:
- Панель «Feed latency p50/p95/p99» — должна совпадать с JMeter ± погрешность.
- Панель «Свайпы (rate / sec)» — нулевая (тест читает, не пишет).
