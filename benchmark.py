#!/usr/bin/env python3
import argparse
import csv
import json
import os
import statistics
import threading
import time
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import pika
import redis
from pika.exceptions import AMQPError, NackError, UnroutableError
from redis.exceptions import RedisError, ResponseError


RABBIT_QUEUE = "benchmark_queue"
REDIS_STREAM = "benchmark_stream"
REDIS_GROUP = "benchmark_group"


@dataclass
class RunConfig:
    broker: str
    profile: str
    msg_size: int
    rate: int
    duration: int
    producers: int
    consumers: int
    run_id: str
    output_dir: str
    sample_interval: float
    drain_timeout: int
    backlog_window_sec: int
    baseline_p95_ms: float | None
    p95_multiplier: float
    error_rate_threshold: float
    loss_rate_threshold: float


@dataclass
class RunResult:
    run_id: str
    broker: str
    profile: str
    msg_size: int
    rate: int
    duration: int
    producers: int
    consumers: int
    sent_total: int
    consumed_unique_total: int
    duplicate_count: int
    lost_total: int
    publish_errors: int
    consume_errors: int
    throughput_msg_sec: float
    avg_latency_ms: float
    p95_latency_ms: float
    max_latency_ms: float
    backlog_peak: int
    backlog_samples: list[dict[str, Any]]
    degradation: dict[str, Any]
    started_at_iso: str
    finished_at_iso: str


class Metrics:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.sent_total = 0
        self.publish_errors = 0
        self.consume_errors = 0
        self.duplicate_count = 0
        self.consumed_ids: set[str] = set()
        self.latencies_ms: list[float] = []
        self.backlog_samples: list[dict[str, Any]] = []

    def inc_sent(self) -> None:
        with self.lock:
            self.sent_total += 1

    def inc_publish_error(self) -> None:
        with self.lock:
            self.publish_errors += 1

    def inc_consume_error(self) -> None:
        with self.lock:
            self.consume_errors += 1

    def record_consumed(self, msg_id: str, latency_ms: float) -> None:
        with self.lock:
            if msg_id in self.consumed_ids:
                self.duplicate_count += 1
                return
            self.consumed_ids.add(msg_id)
            self.latencies_ms.append(latency_ms)

    def record_backlog(self, ts_s: float, depth: int) -> None:
        with self.lock:
            self.backlog_samples.append({"ts_s": round(ts_s, 3), "queue_depth": int(depth)})

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "sent_total": self.sent_total,
                "publish_errors": self.publish_errors,
                "consume_errors": self.consume_errors,
                "duplicate_count": self.duplicate_count,
                "consumed_unique_total": len(self.consumed_ids),
                "latencies_ms": list(self.latencies_ms),
                "backlog_samples": list(self.backlog_samples),
            }


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    ordered = sorted(values)
    idx = (len(ordered) - 1) * q
    low = int(idx)
    high = min(low + 1, len(ordered) - 1)
    if low == high:
        return float(ordered[low])
    frac = idx - low
    return float(ordered[low] * (1 - frac) + ordered[high] * frac)


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def make_payload(target_size: int, msg_id: str, run_id: str) -> bytes:
    base = {
        "msg_id": msg_id,
        "run_id": run_id,
        "sent_ts_ns": time.time_ns(),
        "payload": "",
    }
    raw = json.dumps(base, separators=(",", ":")).encode("utf-8")
    extra = max(0, target_size - len(raw))
    if extra > 0:
        base["payload"] = "x" * extra
    out = json.dumps(base, separators=(",", ":")).encode("utf-8")
    if len(out) < target_size:
        out += b"x" * (target_size - len(out))
    return out


def parse_message(raw: bytes) -> tuple[str, int]:
    body = raw.decode("utf-8", errors="ignore")
    data = json.loads(body)
    return str(data["msg_id"]), int(data["sent_ts_ns"])


