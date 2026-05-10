"""Runner progress endpoints — out-of-band SSE channel for long-running jobs.

Two routes:

  GET /api/runners/events?session_id=&since_event_index=
      SSE subscription. Replays buffered events strictly after
      ``since_event_index`` (0 ⇒ replay everything still in the ring buffer),
      then streams live events as they're emitted. The connection lives until
      the client disconnects; there is no idle timeout (heartbeat events from
      runners keep proxies happy on their own).

  GET /api/runners/{tool}/{job_id}/status?session_id=
      Snapshot of the most recent event for a given (session, tool, job).
      Useful for late-joining UIs that already know a job_id (e.g., from a
      saved session) and want to render its current state without subscribing.

This sits beside the chat SSE (``/api/chat``), which is per-turn. Runners
outlive turns; the UI can keep the runners channel open across many chat
turns.
"""
from __future__ import annotations

import asyncio
import json
import mimetypes
from pathlib import Path
from typing import AsyncGenerator

from access_control import require_inspection_access
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse

from graph.session_manager import _validate_session_id
from runtime.runner_events import (
    get_runner_event_bus,
    serialize_events,
)

router = APIRouter()

# Poll interval for the SSE consumer when there are no new events. Runner
# events fire every ~10s at most (heartbeat cadence), so 0.5s is responsive
# without being wasteful.
_POLL_INTERVAL_S = 0.5

# How long to wait between explicit ":keepalive" comments so intermediate
# proxies don't drop the connection during quiet periods. SSE comments are
# silently discarded by EventSource clients.
_KEEPALIVE_INTERVAL_S = 15.0

# Repo-level artifact root (sibling of backend/), where workflow runners
# materialize outputs under ``<repo>/artifacts/<tool>/<date>/<run_hash>/...``.
# Resolved lazily so tests that monkey-patch the layout still work.
def _artifacts_root() -> Path:
    from graph.agent import agent_manager

    assert agent_manager.base_dir is not None
    return (Path(agent_manager.base_dir).resolve().parent / "artifacts").resolve()


# Extensions allowed via the artifact endpoint. Keep this tight: only the
# file types a UI legitimately needs to render runner outputs.
_ARTIFACT_ALLOWED_SUFFIXES = frozenset({
    ".pdb",
    ".cif",
    ".json",
    ".png",
    ".jpg",
    ".jpeg",
    ".svg",
    ".txt",
    ".log",
    ".tsv",
    ".csv",
    ".fa",
    ".fasta",
    ".faa",
    ".md",
    ".yaml",
    ".yml",
})

# Safety cap so the endpoint can never accidentally stream a giant binary
# (e.g. an h5ad atlas file). Structure files top out around 1–2 MB.
_ARTIFACT_MAX_BYTES = 25 * 1024 * 1024  # 25 MB


def _validate_session(session_id: str) -> None:
    try:
        _validate_session_id(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session_id")


@router.get("/runners/events")
async def runner_events_stream(
    request: Request,
    session_id: str = Query(..., description="Session whose runners to follow"),
    since_event_index: int = Query(
        0,
        ge=0,
        description="Resume from this event_index (exclusive). 0 ⇒ replay all buffered events.",
    ),
):
    require_inspection_access(request)
    _validate_session(session_id)

    bus = get_runner_event_bus()

    async def _generate() -> AsyncGenerator[str, None]:
        last_index = since_event_index
        last_keepalive = asyncio.get_event_loop().time()

        # Replay any buffered events strictly after the resume cursor.
        backlog = bus.events_since(session_id, last_index)
        for payload in serialize_events(backlog):
            last_index = payload["event_index"]
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

        while True:
            if await request.is_disconnected():
                return

            new_events = bus.events_since(session_id, last_index)
            if new_events:
                for payload in serialize_events(new_events):
                    last_index = payload["event_index"]
                    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                last_keepalive = asyncio.get_event_loop().time()
            else:
                now = asyncio.get_event_loop().time()
                if now - last_keepalive >= _KEEPALIVE_INTERVAL_S:
                    yield ": keepalive\n\n"
                    last_keepalive = now

            await asyncio.sleep(_POLL_INTERVAL_S)

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/runners/{tool}/{job_id}/status")
def runner_job_status(
    tool: str,
    job_id: str,
    request: Request,
    session_id: str = Query(..., description="Session that owns the job"),
):
    require_inspection_access(request)
    _validate_session(session_id)

    bus = get_runner_event_bus()
    event = bus.latest_for_job(session_id, job_id)
    if event is None or event.tool != tool:
        raise HTTPException(
            status_code=404,
            detail=f"No runner events found for tool={tool!r} job_id={job_id!r} in this session.",
        )
    return event.model_dump(exclude_none=True)


def _resolve_artifact(tool: str, relative_path: str) -> Path:
    """Resolve ``<repo>/artifacts/<tool>/<relative_path>`` with full safety checks.

    Rejects path traversal, absolute paths, disallowed extensions, and files
    that resolve outside the per-tool artifact root.
    """
    if not tool or "/" in tool or ".." in tool or tool.startswith("."):
        raise HTTPException(400, "Invalid tool identifier.")

    clean = relative_path.strip().lstrip("/").removeprefix("./")
    if not clean:
        raise HTTPException(400, "Empty path.")
    if ".." in clean.split("/"):
        raise HTTPException(403, "Path traversal is not allowed.")
    if Path(clean).is_absolute():
        raise HTTPException(400, "Path must be relative.")

    tool_root = (_artifacts_root() / tool).resolve()
    candidate = (tool_root / clean).resolve()

    try:
        candidate.relative_to(tool_root)
    except ValueError:
        raise HTTPException(403, "Path resolves outside the tool artifact root.")

    if candidate.suffix.lower() not in _ARTIFACT_ALLOWED_SUFFIXES:
        raise HTTPException(
            403,
            f"Extension {candidate.suffix!r} not allowed. Permitted: "
            f"{sorted(_ARTIFACT_ALLOWED_SUFFIXES)}",
        )

    return candidate


@router.get("/runners/artifact")
def get_runner_artifact(
    request: Request,
    tool: str = Query(..., description="Runner / tool name (matches RunnerEvent.tool)"),
    path: str = Query(..., description="Path relative to <repo>/artifacts/<tool>/"),
):
    """Serve a runner output file (PDB / CIF / pLDDT JSON / etc.).

    The path is resolved under ``<repo>/artifacts/<tool>/`` only; nothing
    outside that subtree is reachable. Extensions are whitelisted.
    """
    require_inspection_access(request)

    target = _resolve_artifact(tool, path)
    if not target.exists():
        raise HTTPException(404, f"Artifact not found: tool={tool} path={path}")
    if not target.is_file():
        raise HTTPException(400, f"Not a file: {path}")

    size = target.stat().st_size
    if size > _ARTIFACT_MAX_BYTES:
        raise HTTPException(413, f"Artifact too large: {size} bytes (max {_ARTIFACT_MAX_BYTES}).")

    media_type, _ = mimetypes.guess_type(target.name)
    if media_type is None:
        suffix = target.suffix.lower()
        if suffix in {".pdb", ".cif"}:
            media_type = "chemical/x-pdb" if suffix == ".pdb" else "chemical/x-cif"
        elif suffix == ".json":
            media_type = "application/json"
        elif suffix in {".fa", ".fasta", ".faa"}:
            media_type = "text/x-fasta"
        else:
            media_type = "application/octet-stream"

    return Response(content=target.read_bytes(), media_type=media_type)
