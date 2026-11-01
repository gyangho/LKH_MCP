"""Bounded allowlisted Codex event telemetry queue; never buffers raw JSONL output."""
from collections import deque
import time

EVENT_TYPES = frozenset({"started", "turn_started", "turn_completed", "item_started",
    "item_completed", "item_failed", "command_started", "command_completed",
    "command_failed", "heartbeat", "error", "finished"})
PHASES = frozenset({"codex", "git", "build", "test", "graphify", "cleanup", "unknown"})


class EventOutbox:
    def __init__(self, send, *, clock=None, capacity=128, batch_size=16, flush_interval=2.0):
        if not callable(send) or not 1 <= batch_size <= capacity <= 2000:
            raise ValueError("Invalid outbox settings")
        self._send, self._clock = send, clock or time.monotonic
        self._queue, self._cap, self._batch = deque(), capacity, batch_size
        self._interval, self._last, self._seq = flush_interval, self._clock(), 0
        self.dropped = 0
        self.last_error = ""

    @property
    def pending(self):
        return len(self._queue)

    def emit(self, event_type, phase):
        if event_type not in EVENT_TYPES or phase not in PHASES:
            raise ValueError("Unsupported telemetry fields")
        if self._seq >= 2000:
            self.dropped += 1
            return
        self._seq += 1
        if len(self._queue) >= self._cap:
            self._queue.popleft()
            self.dropped += 1
        self._queue.append({"seq": self._seq, "type": event_type, "phase": phase})
        if len(self._queue) >= self._batch or self._clock() - self._last >= self._interval:
            self.flush()

    def flush(self, *, attempts=1):
        if not 1 <= attempts <= 5:
            raise ValueError("Invalid attempts")
        delivered = 0
        for retry in range(attempts):
            while self._queue:
                batch = list(self._queue)[:self._batch]
                try:
                    self._send(batch)
                except (OSError, ValueError, RuntimeError) as exc:
                    self.last_error = type(exc).__name__
                    break
                for _ in batch:
                    self._queue.popleft()
                delivered += len(batch)
                self.last_error = ""
                self._last = self._clock()
            if not self._queue:
                break
            if retry + 1 < attempts:
                time.sleep(min(0.5 * 2 ** retry, 2))
        return delivered