def make_rabbit_connection_params() -> pika.ConnectionParameters:
    host = os.getenv("RABBITMQ_HOST", "rabbitmq")
    port = int(os.getenv("RABBITMQ_PORT", "5672"))
    user = os.getenv("RABBITMQ_USER", "guest")
    password = os.getenv("RABBITMQ_PASS", "guest")
    creds = pika.PlainCredentials(user, password)
    return pika.ConnectionParameters(
        host=host,
        port=port,
        credentials=creds,
        heartbeat=60,
        blocked_connection_timeout=30,
        connection_attempts=10,
        retry_delay=2,
    )


def make_redis_client() -> redis.Redis:
    host = os.getenv("REDIS_HOST", "redis")
    port = int(os.getenv("REDIS_PORT", "6379"))
    return redis.Redis(
        host=host,
        port=port,
        decode_responses=False,
        socket_connect_timeout=2.0,
        socket_timeout=2.0,
        retry_on_timeout=False,
        health_check_interval=5,
    )


def prepare_rabbit(profile: str) -> None:
    del profile
    conn = pika.BlockingConnection(make_rabbit_connection_params())
    ch = conn.channel()
    ch.queue_declare(queue=RABBIT_QUEUE, durable=True)
    ch.queue_purge(queue=RABBIT_QUEUE)
    conn.close()


def prepare_redis(profile: str, run_id: str) -> None:
    del profile
    client = make_redis_client()
    stream = f"{REDIS_STREAM}:{run_id}"
    group = f"{REDIS_GROUP}:{run_id}"
    try:
        client.xgroup_create(stream, group, id="0", mkstream=True)
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


def get_rabbit_depth() -> int:
    conn = pika.BlockingConnection(make_rabbit_connection_params())
    ch = conn.channel()
    res = ch.queue_declare(queue=RABBIT_QUEUE, passive=True)
    depth = int(res.method.message_count)
    conn.close()
    return depth


def get_redis_depth(run_id: str) -> int:
    client = make_redis_client()
    stream = f"{REDIS_STREAM}:{run_id}"
    group = f"{REDIS_GROUP}:{run_id}"
    try:
        groups = client.xinfo_groups(stream)
    except ResponseError:
        return 0
    if not groups:
        return int(client.xlen(stream))
    target = None
    for g in groups:
        name = g.get(b"name") if isinstance(next(iter(g.keys())), bytes) else g.get("name")
        if isinstance(name, bytes):
            name = name.decode()
        if name == group:
            target = g
            break
    if target is None:
        return int(client.xlen(stream))

    def pick(field: str) -> int | None:
        key = field if field in target else field.encode()
        val = target.get(key)
        if val is None:
            return None
        if isinstance(val, bytes):
            return int(val.decode())
        return int(val)

    lag = pick("lag")
    pending = pick("pending")
    if lag is not None:
        return max(0, lag + (pending or 0))
    return int(client.xlen(stream))


def monitor_backlog(cfg: RunConfig, metrics: Metrics, stop_evt: threading.Event) -> None:
    start = time.monotonic()
    while not stop_evt.is_set():
        try:
            depth = get_rabbit_depth() if cfg.broker == "rabbitmq" else get_redis_depth(cfg.run_id)
            metrics.record_backlog(time.monotonic() - start, depth)
        except Exception:
            metrics.inc_consume_error()
        stop_evt.wait(cfg.sample_interval)


def producer_rabbit(cfg: RunConfig, metrics: Metrics, worker_idx: int, start_ts: float, end_ts: float) -> None:
    conn = pika.BlockingConnection(make_rabbit_connection_params())
    ch = conn.channel()
    ch.queue_declare(queue=RABBIT_QUEUE, durable=True)
    ch.confirm_delivery()

    per_worker_rate = cfg.rate / cfg.producers
    interval = 1.0 / per_worker_rate if per_worker_rate > 0 else 0
    next_tick = start_ts
    seq = 0

    while time.monotonic() < end_ts:
        now = time.monotonic()
        if now < next_tick:
            time.sleep(min(next_tick - now, 0.005))
            continue
        msg_id = f"{cfg.run_id}-p{worker_idx}-{seq}"
        body = make_payload(cfg.msg_size, msg_id, cfg.run_id)
        props = pika.BasicProperties(delivery_mode=2)
        try:
            ch.basic_publish(
                exchange="",
                routing_key=RABBIT_QUEUE,
                body=body,
                properties=props,
                mandatory=True,
            )
            metrics.inc_sent()
        except (AMQPError, NackError, UnroutableError):
            metrics.inc_publish_error()
        seq += 1
        next_tick += interval

    conn.close()


