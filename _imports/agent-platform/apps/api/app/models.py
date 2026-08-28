from pydantic import BaseModel, Field
from typing import Literal


AnswerMode = Literal["auto", "local", "api"]
RetrieverMode = Literal["keyword", "embedding", "hybrid"]
WorkflowMode = Literal["standard", "agentic"]
ActorRole = Literal["viewer", "operator", "admin"]
TicketStatus = Literal["open", "in_progress", "resolved", "closed"]
TicketPriority = Literal["low", "medium", "high", "critical"]


class DocumentUploadResponse(BaseModel):
    document_id: str
    filename: str
    chunk_count: int


class DocumentSummary(BaseModel):
    document_id: str
    filename: str
    chunk_count: int
    created_at: str


class EmbeddingStatus(BaseModel):
    total_chunks: int
    embedded_chunks: int
    missing_chunks: int
    coverage: float
    # A3: 真实语义 embedding（BGE）覆盖情况；0 表示模型不可用，检索走哈希回退
    embedded_chunks_v2: int = 0
    missing_chunks_v2: int = 0


class EmbeddingRebuildResponse(EmbeddingStatus):
    updated_chunks: int


class SystemStatus(BaseModel):
    status: str
    document_count: int
    chunk_count: int
    llm_provider: str
    llm_configured: bool
    default_answer_mode: str
    default_retriever_mode: str
    embedding: EmbeddingStatus


class ToolCallRecord(BaseModel):
    tool_name: str
    success: bool
    result_summary: str
    pending_action_id: str = ""
    status: str = "succeeded"
    duration_ms: float = 0.0


class TokenUsage(BaseModel):
    """V5: 单次回答的 token 规模与成本估算。local 模式按字符估算、成本记 0。"""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    source: str = "local"


class AgentSummary(BaseModel):
    workflow: str
    intent: str
    complexity: str
    retrieval_rounds: int
    queries: list[str]
    evidence_status: str
    citation_status: str
    agents: list[str]
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    pending_approval: bool = False
    graph_entities: list[str] = Field(default_factory=list)
    graph_paths: list[str] = Field(default_factory=list)


class ChatMetricsSummary(BaseModel):
    total_requests: int
    answered_requests: int
    refused_requests: int
    error_requests: int
    answer_rate: float
    refusal_rate: float
    error_rate: float
    evidence_pass_rate: float
    citation_ready_rate: float
    avg_latency_ms: float
    p95_latency_ms: float
    avg_retrieval_rounds: float
    avg_query_count: float
    avg_source_count: float
    workflow_usage: dict[str, int]
    answer_mode_usage: dict[str, int]
    retriever_usage: dict[str, int]
    intent_usage: dict[str, int]
    avg_latency_by_workflow: dict[str, float]
    avg_latency_by_answer_mode: dict[str, float]
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    avg_tokens_per_request: float = 0.0
    total_estimated_cost_usd: float = 0.0
    avg_cost_per_request_usd: float = 0.0
    tokens_by_answer_mode: dict[str, int] = Field(default_factory=dict)
    cost_by_answer_mode: dict[str, float] = Field(default_factory=dict)
    feedback_count: int = 0
    positive_feedback: int = 0
    negative_feedback: int = 0
    satisfaction_rate: float = 1.0


class ChatRequest(BaseModel):
    question: str = Field(min_length=1)
    answer_mode: AnswerMode = Field(
        default="auto",
        description="回答模式：local=内部 RAG，api=调用模型 API，auto=自动选择。",
    )
    retriever_mode: RetrieverMode = Field(
        default="keyword",
        description="检索模式：keyword=关键词检索，embedding=本地向量检索，hybrid=混合检索。",
    )
    workflow_mode: WorkflowMode = Field(
        default="agentic",
        description="工作流模式：standard=单轮 RAG，agentic=分类、改写、多轮检索和引用审核。",
    )


class Source(BaseModel):
    document_id: str
    filename: str
    chunk_index: int
    score: int
    content: str
    title: str = ""  # A4: 块标题，帮助模型理解来源上下文


class TraceStep(BaseModel):
    name: str
    status: str
    detail: str


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]
    trace: list[TraceStep] = Field(default_factory=list)
    agent_summary: AgentSummary | None = None
    pending_actions: list["PendingActionResponse"] = Field(default_factory=list)
    token_usage: TokenUsage | None = None
    log_id: int = 0


# ---------------------------------------------------------------------------
# V3 工单与工具调用模型
# ---------------------------------------------------------------------------

