"""应用装配：CORS、lifespan 初始化、路由注册。

业务端点在 app.routes.* 中，按领域拆分；重量级初始化（建库、建表、
模型预热）在 lifespan 中执行，import 本模块不再产生副作用。
"""

import asyncio
import logging
import time
from contextlib import asynccontextmanager

import anyio.to_thread
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__, database
from app.analysis_store import init_analysis_store
from app.auth import validate_auth_configuration
from app.config import (
    get_default_answer_mode,
    get_llm_settings,
    get_retriever_mode,
    get_settings,
    load_local_env,
)
from app.conversation_store import init_conversation_store
from app.database import get_embedding_stats, init_db
from app.embedding_maintenance import embedding_backfill_loop
from app.embeddings import warm_up_embeddings
from app.graph_store import init_graph_store
from app.llm import is_llm_configured
from app.llm_client import close_async_llm_clients
from app.logging_config import setup_logging
from app.models import SystemStatus
from app.publication_artifacts import init_publication_artifact_store
from app.rag import list_documents
from app.retention import (
    retention_enabled,
    retention_loop,
    stop_retention_task,
    validate_retention_configuration,
)
from app.routes.analysis import router as analysis_router
from app.routes.chat import router as chat_router
from app.routes.documents import router as documents_router
from app.routes.embedding_admin import router as embedding_router
from app.routes.graph import router as graph_router
from app.routes.internal_media import router as internal_media_router
from app.routes.observability import router as observability_router
from app.routes.tickets import router as tickets_router
from app.status_service import build_embedding_coverage
from app.tools import init_tools

logger = logging.getLogger(__name__)

_STATE: dict[str, float | None] = {"started_at": None}

load_local_env()
setup_logging()


@asynccontextmanager
async def lifespan(_: FastAPI):
    get_settings().validate()
    anyio.to_thread.current_default_thread_limiter().total_tokens = get_settings().thread_pool_size
    validate_auth_configuration()
    validate_retention_configuration()
    init_db()
    init_tools()
    init_graph_store()
    init_analysis_store()
    init_publication_artifact_store()
    init_conversation_store()
    # A3: 启动时预加载真实 embedding 模型（不可用时为空操作），
    # 避免第一个 /chat 请求承担秒级模型加载延迟。
    warm_up_embeddings()
    _STATE["started_at"] = time.monotonic()
    logger.info("api_started")
    retention_task = asyncio.create_task(retention_loop()) if retention_enabled() else None
    embedding_task = asyncio.create_task(embedding_backfill_loop())
    try:
        yield
    finally:
        await stop_retention_task(retention_task)
        await stop_retention_task(embedding_task)
        await close_async_llm_clients()


TAG_METADATA = [
    {
        "name": "chat",
        "description": "问答：standard / agentic 两种工作流，返回回答、来源证据、执行轨迹与 token 成本。",
    },
    {
        "name": "documents",
        "description": "知识库文档管理：上传（.txt/.md/.pdf）、列表、删除。写操作需 operator+。",
    },
    {"name": "tickets", "description": "工单管理与状态草稿；写操作需 operator+。"},
    {
        "name": "observability",
        "description": "指标、请求日志与回放、工具调用审计、用户反馈。审计数据需 operator+。",
    },
    {
        "name": "graph",
        "description": "关系图谱：概览、实体、关系、关系链查询与重建。重建需 operator+。",
    },
    {
        "name": "embeddings",
        "description": "Embedding 覆盖率、进程缓存指标与全量重建。状态需登录，重建需 operator+。",
    },
    {
        "name": "internal-media",
        "description": "Media Service 专用的版本化证据摄取接口。",
    },
    {
        "name": "analysis",
        "description": "六阶段证据分析、人工补充、PRD 发布审批与审计。",
    },
]

app = FastAPI(
    title="Enterprise Insight Platform Agent API",
    description=(
        "企业智能工单与知识助手平台 API。\n\n"
        "**鉴权**：生产环境只接受统一平台签发的 Bearer JWT，JWT 携带 tenant、用户和角色；"
        "开发模式可显式启用兼容身份头。写操作与审计数据端点要求 operator+。\n\n"
        "零配置即可运行：不配置 LLM Key 时使用本地模板回答模式。"
    ),
    version=__version__,
    lifespan=lifespan,
    openapi_tags=TAG_METADATA,
    license_info={"name": "MIT", "url": "https://opensource.org/licenses/MIT"},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


for feature_router in (
    documents_router,
    chat_router,
    embedding_router,
    observability_router,
    graph_router,
    tickets_router,
    internal_media_router,
    analysis_router,
):
    app.include_router(feature_router)


# ---------------------------------------------------------------------------
# 健康检查 & 系统状态
# ---------------------------------------------------------------------------


@app.get("/health", summary="健康检查", tags=["health"])
def health() -> dict[str, object]:
    started_at = _STATE["started_at"]
    return {
        "status": "ok",
        "version": __version__,
        "uptime_seconds": round(time.monotonic() - started_at, 1)
        if started_at
        else 0.0,
    }


@app.get(
    "/system/status",
    response_model=SystemStatus,
    summary="系统状态（文档/Chunk/LLM/Embedding）",
)
def get_system_status() -> SystemStatus:
    documents = list_documents()
    embedding = build_embedding_coverage(get_embedding_stats())
    llm_settings = get_llm_settings()
    return SystemStatus(
        status="ok",
        document_count=len(documents),
        chunk_count=embedding.total_chunks,
        llm_provider=llm_settings.provider,
        llm_configured=is_llm_configured(),
        default_answer_mode=get_default_answer_mode(),
        default_retriever_mode=get_retriever_mode(),
        embedding=embedding,
        database_backend="mysql" if database.uses_mysql() else "sqlite",
        jwt_algorithm=get_settings().jwt_algorithm,
        model_egress_policy=get_settings().model_egress_policy,
        model_egress_allowlist_configured=bool(get_settings().model_egress_allowed_tenants),
        retention_enabled=retention_enabled(),
        transcript_retention_days=get_settings().retention_transcript_days,
        audit_retention_days=get_settings().retention_audit_days,
    )