def consumer_rabbit(cfg: RunConfig, metrics: Metrics, stop_evt: threading.Event, producers_done: threading.Event) -> None:
    conn = pika.BlockingConnection(make_rabbit_connection_params())
    ch = conn.channel()
    ch.queue_declare(queue=RABBIT_QUEUE, durable=True)
    ch.basic_qos(prefetch_count=100)

    while True:
        if stop_evt.is_set():
            break
        try:
            method, _, body = ch.basic_get(queue=RABBIT_QUEUE, auto_ack=False)
        except AMQPError:
            metrics.inc_consume_error()
            time.sleep(0.02)
            continue

        if method is None:
            if producers_done.is_set():
                try:
                    if get_rabbit_depth() == 0:
                        break
                except Exception:
                    pass
            time.sleep(0.01)
            continue

        try:
            msg_id, sent_ts_ns = parse_message(body)
            latency_ms = max(0.0, (time.time_ns() - sent_ts_ns) / 1_000_000)
            metrics.record_consumed(msg_id, latency_ms)
            ch.basic_ack(method.delivery_tag)
        except Exception:
            metrics.inc_consume_error()
            try:
                ch.basic_nack(method.delivery_tag, requeue=False)
            except Exception:
                pass

    conn.close()


def producer_redis(cfg: RunConfig, metrics: Metrics, worker_idx: int, start_ts: float, end_ts: float) -> None:
    client = make_redis_client()
    stream = f"{REDIS_STREAM}:{cfg.run_id}"

    per_worker_rate = cfg.rate / cfg.producers
    interval = 1.0 / per_worker_rate if per_worker_rate > 0 else 0
    next_tick = start_ts
    seq = 0

    while time.monotonic() < end_ts:
        now = time.monotonic()
        if now < next_tick:
            time.sleep(min(next_tick - now, 0.005))
            continue
        msg_id = f"{cfg.run_id}-p{worker_idx}-{seq}"
        body = make_payload(cfg.msg_size, msg_id, cfg.run_id)
        try:
            client.xadd(stream, {b"data": body})
            metrics.inc_sent()
        except RedisError:
            metrics.inc_publish_error()
        seq += 1
        next_tick += interval


def consumer_redis(cfg: RunConfig, metrics: Metrics, consumer_idx: int, stop_evt: threading.Event, producers_done: threading.Event) -> None:
    client = make_redis_client()
    stream = f"{REDIS_STREAM}:{cfg.run_id}"
    group = f"{REDIS_GROUP}:{cfg.run_id}"
    consumer_name = f"c-{consumer_idx}-{uuid.uuid4().hex[:8]}"

    while True:
        if stop_evt.is_set():
            break
        try:
            items = client.xreadgroup(
                groupname=group,
                consumername=consumer_name,
                streams={stream: ">"},
                count=50,
                block=1000,
            )
        except RedisError:
            metrics.inc_consume_error()
            time.sleep(0.05)
            continue

        if not items:
            if producers_done.is_set():
                try:
                    if get_redis_depth(cfg.run_id) == 0:
                        break
                except Exception:
                    pass
            continue

        try:
            _, entries = items[0]
            ack_ids: list[str] = []
            for entry_id, fields in entries:
                data = fields.get(b"data") or fields.get("data")
                if data is None:
                    metrics.inc_consume_error()
                    ack_ids.append(entry_id)
                    continue
                msg_id, sent_ts_ns = parse_message(data)
                latency_ms = max(0.0, (time.time_ns() - sent_ts_ns) / 1_000_000)
                metrics.record_consumed(msg_id, latency_ms)
                ack_ids.append(entry_id)
            if ack_ids:
                client.xack(stream, group, *ack_ids)
        except Exception:
            metrics.inc_consume_error()


