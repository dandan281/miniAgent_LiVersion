"""Tests for runner_events bus + /api/runners snapshot / artifact endpoints."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

# Loopback client tuple — the access-control layer treats 127.0.0.1 as
# trusted, which is what TestClient effectively is.
_LOOPBACK_CLIENT = ("127.0.0.1", 50000)
_VALID_SID = "11111111-2222-3333-4444-555555555555"


@pytest.fixture
def fresh_bus():
    from runtime.runner_events import get_runner_event_bus

    bus = get_runner_event_bus()
    bus.reset()
    yield bus
    bus.reset()


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    """Bring up the FastAPI app for endpoint tests with a sandboxed base_dir."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test")
    monkeypatch.setenv("OPENAI_API_KEY", "test")

    from app import app
    from graph.agent import agent_manager

    # Use the lifespan so the manager initializes; it picks up the real backend
    # base_dir, which is fine — we never write to it in these tests.
    with TestClient(app, client=_LOOPBACK_CLIENT) as client:
        yield client


# ───────────────────────── unit: RunnerEventBus ──────────────────────────

def test_emit_assigns_monotonic_event_index_per_session(fresh_bus):
    e1 = fresh_bus.emit(
        session_id="s1",
        job_id="j1",
        tool="alphafold2",
        phase="queued",
    )
    e2 = fresh_bus.emit(
        session_id="s1",
        job_id="j1",
        tool="alphafold2",
        phase="running",
    )
    e_other = fresh_bus.emit(
        session_id="s2",
        job_id="j1",
        tool="alphafold2",
        phase="queued",
    )

    assert e1.event_index == 1
    assert e2.event_index == 2
    # Different session has its own counter.
    assert e_other.event_index == 1


def test_events_since_filters_by_cursor(fresh_bus):
    fresh_bus.emit(session_id="s1", job_id="j1", tool="alphafold2", phase="queued")
    second = fresh_bus.emit(
        session_id="s1", job_id="j1", tool="alphafold2", phase="running"
    )

    assert fresh_bus.events_since("s1", 0) == [
        fresh_bus.events_since("s1", 0)[0],
        second,
    ]
    assert fresh_bus.events_since("s1", 1) == [second]
    assert fresh_bus.events_since("s1", 2) == []


def test_latest_for_job_returns_most_recent(fresh_bus):
    fresh_bus.emit(session_id="s1", job_id="j1", tool="alphafold2", phase="queued")
    fresh_bus.emit(session_id="s1", job_id="j1", tool="alphafold2", phase="running")
    fresh_bus.emit(session_id="s1", job_id="j2", tool="boltz", phase="queued")

    latest_j1 = fresh_bus.latest_for_job("s1", "j1")
    assert latest_j1 is not None
    assert latest_j1.phase == "running"

    latest_j2 = fresh_bus.latest_for_job("s1", "j2")
    assert latest_j2 is not None
    assert latest_j2.tool == "boltz"

    assert fresh_bus.latest_for_job("s1", "missing") is None


def test_emit_runner_event_uses_contextvar(fresh_bus):
    from runtime.runner_events import current_session_id, emit_runner_event

    # No context → returns None, but doesn't raise.
    assert emit_runner_event(job_id="j", tool="t", phase="queued") is None

    token = current_session_id.set("s-ctx")
    try:
        e = emit_runner_event(job_id="j", tool="t", phase="queued")
    finally:
        current_session_id.reset(token)

    assert e is not None
    assert e.session_id == "s-ctx"
    assert fresh_bus.latest_index("s-ctx") == 1


def test_ring_buffer_bounded(fresh_bus, monkeypatch):
    # Force a tiny ring buffer to exercise the eviction path quickly.
    from runtime import runner_events as mod

    monkeypatch.setattr(mod, "_RING_BUFFER_SIZE", 3)
    # Reinstall the bus so it uses the new size.
    fresh_bus._sessions.clear()

    # Build a custom bus with the smaller buffer by re-importing class from
    # the module — our singleton uses the constant via _SessionState.append's
    # deque, so we instantiate _SessionState fresh.
    from runtime.runner_events import _SessionState

    state = _SessionState()
    state.buffer = type(state.buffer)(maxlen=3)  # explicit fresh deque(maxlen=3)
    for i in range(5):
        state.append(
            {
                "session_id": "s",
                "job_id": "j",
                "tool": "t",
                "phase": f"p{i}",
            }
        )

    # Only the last 3 events survive; their indices are 3, 4, 5.
    surviving = list(state.buffer)
    assert [e.event_index for e in surviving] == [3, 4, 5]
    assert [e.phase for e in surviving] == ["p2", "p3", "p4"]