class TicketResponse(BaseModel):
    ticket_id: str
    title: str
    description: str
    status: str
    priority: str
    assignee: str
    source_document_ids: list[str] = Field(default_factory=list)
    risk_level: str = ""
    created_at: str = ""
    updated_at: str = ""


class TicketListResponse(BaseModel):
    tickets: list[TicketResponse]
    total: int
    summary: dict = Field(default_factory=dict)


class TicketCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=3000)
    priority: TicketPriority = "medium"
    assignee: str = Field(default="", max_length=80)
    risk_level: str = Field(default="", max_length=20)
    source_document_ids: list[str] = Field(default_factory=list, max_length=20)


class TicketStatusDraftRequest(BaseModel):
    new_status: TicketStatus
    assignee: str = Field(default="", max_length=80)


class PendingActionResponse(BaseModel):
    action_id: str
    action_type: str
    payload: dict
    status: str
    requested_by: str = "operator"
    requested_by_user: str = "anonymous"
    resolved_by: str = ""
    result: dict = Field(default_factory=dict)
    error_message: str = ""
    duration_ms: float = 0.0
    execution_count: int = 0
    created_at: str = ""
    expires_at: str = ""
    resolved_at: str = ""


class ApprovalRequest(BaseModel):
    approved: bool = Field(description="是否批准该操作")
    action_id: str = Field(default="", description="兼容旧前端；实际 ID 取 URL 路径。")


class ApprovalResponse(BaseModel):
    action_id: str
    status: str
    result: dict = Field(default_factory=dict)
    message: str = ""
    already_resolved: bool = False


class ToolCallLogResponse(BaseModel):
    call_id: str
    tool_name: str
    action_id: str
    operation: str
    requires_approval: bool
    status: str
    actor_role: str
    input: dict = Field(default_factory=dict)
    result: dict = Field(default_factory=dict)
    error_message: str = ""
    duration_ms: float = 0.0
    created_at: str = ""


class ToolMetricsSummary(BaseModel):
    total_calls: int
    succeeded_calls: int
    pending_calls: int
    failed_calls: int
    rejected_calls: int
    expired_calls: int
    success_rate: float
    approval_rate: float
    avg_duration_ms: float
    p95_duration_ms: float
    exact_once_violations: int
    by_tool: dict[str, int]
    by_status: dict[str, int]


# ---------------------------------------------------------------------------
# V4 关系图谱模型
# ---------------------------------------------------------------------------

class GraphEntityResponse(BaseModel):
    name: str
    entity_type: str
    type_label: str
    mention_count: int
    document_ids: list[str] = Field(default_factory=list)


class GraphRelationResponse(BaseModel):
    source_name: str
    source_type: str
    relation_type: str
    target_name: str
    target_type: str
    evidence: str = ""
    document_id: str = ""
    filename: str = ""
    chunk_index: int = 0


class GraphOverviewResponse(BaseModel):
    entity_count: int
    relation_count: int
    document_count: int
    entity_types: dict[str, int] = Field(default_factory=dict)
    relation_types: dict[str, int] = Field(default_factory=dict)
    built_at: str = ""


class GraphRebuildResponse(GraphOverviewResponse):
    duration_ms: float = 0.0


class GraphPathStepResponse(BaseModel):
    source: str
    relation: str
    target: str
    forward: bool = True
    display: str = ""


class GraphPathResponse(BaseModel):
    steps: list[GraphPathStepResponse]
    display: str


class GraphPathQueryResponse(BaseModel):
    source: str
    target: str
    max_depth: int
    paths: list[GraphPathResponse] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# V5 请求日志 / 反馈模型
# ---------------------------------------------------------------------------

class ChatLogResponse(BaseModel):
    log_id: int
    question: str
    workflow_mode: str
    answer_mode: str
    retriever_mode: str
    intent: str
    outcome: str
    evidence_status: str
    citation_status: str
    source_count: int
    latency_ms: float
    total_tokens: int
    estimated_cost_usd: float
    answer_preview: str
    feedback: int = 0
    feedback_note: str = ""
    created_at: str = ""


class ChatLogDetailResponse(ChatLogResponse):
    trace: list[TraceStep] = Field(default_factory=list)


class FeedbackRequest(BaseModel):
    rating: Literal["up", "down"]
    note: str = Field(default="", max_length=500)


class FeedbackResponse(BaseModel):
    log_id: int
    feedback: int
    feedback_note: str = ""