def detect_degradation(
    cfg: RunConfig,
    sent_total: int,
    lost_total: int,
    publish_errors: int,
    consume_errors: int,
    p95_latency_ms: float,
    backlog_samples: list[dict[str, Any]],
) -> dict[str, Any]:
    window_samples = max(1, int(cfg.backlog_window_sec / cfg.sample_interval))
    tail = backlog_samples[-window_samples:] if backlog_samples else []

    backlog_growing = False
    if len(tail) >= 2:
        depths = [row["queue_depth"] for row in tail]
        non_decreasing = all(depths[i] <= depths[i + 1] for i in range(len(depths) - 1))
        backlog_growing = non_decreasing and depths[-1] > depths[0]

    p95_over_baseline = False
    if cfg.baseline_p95_ms and cfg.baseline_p95_ms > 0:
        p95_over_baseline = p95_latency_ms >= cfg.baseline_p95_ms * cfg.p95_multiplier

    total_errors = publish_errors + consume_errors
    error_rate = (total_errors / sent_total) if sent_total > 0 else 0.0
    errors_stable = total_errors >= 10 and error_rate >= cfg.error_rate_threshold

    loss_rate = (lost_total / sent_total) if sent_total > 0 else 0.0
    repeated_loss_candidate = loss_rate >= cfg.loss_rate_threshold

    return {
        "backlog_growing": backlog_growing,
        "p95_over_baseline": p95_over_baseline,
        "errors_stable": errors_stable,
        "repeated_loss_candidate": repeated_loss_candidate,
        "is_degraded": any([backlog_growing, p95_over_baseline, errors_stable, repeated_loss_candidate]),
        "details": {
            "error_rate": round(error_rate, 6),
            "loss_rate": round(loss_rate, 6),
            "baseline_p95_ms": cfg.baseline_p95_ms,
            "p95_multiplier": cfg.p95_multiplier,
            "window_samples": window_samples,
        },
    }


