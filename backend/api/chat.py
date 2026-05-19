"""
POST /api/chat — SSE streaming conversation endpoint.

All emitted events include:
  request_id   stable per-turn identifier
  event_index  monotonic 1-based sequence number within the stream

SSE event types emitted:
  retrieval    {type, query, results}
  token        {type, content}
  tool_start   {type, tool, input, run_id}
  tool_end     {type, tool, output, result, run_id}
  plan_created {type, summary, plan, tool_trace?, run_id?}
  plan_updated {type, summary, plan, tool_trace?, run_id?}
  verification_result {type, summary, verdict, verification, tool_trace?, run_id?}
  new_response {type}
  done         {type, content, session_id}
  error        {type, error}
"""
from access_control import require_execution_access
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, field_validator
from typing import List

from graph.session_manager import _validate_session_id
from runtime.chat_runtime import ChatRuntime, ChatStreamInput

router = APIRouter()

_MAX_MESSAGE_LEN = 32_000  # ~8 k tokens; prevents context blowout and large session files
_MAX_FILE_CONTEXT_CHARS = 60_000  # cap on total injected file text


_GPU_CONTEXT = (
    "[GPU_TASK] The user has flagged this as a GPU-compute task. "
    "When writing code: prefer vectorised operations (numpy/cupy/torch), "
    "use batch processing, leverage CUDA/GPU-accelerated libraries where available "
    "(RAPIDS, cuML, cuDF, torch.cuda), and note in your answer which operations "
    "are GPU-accelerated. Structure long-running steps as scripts that can be "
    "submitted to a GPU cluster or run with CUDA."
)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str
    session_id: str
    file_ids: List[str] = []
    gpu_mode: bool = False

    @field_validator("message")
    @classmethod
    def _check_message_length(cls, value: str) -> str:
        if len(value) > _MAX_MESSAGE_LEN:
            raise ValueError(f"message too long (max {_MAX_MESSAGE_LEN} characters)")
        return value


def _build_message_with_context(
    message: str, session_id: str, file_ids: list[str], gpu_mode: bool
) -> str:
    msg = _build_message_with_files(message, session_id, file_ids)
    if gpu_mode:
        msg = f"{_GPU_CONTEXT}\n\n{msg}"
    return msg


def _build_message_with_files(message: str, session_id: str, file_ids: list[str]) -> str:
    """Prepend extracted file content to the user message as labelled context blocks."""
    if not file_ids:
        return message
    from api.uploads import load_file_texts
    records = load_file_texts(session_id, file_ids)
    if not records:
        return message

    parts: list[str] = []
    total_chars = 0
    for rec in records:
        text: str = rec.get("extracted_text", "")
        if not text.strip():
            continue
        remaining = _MAX_FILE_CONTEXT_CHARS - total_chars
        if remaining <= 0:
            break
        excerpt = text[:remaining]
        total_chars += len(excerpt)
        parts.append(
            f"<attached_file name=\"{rec['filename']}\" type=\"{rec['file_type']}\">\n"
            f"{excerpt}\n"
            f"</attached_file>"
        )

    if not parts:
        return message
    file_block = "\n\n".join(parts)
    return f"{file_block}\n\n---\n\n{message}"


@router.post("/chat")
async def chat(request: ChatRequest, http_request: Request = None):
    require_execution_access(http_request)
    try:
        _validate_session_id(request.session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session_id")

    from graph.agent import agent_manager

    effective_message = _build_message_with_context(
        request.message, request.session_id, request.file_ids, request.gpu_mode
    )

    runtime = ChatRuntime(agent_manager)
    stream = runtime.stream_turn(
        ChatStreamInput(
            message=effective_message,
            session_id=request.session_id,
            display_message=request.message,
        )
    )
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
