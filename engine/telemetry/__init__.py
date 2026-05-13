"""engine.telemetry — in-flight pub/sub bus + JSONL log writer.

Two concerns live here:

* :class:`TelemetryBus` Protocol — synchronous, topic-keyed pub/sub.
  Producers (flight controller, SLAM, sensors) ``publish`` events;
  consumers (mission runner, ground-station logger) ``subscribe``.
* :class:`JSONLTelemetryLogger` — a concrete subscriber that writes
  every event as one JSON line to an append-only file. This is what
  ISC-29 ("1 Hz minimum log") draws from.

Event shape
-----------

Events are plain dicts. By convention every event has at least:

* ``topic`` (str) — the bus topic the producer published to
* ``timestamp_ns`` (int) — producer's monotonic clock
* ``payload`` (dict) — topic-specific body
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, runtime_checkable

#: One telemetry event. Dict-typed rather than dataclass so heterogeneous
#: producers can add topic-specific fields without forcing schema
#: coordination on every consumer.
TelemetryEvent = Mapping[str, Any]

#: Subscriber callback. The bus calls these synchronously on the
#: publisher's thread — callbacks must be fast and non-blocking.
TelemetryCallback = Callable[[TelemetryEvent], None]


@runtime_checkable
class TelemetryBus(Protocol):
    """Synchronous topic-keyed pub/sub.

    No backpressure, no buffering: ``publish`` calls each subscriber
    inline. A subscriber that wants async handling must hand off to a
    queue itself. This keeps the v1 bus trivial and analyzable.
    """

    def publish(self, topic: str, event: TelemetryEvent) -> None:
        """Deliver ``event`` to every subscriber of ``topic``."""
        ...

    def subscribe(self, topic: str, callback: TelemetryCallback) -> None:
        """Register ``callback`` for ``topic``. Many callbacks per topic OK."""
        ...


class InMemoryTelemetryBus:
    """In-process implementation of :class:`TelemetryBus`.

    Thread-safe for concurrent publish/subscribe via a single lock —
    subscriber lists are mutated under the lock but callbacks fire
    outside it so a slow subscriber can't block ``subscribe`` calls.
    """

    def __init__(self) -> None:
        self._subs: dict[str, list[TelemetryCallback]] = {}
        self._lock = threading.Lock()

    def publish(self, topic: str, event: TelemetryEvent) -> None:
        with self._lock:
            callbacks = list(self._subs.get(topic, ()))
        for cb in callbacks:
            cb(event)

    def subscribe(self, topic: str, callback: TelemetryCallback) -> None:
        with self._lock:
            self._subs.setdefault(topic, []).append(callback)


class JSONLTelemetryLogger:
    """Append-only JSONL file subscriber.

    Construct with a path and a bus, then call :meth:`attach` with the
    topics to record. Each event becomes one ``json.dumps(event)`` line.
    Closing is the caller's responsibility (use as a context manager or
    call :meth:`close`).
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._fh = self._path.open("a", encoding="utf-8")
        self._lock = threading.Lock()

    def attach(self, bus: TelemetryBus, *topics: str) -> None:
        for topic in topics:
            bus.subscribe(topic, self._on_event)

    def _on_event(self, event: TelemetryEvent) -> None:
        line = json.dumps(event, default=str)
        with self._lock:
            self._fh.write(line + "\n")
            self._fh.flush()

    def close(self) -> None:
        with self._lock:
            if not self._fh.closed:
                self._fh.close()

    def __enter__(self) -> "JSONLTelemetryLogger":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


__all__ = [
    "InMemoryTelemetryBus",
    "JSONLTelemetryLogger",
    "TelemetryBus",
    "TelemetryCallback",
    "TelemetryEvent",
]
