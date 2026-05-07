from __future__ import annotations

import argparse
import asyncio
import os
import statistics
import time
from typing import Any

import httpx

from loadgen.report import RunResult, append_summary, write_run_csv, write_wb_timeline
from loadgen.workload import PROFILES, Profile, ZipfKeySpace, pick_op, random_payload


APP_URL = os.getenv("APP_URL", "http://app:8000")
N_KEYS = int(os.getenv("N_KEYS", "10000"))
DURATION = int(os.getenv("DURATION", "60"))
CONCURRENCY = int(os.getenv("CONCURRENCY", "100"))
PAYLOAD_SIZE = int(os.getenv("PAYLOAD_SIZE", "256"))
RESULTS_DIR = os.getenv("RESULTS_DIR", "/results")
WB_TAIL_WAIT = int(os.getenv("WB_TAIL_WAIT", "10"))
ZIPF_ALPHA = float(os.getenv("ZIPF_ALPHA", "1.2"))


async def reset_app(client: httpx.AsyncClient) -> None:
    r = await client.post(f"{APP_URL}/admin/reset")
    r.raise_for_status()


async def fetch_metrics(client: httpx.AsyncClient) -> dict[str, Any]:
    r = await client.get(f"{APP_URL}/metrics")
    r.raise_for_status()
    return r.json()


async def fetch_health(client: httpx.AsyncClient) -> dict[str, Any]:
    r = await client.get(f"{APP_URL}/healthz")
    r.raise_for_status()
    return r.json()


async def wait_for_app(timeout: int = 120) -> dict[str, Any]:
    deadline = time.time() + timeout
    last_err: Exception | None = None
    async with httpx.AsyncClient(timeout=5.0) as c:
        while time.time() < deadline:
            try:
                return await fetch_health(c)
            except Exception as e:
                last_err = e
                await asyncio.sleep(1)
    raise RuntimeError(f"app not ready: {last_err}")


async def worker(
    client: httpx.AsyncClient,
    profile: Profile,
    keys: ZipfKeySpace,
    stop_at: float,
    latencies: list[float],
    counters: dict[str, int],
) -> None:
    while time.monotonic() < stop_at:
        op = pick_op(profile.read_ratio)
        item_id = keys.next_key()
        t0 = time.monotonic()
        try:
            if op == "read":
                r = await client.get(f"{APP_URL}/items/{item_id}")
            else:
                r = await client.put(
                    f"{APP_URL}/items/{item_id}",
                    json={"payload": random_payload(PAYLOAD_SIZE)},
                )
            if r.status_code >= 400 and r.status_code != 404:
                counters["errors"] += 1
            else:
                latencies.append((time.monotonic() - t0) * 1000.0)
                counters[op] += 1
        except Exception:
            counters["errors"] += 1