def run_single(cfg: RunConfig) -> RunResult:
    metrics = Metrics()
    started_at = now_iso()

    if cfg.broker == "rabbitmq":
        try:
            prepare_rabbit(cfg.profile)
        except Exception:
            metrics.inc_consume_error()
    elif cfg.broker == "redis":
        try:
            prepare_redis(cfg.profile, cfg.run_id)
        except Exception:
            metrics.inc_consume_error()
    else:
        raise ValueError(f"Unsupported broker: {cfg.broker}")

    monitor_stop = threading.Event()
    stop_consumers = threading.Event()
    producers_done = threading.Event()

    monitor_thread = threading.Thread(
        target=monitor_backlog,
        args=(cfg, metrics, monitor_stop),
        daemon=True,
    )
    monitor_thread.start()

    consumer_threads: list[threading.Thread] = []
    for i in range(cfg.consumers):
        target = consumer_rabbit if cfg.broker == "rabbitmq" else consumer_redis
        args = (cfg, metrics, stop_consumers, producers_done) if cfg.broker == "rabbitmq" else (cfg, metrics, i, stop_consumers, producers_done)
        t = threading.Thread(target=target, args=args, daemon=True)
        t.start()
        consumer_threads.append(t)

    start_ts = time.monotonic() + 1.0
    end_ts = start_ts + cfg.duration

    producer_threads: list[threading.Thread] = []
    for i in range(cfg.producers):
        target = producer_rabbit if cfg.broker == "rabbitmq" else producer_redis
        t = threading.Thread(target=target, args=(cfg, metrics, i, start_ts, end_ts), daemon=True)
        t.start()
        producer_threads.append(t)

    for t in producer_threads:
        t.join()
    producers_done.set()

    drain_deadline = time.monotonic() + cfg.drain_timeout
    while time.monotonic() < drain_deadline:
        try:
            depth = get_rabbit_depth() if cfg.broker == "rabbitmq" else get_redis_depth(cfg.run_id)
            if depth == 0:
                break
        except Exception:
            pass
        time.sleep(0.5)

    stop_consumers.set()
    for t in consumer_threads:
        t.join(timeout=2)

    monitor_stop.set()
    monitor_thread.join(timeout=2)

    snap = metrics.snapshot()
    sent_total = int(snap["sent_total"])
    consumed_unique_total = int(snap["consumed_unique_total"])
    duplicate_count = int(snap["duplicate_count"])
    publish_errors = int(snap["publish_errors"])
    consume_errors = int(snap["consume_errors"])
    latencies = snap["latencies_ms"]
    backlog_samples = snap["backlog_samples"]

    lost_total = max(0, sent_total - consumed_unique_total)
    throughput = consumed_unique_total / max(1, cfg.duration)
    avg_latency = statistics.fmean(latencies) if latencies else 0.0
    p95_latency = percentile(latencies, 0.95)
    max_latency = max(latencies) if latencies else 0.0
    backlog_peak = max((row["queue_depth"] for row in backlog_samples), default=0)

    degradation = detect_degradation(
        cfg,
        sent_total,
        lost_total,
        publish_errors,
        consume_errors,
        p95_latency,
        backlog_samples,
    )

    result = RunResult(
        run_id=cfg.run_id,
        broker=cfg.broker,
        profile=cfg.profile,
        msg_size=cfg.msg_size,
        rate=cfg.rate,
        duration=cfg.duration,
        producers=cfg.producers,
        consumers=cfg.consumers,
        sent_total=sent_total,
        consumed_unique_total=consumed_unique_total,
        duplicate_count=duplicate_count,
        lost_total=lost_total,
        publish_errors=publish_errors,
        consume_errors=consume_errors,
        throughput_msg_sec=round(throughput, 3),
        avg_latency_ms=round(avg_latency, 3),
        p95_latency_ms=round(p95_latency, 3),
        max_latency_ms=round(max_latency, 3),
        backlog_peak=backlog_peak,
        backlog_samples=backlog_samples,
        degradation=degradation,
        started_at_iso=started_at,
        finished_at_iso=now_iso(),
    )

    persist_result(cfg.output_dir, result)
    return result


def persist_result(output_dir: str, result: RunResult) -> None:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / f"{result.run_id}.json"
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(asdict(result), f, ensure_ascii=False, indent=2)

    csv_path = out_dir / "results.csv"
    row = {
        "run_id": result.run_id,
        "broker": result.broker,
        "profile": result.profile,
        "msg_size": result.msg_size,
        "rate": result.rate,
        "duration": result.duration,
        "producers": result.producers,
        "consumers": result.consumers,
        "sent_total": result.sent_total,
        "consumed_unique_total": result.consumed_unique_total,
        "duplicate_count": result.duplicate_count,
        "lost_total": result.lost_total,
        "publish_errors": result.publish_errors,
        "consume_errors": result.consume_errors,
        "throughput_msg_sec": result.throughput_msg_sec,
        "avg_latency_ms": result.avg_latency_ms,
        "p95_latency_ms": result.p95_latency_ms,
        "max_latency_ms": result.max_latency_ms,
        "backlog_peak": result.backlog_peak,
        "degraded": result.degradation["is_degraded"],
        "backlog_growing": result.degradation["backlog_growing"],
        "p95_over_baseline": result.degradation["p95_over_baseline"],
        "errors_stable": result.degradation["errors_stable"],
        "repeated_loss_candidate": result.degradation["repeated_loss_candidate"],
        "started_at_iso": result.started_at_iso,
        "finished_at_iso": result.finished_at_iso,
    }

    write_header = not csv_path.exists()
    with csv_path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(row.keys()))
        if write_header:
            writer.writeheader()
        writer.writerow(row)


