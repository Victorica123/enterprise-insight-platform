"""文档管理端点：上传、列表、删除。

写操作要求 operator/admin；viewer 只读。
"""
import logging
import os

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from app.auth import ActorPrincipal, current_principal, require_write_role
from app.document_parser import is_supported_file, parse_document
from app.models import DocumentSummary, DocumentUploadResponse
from app.rag import delete_document, ingest_document, list_documents


logger = logging.getLogger(__name__)

# 上传大小上限（字节）：防止单文件读满内存；测试可通过环境变量调小。
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(50 * 1024 * 1024)))

router = APIRouter(tags=["documents"])


@router.post("/documents", response_model=DocumentUploadResponse, summary="上传文档（.txt/.md/.pdf，≤50MB）",
             responses={403: {"description": "viewer 无写权限"}})
async def upload_document(
    file: UploadFile = File(...),
    principal: ActorPrincipal = Depends(current_principal),
) -> DocumentUploadResponse:
    require_write_role(principal.role)
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename.")

    filename = file.filename
    if not is_supported_file(filename):
        raise HTTPException(status_code=400, detail="Only .txt, .md and .pdf files are supported in V1.")

    raw = bytearray()
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        raw.extend(chunk)
        if len(raw) > MAX_UPLOAD_BYTES:
            limit_mb = MAX_UPLOAD_BYTES // (1024 * 1024)
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds the maximum upload size of {limit_mb} MB.",
            )

    try:
        response = await run_in_threadpool(
            process_uploaded_document,
            filename,
            bytes(raw),
            principal.tenant_id,
            principal.user_id,
            principal.auth_mode == "development",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    logger.info(
        "document_ingested filename=%s chunks=%d actor=%s",
        response.filename, response.chunk_count, principal.role,
    )
    return response


def process_uploaded_document(
    filename: str,
    raw: bytes,
    tenant_id: str = "legacy",
    owner_id: str = "legacy",
    index_graph: bool = True,
) -> DocumentUploadResponse:
    """Run parsing, embedding and graph extraction outside the event loop."""
    content = parse_document(filename=filename, raw=raw)
    if not content.strip():
        raise ValueError("No readable text was found in the file.")
    return ingest_document(
        filename=filename,
        content=content,
        tenant_id=tenant_id,
        owner_id=owner_id,
        index_graph=index_graph,
    )


@router.get("/documents", response_model=list[DocumentSummary], summary="文档列表")
def get_documents(principal: ActorPrincipal = Depends(current_principal)) -> list[DocumentSummary]:
    if principal.auth_mode == "development":
        return list_documents()
    return list_documents(tenant_id=principal.tenant_id, owner_id=principal.user_id)


@router.delete("/documents/{document_id}", summary="删除文档（级联删除 chunk 与图谱）",
             responses={403: {"description": "viewer 无写权限"}, 404: {"description": "文档不存在"}})
def remove_document(
    document_id: str,
    principal: ActorPrincipal = Depends(current_principal),
) -> dict[str, str]:
    require_write_role(principal.role)
    deleted = (
        delete_document(document_id)
        if principal.auth_mode == "development"
        else delete_document(
            document_id,
            tenant_id=principal.tenant_id,
            owner_id=principal.user_id,
            rebuild_graph=False,
        )
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found.")
    logger.info("document_deleted document_id=%s actor=%s", document_id, principal.user_id)
    return {"status": "deleted", "document_id": document_id}
