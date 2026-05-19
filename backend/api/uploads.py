"""
File upload and text-extraction endpoints.

POST /api/uploads           — upload a file (PDF, DOCX, XLSX/XLS) for a session
GET  /api/uploads/{session_id} — list uploaded files for a session
DELETE /api/uploads/{session_id}/{file_id} — remove an uploaded file

Extracted text is stored at:
  backend/uploads/{session_id}/{file_id}.json
  {filename, file_type, extracted_text, char_count, uploaded_at}
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from time import time

from access_control import require_execution_access, require_inspection_access
from fastapi import APIRouter, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

router = APIRouter()

_MAX_FILE_BYTES = 20 * 1024 * 1024  # 20 MB hard limit
_ALLOWED_MIME_PREFIXES = (
    "application/pdf",
    "application/vnd.openxmlformats-officedocument",
    "application/vnd.ms-excel",
    "application/msword",
)
_ALLOWED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".xls", ".doc"}


def _uploads_dir() -> Path:
    from graph.agent import agent_manager
    assert agent_manager.base_dir is not None
    uploads = agent_manager.base_dir / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    return uploads


def _session_dir(session_id: str) -> Path:
    _validate_session_id_simple(session_id)
    d = _uploads_dir() / session_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _validate_session_id_simple(session_id: str) -> None:
    if not session_id or "/" in session_id or ".." in session_id or len(session_id) > 128:
        raise HTTPException(400, "Invalid session_id")


# ── Extraction helpers ──────────────────────────────────────────────────────


def _extract_pdf(data: bytes) -> str:
    from pypdf import PdfReader
    import io
    reader = PdfReader(io.BytesIO(data))
    parts: list[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        if text.strip():
            parts.append(text)
    return "\n\n".join(parts)


def _extract_docx(data: bytes) -> str:
    import io
    from docx import Document
    doc = Document(io.BytesIO(data))
    return "\n".join(para.text for para in doc.paragraphs if para.text.strip())


def _extract_excel(data: bytes) -> str:
    import io
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    parts: list[str] = []
    for sheet in wb.worksheets:
        rows: list[str] = []
        for row in sheet.iter_rows(values_only=True):
            cells = [str(c) if c is not None else "" for c in row]
            if any(c.strip() for c in cells):
                rows.append("\t".join(cells))
        if rows:
            parts.append(f"[Sheet: {sheet.title}]\n" + "\n".join(rows))
    wb.close()
    return "\n\n".join(parts)


def _extract_text(filename: str, data: bytes) -> tuple[str, str]:
    """Return (file_type, extracted_text). Raises HTTPException on unsupported type."""
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        return "pdf", _extract_pdf(data)
    if suffix in (".docx", ".doc"):
        return "docx", _extract_docx(data)
    if suffix in (".xlsx", ".xls"):
        return "excel", _extract_excel(data)
    raise HTTPException(415, f"Unsupported file type: {suffix!r}. Accepted: PDF, DOCX, XLSX.")


# ── Routes ──────────────────────────────────────────────────────────────────


@router.post("/uploads")
async def upload_file(
    http_request: Request,
    file: UploadFile,
    session_id: str = Form(...),
):
    require_execution_access(http_request)
    _validate_session_id_simple(session_id)

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in _ALLOWED_EXTENSIONS:
        raise HTTPException(415, f"Unsupported extension {suffix!r}. Accepted: PDF, DOCX, XLSX.")

    data = await file.read()
    if len(data) > _MAX_FILE_BYTES:
        raise HTTPException(413, f"File too large (max {_MAX_FILE_BYTES // (1024*1024)} MB).")
    if not data:
        raise HTTPException(400, "Uploaded file is empty.")

    try:
        file_type, extracted_text = _extract_text(file.filename or "upload", data)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(422, f"Could not parse file: {exc}") from exc

    file_id = str(uuid.uuid4())
    record = {
        "file_id": file_id,
        "filename": file.filename,
        "file_type": file_type,
        "extracted_text": extracted_text,
        "char_count": len(extracted_text),
        "uploaded_at": time(),
    }

    dest = _session_dir(session_id) / f"{file_id}.json"
    dest.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")

    return JSONResponse({
        "file_id": file_id,
        "filename": file.filename,
        "file_type": file_type,
        "char_count": len(extracted_text),
        "preview": extracted_text[:300].replace("\n", " "),
    })


@router.get("/uploads/{session_id}")
def list_uploads(session_id: str, http_request: Request = None):
    require_inspection_access(http_request)
    _validate_session_id_simple(session_id)

    try:
        d = _uploads_dir() / session_id
    except HTTPException:
        raise

    if not d.exists():
        return JSONResponse([])

    items = []
    for p in sorted(d.glob("*.json")):
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
            items.append({
                "file_id": rec["file_id"],
                "filename": rec["filename"],
                "file_type": rec["file_type"],
                "char_count": rec["char_count"],
                "uploaded_at": rec["uploaded_at"],
            })
        except Exception:
            continue
    return JSONResponse(items)


@router.delete("/uploads/{session_id}/{file_id}")
def delete_upload(session_id: str, file_id: str, http_request: Request = None):
    require_execution_access(http_request)
    _validate_session_id_simple(session_id)

    if not file_id or "/" in file_id or ".." in file_id or len(file_id) > 64:
        raise HTTPException(400, "Invalid file_id")

    p = _uploads_dir() / session_id / f"{file_id}.json"
    if not p.exists():
        raise HTTPException(404, "Upload not found")
    p.unlink()
    return JSONResponse({"deleted": file_id})


def load_file_texts(session_id: str, file_ids: list[str]) -> list[dict]:
    """Load stored upload records for given file_ids. Silently skips missing ones."""
    if not file_ids:
        return []
    results = []
    try:
        d = _uploads_dir() / session_id
    except Exception:
        return []
    for fid in file_ids:
        if not fid or "/" in fid or ".." in fid:
            continue
        p = d / f"{fid}.json"
        if not p.exists():
            continue
        try:
            results.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            continue
    return results
