import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, UploadFile

router = APIRouter()
logger = logging.getLogger(__name__)

_ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md", ".rst"}


@router.post("/v1/documents/upload")
async def upload_document(file: UploadFile, request: Request) -> dict:
    """파일 업로드 후 RAG 인덱스에 추가."""
    suffix = Path(file.filename).suffix.lower()
    if suffix not in _ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=415, detail=f"지원하지 않는 형식: {suffix}")

    indexer = request.app.state.indexer

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        count = indexer.index_file(tmp_path)
    except Exception as e:
        logger.error(f"[documents] 인덱싱 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    return {"filename": file.filename, "chunks_indexed": count}


@router.delete("/v1/documents/{source}")
async def delete_document(source: str, request: Request) -> dict:
    """소스 경로로 인덱스에서 문서 삭제."""
    indexer = request.app.state.indexer
    indexer.delete_source(source)
    return {"deleted": source}


@router.get("/v1/documents/stats")
async def document_stats(request: Request) -> dict:
    indexer = request.app.state.indexer
    return {"total_chunks": indexer.count}
