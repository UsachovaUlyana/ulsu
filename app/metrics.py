from __future__ import annotations

import threading
from dataclasses import dataclass, field


@dataclass
class Metrics:
    requests_total: int = 0
    read_total: int = 0
    write_total: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    db_reads: int = 0
    db_writes: int = 0
    wb_queue_size: int = 0
    wb_flushes: int = 0
    wb_flushed_rows: int = 0
    errors: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def incr(self, name: str, value: int = 1) -> None:
        with self._lock:
            setattr(self, name, getattr(self, name) + value)

    def set_value(self, name: str, value: int) -> None:
        with self._lock:
            setattr(self, name, value)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "requests_total": self.requests_total,
                "read_total": self.read_total,
                "write_total": self.write_total,
                "cache_hits": self.cache_hits,
                "cache_misses": self.cache_misses,
                "db_reads": self.db_reads,
                "db_writes": self.db_writes,
                "wb_queue_size": self.wb_queue_size,
                "wb_flushes": self.wb_flushes,
                "wb_flushed_rows": self.wb_flushed_rows,
                "errors": self.errors,
            }

    def reset(self) -> None:
        with self._lock:
            self.requests_total = 0
            self.read_total = 0
            self.write_total = 0
            self.cache_hits = 0
            self.cache_misses = 0
            self.db_reads = 0
            self.db_writes = 0
            self.wb_queue_size = 0
            self.wb_flushes = 0
            self.wb_flushed_rows = 0
            self.errors = 0


metrics = Metrics()