# ───────────────────── endpoint: /api/runners/{tool}/{job}/status ───────

def test_status_endpoint_404_when_no_events(app_client, fresh_bus):
    r = app_client.get(
        "/api/runners/alphafold2/jobX/status",
        params={"session_id": _VALID_SID},
    )
    assert r.status_code == 404


def test_status_endpoint_200_after_emit(app_client, fresh_bus):
    fresh_bus.emit(
        session_id=_VALID_SID,
        job_id="jobX",
        tool="alphafold2",
        phase="running",
        elapsed_s=12.5,
        eta_s=300.0,
    )
    r = app_client.get(
        "/api/runners/alphafold2/jobX/status",
        params={"session_id": _VALID_SID},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["phase"] == "running"
    assert body["elapsed_s"] == 12.5
    # exclude_none drops empty fields.
    assert "log_tail" not in body


def test_status_endpoint_404_on_tool_mismatch(app_client, fresh_bus):
    fresh_bus.emit(
        session_id=_VALID_SID,
        job_id="jobX",
        tool="alphafold2",
        phase="queued",
    )
    r = app_client.get(
        "/api/runners/boltz/jobX/status",
        params={"session_id": _VALID_SID},
    )
    assert r.status_code == 404


def test_status_endpoint_400_on_bad_session_id(app_client, fresh_bus):
    r = app_client.get(
        "/api/runners/alphafold2/jobX/status",
        params={"session_id": "../traversal-attempt"},
    )
    assert r.status_code == 400


# ─────────────────── endpoint: /api/runners/artifact ─────────────────────

def test_artifact_endpoint_rejects_bad_extension(app_client):
    r = app_client.get(
        "/api/runners/artifact",
        params={"tool": "alphafold2", "path": "evil.exe"},
    )
    assert r.status_code == 403


def test_artifact_endpoint_rejects_path_traversal(app_client):
    r = app_client.get(
        "/api/runners/artifact",
        params={"tool": "alphafold2", "path": "../../etc/passwd"},
    )
    assert r.status_code == 403


def test_artifact_endpoint_rejects_bad_tool_name(app_client):
    r = app_client.get(
        "/api/runners/artifact",
        params={"tool": "../etc", "path": "foo.pdb"},
    )
    assert r.status_code == 400


def test_artifact_endpoint_404_for_missing_file(app_client):
    r = app_client.get(
        "/api/runners/artifact",
        params={
            "tool": "alphafold2",
            "path": "this_path/does_not_exist/sample.pdb",
        },
    )
    # Either 404 (resolved cleanly but file absent) or 403 if the tool dir
    # itself is missing — both are acceptable safe-failure modes.
    assert r.status_code in (403, 404)


# ─────────────────── unit: SSE replay cursor semantics ──────────────────
#
# The SSE endpoint is an open-ended stream that can't be cleanly drained by
# the synchronous TestClient (iter_lines blocks on the keepalive timer). The
# replay-from-cursor logic itself lives in the bus, though, so we cover it
# directly here — the endpoint is just a thin formatting layer over this.

def test_resume_cursor_returns_only_newer_events(fresh_bus):
    fresh_bus.emit(session_id=_VALID_SID, job_id="j", tool="alphafold2", phase="queued")
    fresh_bus.emit(session_id=_VALID_SID, job_id="j", tool="alphafold2", phase="running")
    fresh_bus.emit(
        session_id=_VALID_SID, job_id="j", tool="alphafold2", phase="downloading"
    )

    after_first = fresh_bus.events_since(_VALID_SID, 1)
    assert [e.event_index for e in after_first] == [2, 3]
    assert [e.phase for e in after_first] == ["running", "downloading"]

    after_all = fresh_bus.events_since(_VALID_SID, 3)
    assert after_all == []