def summarize_results(output_dir: str) -> None:
    csv_path = Path(output_dir) / "results.csv"
    if not csv_path.exists():
        print(f"No results found in {csv_path}")
        return

    grouped: dict[tuple[str, str, int, int], list[dict[str, str]]] = {}
    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = (row["broker"], row["profile"], int(row["msg_size"]), int(row["rate"]))
            grouped.setdefault(key, []).append(row)

    summary_rows: list[dict[str, Any]] = []
    for (broker, profile, msg_size, rate), rows in grouped.items():
        throughputs = [float(r["throughput_msg_sec"]) for r in rows]
        p95s = [float(r["p95_latency_ms"]) for r in rows]
        losses = [int(r["lost_total"]) for r in rows]
        backlogs = [int(r["backlog_peak"]) for r in rows]
        summary_rows.append(
            {
                "broker": broker,
                "profile": profile,
                "msg_size": msg_size,
                "rate": rate,
                "runs": len(rows),
                "throughput_median": round(statistics.median(throughputs), 3),
                "throughput_min": round(min(throughputs), 3),
                "throughput_max": round(max(throughputs), 3),
                "p95_median": round(statistics.median(p95s), 3),
                "loss_median": int(statistics.median(losses)),
                "loss_max": max(losses),
                "backlog_peak_median": int(statistics.median(backlogs)),
            }
        )

    summary_path = Path(output_dir) / "summary.csv"
    with summary_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(summary_rows[0].keys()) if summary_rows else [])
        if summary_rows:
            writer.writeheader()
            writer.writerows(summary_rows)

    print(f"Summary written to {summary_path}")


def parse_csv_ints(value: str) -> list[int]:
    return [int(x.strip()) for x in value.split(",") if x.strip()]


def build_run_id(broker: str, profile: str, msg_size: int, rate: int, attempt: int) -> str:
    ts = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
    return f"{ts}_{broker}_{profile}_{msg_size}b_{rate}r_{attempt}"


def run_matrix(args: argparse.Namespace) -> None:
    brokers = [x.strip() for x in args.brokers.split(",") if x.strip()]
    sizes = parse_csv_ints(args.msg_sizes)
    rates = parse_csv_ints(args.rates)

    baseline_p95_by_point: dict[tuple[str, int, int], float] = {}

    for broker in brokers:
        for msg_size in sizes:
            for rate in rates:
                for attempt in range(1, args.repeats + 1):
                    baseline_run_id = build_run_id(broker, "baseline", msg_size, rate, attempt)
                    baseline_cfg = RunConfig(
                        broker=broker,
                        profile="baseline",
                        msg_size=msg_size,
                        rate=rate,
                        duration=args.duration,
                        producers=args.producers,
                        consumers=args.consumers,
                        run_id=baseline_run_id,
                        output_dir=args.output_dir,
                        sample_interval=args.sample_interval,
                        drain_timeout=args.drain_timeout,
                        backlog_window_sec=args.backlog_window_sec,
                        baseline_p95_ms=None,
                        p95_multiplier=args.p95_multiplier,
                        error_rate_threshold=args.error_rate_threshold,
                        loss_rate_threshold=args.loss_rate_threshold,
                    )
                    print(f"[RUN] {baseline_run_id}")
                    baseline_result = run_single(baseline_cfg)
                    print(json.dumps(asdict(baseline_result), ensure_ascii=False))
                    key = (broker, msg_size, rate)
                    prev = baseline_p95_by_point.get(key, 0.0)
                    baseline_p95_by_point[key] = max(prev, baseline_result.p95_latency_ms)

                    stress_run_id = build_run_id(broker, "stress", msg_size, rate, attempt)
                    stress_cfg = RunConfig(
                        broker=broker,
                        profile="stress",
                        msg_size=msg_size,
                        rate=rate,
                        duration=args.duration,
                        producers=args.producers,
                        consumers=args.consumers,
                        run_id=stress_run_id,
                        output_dir=args.output_dir,
                        sample_interval=args.sample_interval,
                        drain_timeout=args.drain_timeout,
                        backlog_window_sec=args.backlog_window_sec,
                        baseline_p95_ms=baseline_p95_by_point.get((broker, msg_size, rate)),
                        p95_multiplier=args.p95_multiplier,
                        error_rate_threshold=args.error_rate_threshold,
                        loss_rate_threshold=args.loss_rate_threshold,
                    )
                    print(f"[RUN] {stress_run_id}")
                    stress_result = run_single(stress_cfg)
                    print(json.dumps(asdict(stress_result), ensure_ascii=False))

    summarize_results(args.output_dir)