async def sample_wb(client: httpx.AsyncClient, samples: list[tuple[float, int, int, int]], started: float, stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            m = await fetch_metrics(client)
            samples.append(
                (
                    time.monotonic() - started,
                    int(m.get("wb_queue_size", 0)),
                    int(m.get("wb_flushes", 0)),
                    int(m.get("wb_flushed_rows", 0)),
                )
            )
        except Exception:
            pass
        try:
            await asyncio.wait_for(stop.wait(), timeout=1.0)
        except asyncio.TimeoutError:
            pass


def percentile(data: list[float], p: float) -> float:
    if not data:
        return 0.0
    data_sorted = sorted(data)
    k = max(0, min(len(data_sorted) - 1, int(round((p / 100.0) * (len(data_sorted) - 1)))))
    return data_sorted[k]


async def run_one(profile: Profile, strategy_name: str) -> RunResult:
    print(f"\n=== run: strategy={strategy_name} profile={profile.name} duration={DURATION}s clients={CONCURRENCY} keys={N_KEYS} ===", flush=True)
    limits = httpx.Limits(max_connections=CONCURRENCY * 2, max_keepalive_connections=CONCURRENCY)
    timeout = httpx.Timeout(10.0)

    latencies: list[float] = []
    counters: dict[str, int] = {"read": 0, "write": 0, "errors": 0}
    wb_samples: list[tuple[float, int, int, int]] = []

    async with httpx.AsyncClient(limits=limits, timeout=timeout) as client:
        await reset_app(client)
        keys = ZipfKeySpace(N_KEYS, alpha=ZIPF_ALPHA, seed=42)
        started = time.monotonic()
        stop_at = started + DURATION

        sampler_stop = asyncio.Event()
        sampler_task = (
            asyncio.create_task(sample_wb(client, wb_samples, started, sampler_stop))
            if strategy_name == "write_back"
            else None
        )

        workers = [
            asyncio.create_task(worker(client, profile, keys, stop_at, latencies, counters))
            for _ in range(CONCURRENCY)
        ]
        await asyncio.gather(*workers)
        actual_duration = time.monotonic() - started

        if sampler_task is not None:
            await asyncio.sleep(WB_TAIL_WAIT)
            sampler_stop.set()
            await sampler_task

        m = await fetch_metrics(client)

    requests_done = counters["read"] + counters["write"]
    throughput = requests_done / actual_duration if actual_duration > 0 else 0.0
    cache_hits = int(m.get("cache_hits", 0))
    cache_misses = int(m.get("cache_misses", 0))
    hit_rate = cache_hits / (cache_hits + cache_misses) if (cache_hits + cache_misses) else 0.0

    result = RunResult(
        strategy=strategy_name,
        profile=profile.name,
        duration_s=round(actual_duration, 3),
        requests_total=requests_done,
        read_total=counters["read"],
        write_total=counters["write"],
        errors=counters["errors"],
        throughput_rps=round(throughput, 2),
        avg_latency_ms=round(statistics.fmean(latencies) if latencies else 0.0, 3),
        p50_latency_ms=round(percentile(latencies, 50), 3),
        p95_latency_ms=round(percentile(latencies, 95), 3),
        p99_latency_ms=round(percentile(latencies, 99), 3),
        db_reads=int(m.get("db_reads", 0)),
        db_writes=int(m.get("db_writes", 0)),
        cache_hits=cache_hits,
        cache_misses=cache_misses,
        hit_rate=round(hit_rate, 4),
        redis_keyspace_hits=int(m.get("redis_keyspace_hits", 0)),
        redis_keyspace_misses=int(m.get("redis_keyspace_misses", 0)),
        wb_queue_size_end=int(m.get("wb_queue_size", 0)),
        wb_flushes=int(m.get("wb_flushes", 0)),
        wb_flushed_rows=int(m.get("wb_flushed_rows", 0)),
    )

    os.makedirs(RESULTS_DIR, exist_ok=True)
    write_run_csv(
        os.path.join(RESULTS_DIR, f"latencies_{strategy_name}_{profile.name}.csv"),
        latencies,
    )
    if wb_samples:
        write_wb_timeline(
            os.path.join(RESULTS_DIR, f"wb_timeline_{strategy_name}_{profile.name}.csv"),
            wb_samples,
        )
    append_summary(os.path.join(RESULTS_DIR, "summary.csv"), result)
    print_result(result)
    return result


def print_result(r: RunResult) -> None:
    print(
        f"  -> rps={r.throughput_rps:.1f} avg={r.avg_latency_ms:.2f}ms "
        f"p95={r.p95_latency_ms:.2f}ms hit_rate={r.hit_rate*100:.1f}% "
        f"db_reads={r.db_reads} db_writes={r.db_writes} "
        f"wb(flushes={r.wb_flushes},rows={r.wb_flushed_rows},queue_end={r.wb_queue_size_end})",
        flush=True,
    )


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", required=True, help="cache_aside|write_through|write_back")
    parser.add_argument("--profile", default=None, help="run only one profile by name")
    args = parser.parse_args()

    health = await wait_for_app()
    actual = health.get("strategy")
    if actual != args.strategy:
        raise SystemExit(
            f"app reports strategy={actual!r} but runner was asked for {args.strategy!r}; "
            "перезапусти контейнер app с нужным CACHE_STRATEGY"
        )

    profiles = PROFILES if args.profile is None else [p for p in PROFILES if p.name == args.profile]
    if not profiles:
        raise SystemExit(f"unknown profile: {args.profile}")

    for profile in profiles:
        await run_one(profile, args.strategy)


if __name__ == "__main__":
    asyncio.run(main())
