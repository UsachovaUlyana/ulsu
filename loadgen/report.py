from __future__ import annotations

import csv
import os
from dataclasses import asdict, dataclass


@dataclass
class RunResult:
    strategy: str
    profile: str
    duration_s: float
    requests_total: int
    read_total: int
    write_total: int
    errors: int
    throughput_rps: float
    avg_latency_ms: float
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    db_reads: int
    db_writes: int
    cache_hits: int
    cache_misses: int
    hit_rate: float
    redis_keyspace_hits: int
    redis_keyspace_misses: int
    wb_queue_size_end: int
    wb_flushes: int
    wb_flushed_rows: int


SUMMARY_HEADERS = list(RunResult.__dataclass_fields__.keys())


def append_summary(path: str, result: RunResult) -> None:
    new_file = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SUMMARY_HEADERS)
        if new_file:
            w.writeheader()
        w.writerow(asdict(result))


def write_run_csv(path: str, latencies_ms: list[float]) -> None:
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["i", "latency_ms"])
        for i, lat in enumerate(latencies_ms):
            w.writerow([i, f"{lat:.3f}"])


def write_wb_timeline(path: str, samples: list[tuple[float, int, int, int]]) -> None:
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t_s", "wb_queue_size", "wb_flushes", "wb_flushed_rows"])
        for row in samples:
            w.writerow([f"{row[0]:.2f}", row[1], row[2], row[3]])