def add_common_run_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--broker", choices=["rabbitmq", "redis"], required=True)
    p.add_argument("--profile", choices=["baseline", "stress"], default="baseline")
    p.add_argument("--msg-size", type=int, required=True)
    p.add_argument("--rate", type=int, required=True)
    p.add_argument("--duration", type=int, default=120)
    p.add_argument("--producers", type=int, default=2)
    p.add_argument("--consumers", type=int, default=2)
    p.add_argument("--run-id", default=None)
    p.add_argument("--output-dir", default="results")
    p.add_argument("--sample-interval", type=float, default=1.0)
    p.add_argument("--drain-timeout", type=int, default=30)
    p.add_argument("--backlog-window-sec", type=int, default=30)
    p.add_argument("--baseline-p95-ms", type=float, default=None)
    p.add_argument("--p95-multiplier", type=float, default=2.0)
    p.add_argument("--error-rate-threshold", type=float, default=0.01)
    p.add_argument("--loss-rate-threshold", type=float, default=0.01)


def main() -> None:
    parser = argparse.ArgumentParser(description="RabbitMQ vs Redis Streams benchmark")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="Run one experiment")
    add_common_run_args(p_run)

    p_matrix = sub.add_parser("matrix", help="Run full matrix for both profiles")
    p_matrix.add_argument("--brokers", default="rabbitmq,redis")
    p_matrix.add_argument("--msg-sizes", default="128,1024,10240,102400")
    p_matrix.add_argument("--rates", default="1000,5000,10000")
    p_matrix.add_argument("--duration", type=int, default=120)
    p_matrix.add_argument("--repeats", type=int, default=3)
    p_matrix.add_argument("--producers", type=int, default=2)
    p_matrix.add_argument("--consumers", type=int, default=2)
    p_matrix.add_argument("--output-dir", default="results")
    p_matrix.add_argument("--sample-interval", type=float, default=1.0)
    p_matrix.add_argument("--drain-timeout", type=int, default=30)
    p_matrix.add_argument("--backlog-window-sec", type=int, default=30)
    p_matrix.add_argument("--p95-multiplier", type=float, default=2.0)
    p_matrix.add_argument("--error-rate-threshold", type=float, default=0.01)
    p_matrix.add_argument("--loss-rate-threshold", type=float, default=0.01)

    p_summary = sub.add_parser("summary", help="Build summary from results.csv")
    p_summary.add_argument("--output-dir", default="results")

    args = parser.parse_args()

    if args.cmd == "run":
        run_id = args.run_id or build_run_id(args.broker, args.profile, args.msg_size, args.rate, 1)
        cfg = RunConfig(
            broker=args.broker,
            profile=args.profile,
            msg_size=args.msg_size,
            rate=args.rate,
            duration=args.duration,
            producers=args.producers,
            consumers=args.consumers,
            run_id=run_id,
            output_dir=args.output_dir,
            sample_interval=args.sample_interval,
            drain_timeout=args.drain_timeout,
            backlog_window_sec=args.backlog_window_sec,
            baseline_p95_ms=args.baseline_p95_ms,
            p95_multiplier=args.p95_multiplier,
            error_rate_threshold=args.error_rate_threshold,
            loss_rate_threshold=args.loss_rate_threshold,
        )
        result = run_single(cfg)
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    elif args.cmd == "matrix":
        run_matrix(args)
    elif args.cmd == "summary":
        summarize_results(args.output_dir)


if __name__ == "__main__":
    main()
