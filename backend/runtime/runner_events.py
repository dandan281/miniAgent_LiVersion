"""Per-session event bus for long-running tool/runner progress.

The chat SSE stream in ``backend/runtime/chat_runtime.py`` is bounded to a
single conversational turn, but runners like AlphaFold2 (5–60 min on Superbio)
outlive any single turn — the user may send another message before the job
finishes. This module provides a complementary out-of-band channel:

  - Producers (runner code) call :func:`emit_runner_event` synchronously.
  - Consumers (the ``GET /api/runners/events`` SSE endpoint) subscribe per
    session and stream events. Late joiners can pass ``since_event_index`` to
    replay buffered events from a bounded ring buffer.

Why polling, not asyncio queues: runners are synchronous Python code that may
run inside thread pools or workflow executors. A polling consumer keeps the
producer side trivially safe (just a lock + ring buffer). Runner events fire
at most every ~10s, so a 0.5s SSE poll is more than fast enough.

The bus is in-process. If we ever scale beyond a single uvicorn worker, swap
the in-memory ring for Redis Streams without changing the producer/consumer
contracts.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from contextvars import ContextVar
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict

# Ring buffer size per session. A long AF2 run emits ~1 event/30s plus a
# heartbeat every 10s ≈ 4 events/min ≈ 240/hour; 500 covers a couple of hours
# of multi-runner activity before the oldest events roll off.
_RING_BUFFER_SIZE = 500

# Public set of valid phases. Kept open enough for tool-specific extension
# (a tool can use any string), but these are the canonical ones the UI knows
# how to render with first-class styling.
CANONICAL_PHASES = frozenset({
    "queued",
    "running",
    "downloading",
    "done",
    "failed",
    "heartbeat",
})


class RunnerEvent(BaseModel):
    """A single runner progress event.

    ``event_index`` is monotonic per session_id, assigned by the bus on emit,
    so consumers can resume by passing ``since_event_index`` and trust ordering.
    """

    model_config = ConfigDict(extra="forbid")

    session_id: str
    job_id: str
    tool: str
    phase: str
    timestamp: float
    event_index: int

    percent: float | None = None
    eta_s: float | None = None
    elapsed_s: float | None = None
    log_tail: str | None = None
    payload: dict[str, Any] | None = None


# ContextVar lets emitters inside deeply-nested code (workflow runners, tool
# wrappers) implicitly find the active session without threading session_id
# through every signature. Set by the chat runtime at the start of a turn and
# by any code that spawns a long-running runner from a known session.
current_session_id: ContextVar[str | None] = ContextVar(
    "runner_events_current_session_id",
    default=None,
)


class _SessionState:
    """Per-session ring buffer + monotonic counter."""

    __slots__ = ("buffer", "next_index", "_lock")

    def __init__(self) -> None:
        self.buffer: deque[RunnerEvent] = deque(maxlen=_RING_BUFFER_SIZE)
        self.next_index: int = 1
        self._lock = threading.Lock()

    def append(self, event_data: dict[str, Any]) -> RunnerEvent:
        with self._lock:
            event = RunnerEvent(
                event_index=self.next_index,
                timestamp=event_data.pop("timestamp", time.time()),
                **event_data,
            )
            self.next_index += 1
            self.buffer.append(event)
            return event

    def snapshot(self, since_event_index: int) -> list[RunnerEvent]:
        with self._lock:
            if since_event_index <= 0:
                return list(self.buffer)
            return [e for e in self.buffer if e.event_index > since_event_index]

    def latest_for_job(self, job_id: str) -> RunnerEvent | None:
        with self._lock:
            for event in reversed(self.buffer):
                if event.job_id == job_id:
                    return event
            return None

    def latest_index(self) -> int:
        with self._lock:
            return self.next_index - 1


class RunnerEventBus:
    """In-process per-session pub/sub for runner events."""

    def __init__(self) -> None:
        self._sessions: dict[str, _SessionState] = {}
        self._lock = threading.Lock()

    def _state(self, session_id: str) -> _SessionState:
        with self._lock:
            state = self._sessions.get(session_id)
            if state is None:
                state = _SessionState()
                self._sessions[session_id] = state
            return state

    def emit(
        self,
        *,
        session_id: str,
        job_id: str,
        tool: str,
        phase: str,
        percent: float | None = None,
        eta_s: float | None = None,
        elapsed_s: float | None = None,
        log_tail: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> RunnerEvent:
        return self._state(session_id).append({
            "session_id": session_id,
            "job_id": job_id,
            "tool": tool,
            "phase": phase,
            "percent": percent,
            "eta_s": eta_s,
            "elapsed_s": elapsed_s,
            "log_tail": log_tail,
            "payload": payload,
        })

    def events_since(self, session_id: str, since_event_index: int) -> list[RunnerEvent]:
        return self._state(session_id).snapshot(since_event_index)

    def latest_for_job(self, session_id: str, job_id: str) -> RunnerEvent | None:
        return self._state(session_id).latest_for_job(job_id)

    def latest_index(self, session_id: str) -> int:
        return self._state(session_id).latest_index()

    def reset(self) -> None:
        """Test helper — drop all buffered state."""
        with self._lock:
            self._sessions.clear()


_bus = RunnerEventBus()


def get_runner_event_bus() -> RunnerEventBus:
    return _bus


def emit_runner_event(
    *,
    job_id: str,
    tool: str,
    phase: str,
    session_id: str | None = None,
    percent: float | None = None,
    eta_s: float | None = None,
    elapsed_s: float | None = None,
    log_tail: str | None = None,
    payload: dict[str, Any] | None = None,
) -> RunnerEvent | None:
    """Sync, fire-and-forget emitter for runner code.

    Returns ``None`` if no session context is available (e.g., a runner
    invoked from a CLI script with no chat session). Emitters should not need
    to care — observability simply degrades to "not visible in UI" rather than
    crashing the runner.
    """
    sid = session_id if session_id is not None else current_session_id.get()
    if not sid:
        return None
    return _bus.emit(
        session_id=sid,
        job_id=job_id,
        tool=tool,
        phase=phase,
        percent=percent,
        eta_s=eta_s,
        elapsed_s=elapsed_s,
        log_tail=log_tail,
        payload=payload,
    )


def serialize_events(events: Iterable[RunnerEvent]) -> list[dict[str, Any]]:
    return [e.model_dump(exclude_none=True) for e in events]
