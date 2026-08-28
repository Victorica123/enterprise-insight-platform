from dataclasses import dataclass, field
import logging

from app.config import get_llm_pricing
from app.graph_rag import lookup_graph
from app.agent_planning import (
    build_intent_queries,
    build_retry_queries,
    detect_intents,
    is_complex_question,
    rewrite_question,
    split_complex_question,
)
from app.citation_review import review_citations
from app.llm_router import (
    llm_plan_queries,
    llm_route_question,
    llm_select_tool_calls,
)
from app.models import (
    AgentSummary,
    ChatResponse,
    PendingActionResponse,
    Source,
    TokenUsage,
    ToolCallRecord,
    TraceStep,
)
from app.rag import (
    EvidenceCheck,
    MAX_SOURCES,
    build_answer,
    build_insufficient_evidence_answer,
    build_local_usage,
    check_evidence,
    deduplicate_preserve_order,
    expand_queries,
    title_term_boost,
)
from app.retrievers import RetrievalHit, get_retriever
from app.slot_extraction import (
    extract_assignee,
    extract_priority,
    extract_risk_level,
    extract_target_status,
    extract_ticket_description,
    extract_ticket_id,
    extract_ticket_title,
)
from app.ticket_store import get_pending_action
from app.tools import (
    ToolCallResult,
    execute_tool,
    get_tool,
    init_tools,
)


logger = logging.getLogger(__name__)

MAX_RETRIEVAL_ROUNDS = 2


@dataclass
class AgenticRagState:
    question: str
    answer_mode: str
    retriever_mode: str
    actor_role: str = "operator"
    actor_user: str = "anonymous"
    intent: str = "general"
    complexity: str = "simple"
    queries: list[str] = field(default_factory=list)
    retrieval_rounds: int = 0
    hits: dict[tuple[str, int], RetrievalHit] = field(default_factory=dict)
    sources: list[Source] = field(default_factory=list)
    evidence_status: str = "pending"
    citation_status: str = "pending"
    agents: list[str] = field(default_factory=list)
    trace: list[TraceStep] = field(default_factory=list)
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    pending_actions: list[PendingActionResponse] = field(default_factory=list)
    tool_context: str = ""
    graph_entities: list[str] = field(default_factory=list)
    graph_paths: list[str] = field(default_factory=list)
    graph_context: str = ""
    token_usage: TokenUsage | None = None
    # B1/B2: LLM 路由/规划/工具选择的真实 token 用量（并入成本核算）
    router_prompt_tokens: int = 0
    router_completion_tokens: int = 0


def answer_agentic_question(
    question: str,
    answer_mode: str = "auto",
    retriever_mode: str = "hybrid",
    actor_role: str = "operator",
    actor_user: str = "anonymous",
) -> ChatResponse:
    init_tools()

    state = AgenticRagState(
        question=question,
        answer_mode=answer_mode,
        retriever_mode=retriever_mode,
        actor_role=actor_role,
        actor_user=actor_user,
        trace=[
            TraceStep(
                name="question_received",
                status="ok",
                detail=f"收到问题，进入 Agentic RAG；回答模式 {answer_mode}，检索模式 {retriever_mode}。",
            )
        ],
    )

    route_question(state)
    if _is_tool_only_question(state.question):
        state.evidence_status = "not_required"
        state.agents.append("Planner Agent")
        state.trace.append(
            TraceStep(
                name="retrieval_plan",
                status="skipped",
                detail="这是直接工单操作，不依赖知识库证据，跳过检索以降低延迟和 token 消耗。",
            )
        )
    else:
        plan_retrieval(state)
        retrieve_until_sufficient(state)
        # V4: Graph Agent - 查询关系图谱补充关系链上下文
        run_graph_agent(state)

    # V3: Tool Agent - 执行工具调用
    run_tool_agent(state)

    if state.evidence_status == "not_required":
        answer = build_tool_only_answer(state)
        state.token_usage = build_local_usage(state.question, [], answer, "local_template")
        state.citation_status = "not_applicable"
        state.agents.extend(["Answer Agent", "Reviewer Agent"])
        state.trace.append(
            TraceStep(
                name="citation_check",
                status="not_applicable",
                detail="直接工具操作没有使用知识库证据，因此不需要来源引用。",
            )
        )
        return build_response(state, answer)

    if state.evidence_status != "passed":
        detail = state.trace[-1].detail if state.trace else "证据不足。"
        answer = (
            build_insufficient_evidence_answer(check_evidence(question, state.sources))
            if state.sources
            else "我经过多轮检索后，仍然没有找到足够相关的资料，因此暂时不能可靠回答这个问题。"
        )
        state.trace.append(
            TraceStep(
                name="reviewer",
                status="refused",
                detail=f"Reviewer Agent 拒绝生成答案：{detail}",
            )
        )
        state.citation_status = "not_applicable"
        state.agents.append("Reviewer Agent")
        return build_response(state, answer)

    # 将工具调用与图谱结果注入上下文（直接下钻到 build_answer，
    # extra_contexts 在 API 模式进入 prompt，local 模式追加到答案末尾）
    answer, answer_trace, token_usage = build_answer(
        question, state.sources, answer_mode, [state.tool_context, state.graph_context]
    )
    state.token_usage = token_usage
    state.trace.extend(answer_trace)
    state.agents.append("Answer Agent")

    reviewed_answer, citation_status, citation_detail = review_citations(answer, state.sources)
    state.citation_status = citation_status
    state.agents.append("Reviewer Agent")
    state.trace.append(
        TraceStep(
            name="citation_check",
            status=citation_status,
            detail=citation_detail,
        )
    )
    return build_response(state, reviewed_answer)


# ---------------------------------------------------------------------------
# V4: Graph Agent
# ---------------------------------------------------------------------------

def run_graph_agent(state: AgenticRagState) -> None:
    """Graph Agent：识别问题实体，取子图并生成关系链上下文。"""
    lookup = lookup_graph(state.question, state.intent)
    if not lookup.matched_entities:
        return

    state.agents.append("Graph Agent")
    state.graph_entities = lookup.matched_entities
    if not lookup.hit:
        state.trace.append(
            TraceStep(
                name="graph_lookup",
                status="no_match",
                detail=f"Graph Agent 命中实体 {'、'.join(lookup.matched_entities)}，但图谱中暂无关联关系。",
            )
        )
        return

    state.graph_paths = lookup.paths
    state.graph_context = lookup.context
    risk_note = f"，其中风险链路 {len(lookup.risk_chains)} 条" if lookup.risk_chains else ""
    state.trace.append(
        TraceStep(
            name="graph_lookup",
            status="ok",
            detail=(
                f"Graph Agent 命中实体 {'、'.join(lookup.matched_entities)}，"
                f"取到 {len(lookup.relations)} 条关系{risk_note}。"
            ),
        )
    )


# ---------------------------------------------------------------------------
# V3: Tool Agent
# ---------------------------------------------------------------------------

_TOOL_KEYWORDS = [
    "工单", "创建工单", "查工单", "查询工单", "更新工单",
    "跟进", "指派", "分配", "处理状态", "工单状态",
    "ticket", "create ticket", "query ticket",
    "要不要创建", "帮我创建", "生成工单", "建一个工单",
]


def _question_needs_tools(question: str) -> bool:
    lowered = question.lower()
    return any(kw.lower() in lowered for kw in _TOOL_KEYWORDS)


def _is_tool_only_question(question: str) -> bool:
    """Direct ticket operations can bypass RAG; knowledge-backed creation cannot."""
    query_or_update = any(
        keyword in question
        for keyword in ["查工单", "查询工单", "工单列表", "有哪些工单", "更新工单", "修改状态", "关闭工单", "解决工单"]
    )
    if query_or_update:
        return True
    create_requested = any(
        keyword in question for keyword in ["创建工单", "生成工单", "帮我创建", "建一个工单"]
    )
    needs_knowledge = any(
        keyword in question for keyword in ["为什么", "原因", "风险", "根据", "资料", "延期", "负责人"]
    )
    return create_requested and not needs_knowledge


def run_tool_agent(state: AgenticRagState) -> None:
    """Tool Agent：B2 LLM 工具选择优先（原生 function-calling 风格），关键词规则降级。"""
    # B2: LLM 决策路径——模型按工具 JSON Schema 决定调用哪些工具与参数
    llm_result = llm_select_tool_calls(state.question)
    if llm_result is not None:
        state.router_prompt_tokens += llm_result.prompt_tokens
        state.router_completion_tokens += llm_result.completion_tokens
        # 白名单过滤：LLM 幻觉出的未注册工具名不进入执行，记日志后丢弃
        valid_calls = [(name, args) for name, args in llm_result.data if get_tool(name) is not None]
        unknown_tools = [name for name, _ in llm_result.data if get_tool(name) is None]
        if unknown_tools:
            logger.warning("llm_tool_selection_filtered unknown_tools=%s", unknown_tools)
            state.trace.append(
                TraceStep(
                    name="tool_call",
                    status="filtered",
                    detail=f"Tool Agent 过滤掉 LLM 选择的未注册工具：{'、'.join(unknown_tools)}。",
                )
            )
        if valid_calls:
            state.agents.append("Tool Agent")
            tool_results = [
                execute_tool(name, arguments, actor_role=state.actor_role, actor_user=state.actor_user)
                for name, arguments in valid_calls
            ]
            _record_tool_results(state, tool_results, source="LLM 工具选择")
            return
        # LLM 明确返回空列表 = 不需要工具；全是幻觉工具名则降级走关键词规则
        if not llm_result.data:
            return

    # 规则降级路径：关键词触发（原有逻辑不变）
    if not _question_needs_tools(state.question):
        return

    state.agents.append("Tool Agent")
    tool_results: list[ToolCallResult] = []

    create_requested = any(
        kw in state.question for kw in ["创建工单", "生成工单", "帮我创建", "建一个工单", "要不要创建"]
    )
    update_requested = any(
        kw in state.question for kw in ["更新工单", "修改状态", "关闭工单", "解决工单"]
    )
    query_requested = any(
        kw in state.question for kw in ["查工单", "查询工单", "工单状态", "工单列表", "有哪些工单"]
    ) and not update_requested

    # 查询工单场景
    if query_requested:
        kwargs = {}
        for status_kw in ["open", "in_progress", "resolved", "closed"]:
            if status_kw in state.question.lower():
                kwargs["status"] = status_kw
                break
        for priority_kw in ["low", "medium", "high", "critical"]:
            if priority_kw in state.question.lower():
                kwargs["priority"] = priority_kw
                break
        tool_results.append(execute_tool("query_tickets", kwargs, actor_role=state.actor_role))

    # 创建工单场景
    if create_requested and state.evidence_status in {"passed", "not_required"}:
        result = execute_tool(
            "create_ticket",
            {
                "title": extract_ticket_title(state.question, state.sources),
                "description": extract_ticket_description(state.question, state.sources),
                "priority": extract_priority(state.question, state.sources),
                "assignee": extract_assignee(state.question, state.sources),
                "risk_level": extract_risk_level(state.question, state.sources),
                "source_document_ids": deduplicate_preserve_order([s.document_id for s in state.sources]),
            },
            actor_role=state.actor_role,
            actor_user=state.actor_user,
        )
        tool_results.append(result)

    # 更新工单状态场景
    if update_requested:
        ticket_id = extract_ticket_id(state.question)
        target_status = extract_target_status(state.question)
        if ticket_id and target_status:
            tool_results.append(
                execute_tool(
                    "update_ticket_status",
                    {"ticket_id": ticket_id, "new_status": target_status},
                    actor_role=state.actor_role,
                    actor_user=state.actor_user,
                )
            )
        elif not ticket_id:
            tool_results.append(
                ToolCallResult(
                    "update_ticket_status",
                    False,
                    {"error": "没有识别到完整工单 ID。"},
                    "failed",
                    0.0,
                )
            )
        else:
            # 目标状态模糊时不草拟（旧版会静默默认 resolved）
            tool_results.append(
                ToolCallResult(
                    "update_ticket_status",
                    False,
                    {"error": "未识别到明确的目标状态，请说明要变更为 open/in_progress/resolved/closed 中的哪一个。"},
                    "failed",
                    0.0,
                )
            )

    _record_tool_results(state, tool_results, source="关键词规则")


def _record_tool_results(state: AgenticRagState, tool_results: list[ToolCallResult], *, source: str) -> None:
    """工具调用结果的统一记账：待审批动作、调用记录、上下文与 trace。"""
    for result in tool_results:
        if not result.pending_action_id:
            continue
        pending = get_pending_action(result.pending_action_id)
        if pending is not None:
            state.pending_actions.append(PendingActionResponse(**pending.to_dict()))

    # 记录工具调用
    for tr in tool_results:
        state.tool_calls.append(ToolCallRecord(
            tool_name=tr.tool_name,
            success=tr.success,
            result_summary=_summarize_tool_result(tr.result),
            pending_action_id=tr.pending_action_id,
            status=tr.status,
            duration_ms=tr.duration_ms,
        ))

    # 生成工具上下文供 Answer Agent 使用
    if tool_results:
        state.tool_context = _build_tool_context(tool_results, state.pending_actions)
        state.trace.append(
            TraceStep(
                name="tool_call",
                status="ok",
                detail=(
                    f"Tool Agent（{source}）执行 {len(tool_results)} 个工具调用："
                    f"{' / '.join(f'{tr.tool_name}({tr.status})' for tr in tool_results)}"
                ),
            )
        )


def build_tool_only_answer(state: AgenticRagState) -> str:
    if not state.tool_calls:
        return "没有识别到可执行的工单操作，请补充工单 ID 或明确要查询、创建还是更新。"
    failed = [call for call in state.tool_calls if not call.success]
    prefix = "工具操作未完成。" if failed else "工具操作已处理。"
    return f"{prefix}\n\n{state.tool_context}"


# ---------------------------------------------------------------------------
# 工具调用的辅助函数
# ---------------------------------------------------------------------------

def _summarize_tool_result(result: dict) -> str:
    """生成工具调用结果摘要。"""
    if "count" in result:
        return f"查询到 {result['count']} 个工单"
    if result.get("action") == "create_ticket":
        draft = result.get("draft", {})
        return f"生成工单草稿：{draft.get('title', '')[:50]}"
    if result.get("action") == "update_ticket_status":
        draft = result.get("draft", {})
        return f"生成状态更新草稿：{draft.get('current_status', '')} → {draft.get('new_status', '')}"
    if "error" in result:
        return f"错误：{result['error']}"
    return "工具调用完成"


def _build_tool_context(tool_results: list[ToolCallResult], pending_actions: list[PendingActionResponse]) -> str:
    """为 Answer Agent 构建工具调用上下文。"""
    parts = ["【工具调用结果】"]

    for tr in tool_results:
        parts.append(f"\n工具：{tr.tool_name}")
        if tr.result.get("count") is not None:
            parts.append(f"查询结果：共 {tr.result['count']} 条记录")
            for ticket in tr.result.get("tickets", [])[:5]:
                parts.append(f"  - [{ticket['status']}] {ticket['title']} (优先级: {ticket['priority']})")
        elif tr.result.get("action") in ("create_ticket", "update_ticket_status"):
            parts.append(f"状态：已生成草稿，等待人工确认")
            parts.append(f"消息：{tr.result.get('message', '')}")
        elif "error" in tr.result:
            parts.append(f"错误：{tr.result['error']}")

    if pending_actions:
        parts.append("\n【待审批操作】")
        for pa in pending_actions:
            parts.append(f"  - [{pa.action_type}] {pa.action_id[:8]} (状态: {pa.status})")

    return "\n".join(parts)


def route_question(state: AgenticRagState) -> None:
    """B1: LLM 路由优先，规则版为降级通道（无 Key/失败时自动回退）。"""
    decision = llm_route_question(state.question)
    if decision is not None:
        state.intent = decision.intent
        state.complexity = decision.complexity
        state.router_prompt_tokens += decision.prompt_tokens
        state.router_completion_tokens += decision.completion_tokens
        router_source = "LLM 路由"
    else:
        intents = detect_intents(state.question)
        state.intent = intents[0] if intents else "general"
        state.complexity = "complex" if is_complex_question(state.question, intents) else "simple"
        router_source = "规则路由"
    state.agents.append("Router Agent")
    state.trace.append(
        TraceStep(
            name="question_classification",
            status="ok",
            detail=f"Router Agent（{router_source}）判断问题类型为 {state.intent}，复杂度为 {state.complexity}。",
        )
    )


def plan_retrieval(state: AgenticRagState) -> None:
    """B1: LLM 检索规划优先（覆盖同义表述，如"质量门槛"->"验收标准"），规则版降级。"""
    llm_result = llm_plan_queries(state.question, state.intent)
    if llm_result is not None:
        llm_queries = [str(q) for q in llm_result.data]
        state.router_prompt_tokens += llm_result.prompt_tokens
        state.router_completion_tokens += llm_result.completion_tokens
        queries = [state.question] + llm_queries
        queries.extend(build_intent_queries(state.intent))
        if state.complexity == "complex":
            queries.extend(split_complex_question(state.question))
        planner_source = "LLM 规划"
    else:
        rewritten = rewrite_question(state.question)
        queries = [state.question, rewritten]
        queries.extend(expand_queries(state.question))
        queries.extend(build_intent_queries(state.intent))
        if state.complexity == "complex":
            queries.extend(split_complex_question(state.question))
        planner_source = "规则规划"

    state.queries = deduplicate_preserve_order(queries)[:8]
    state.agents.append("Planner Agent")
    state.trace.append(
        TraceStep(
            name="query_planning",
            status="ok",
            detail=f"Planner Agent（{planner_source}）生成 {len(state.queries)} 个 query：{' / '.join(state.queries)}",
        )
    )


def retrieve_until_sufficient(state: AgenticRagState) -> None:
    retriever = get_retriever(state.retriever_mode)
    round_queries = state.queries

    for round_index in range(1, MAX_RETRIEVAL_ROUNDS + 1):
        state.retrieval_rounds = round_index
        state.agents.append("Retriever Agent")
        result = retriever.search(round_queries)
        merge_hits(state.hits, result.hits)
        state.sources = hits_to_sources(state.hits, state.question)
        useful_count = sum(1 for hit in result.hits if hit.score > 0)
        top_score = state.sources[0].score if state.sources else 0
        state.trace.append(
            TraceStep(
                name=f"retrieve_round_{round_index}",
                status="ok" if useful_count else "no_match",
                detail=f"第 {round_index} 轮检索：扫描 {result.scanned_count} 个 chunk，命中 {useful_count} 个，最高分 {top_score}。",
            )
        )

        check = check_evidence(state.question, state.sources)
        state.trace.append(
            TraceStep(
                name=f"evidence_check_{round_index}",
                status=check.status,
                detail=check.detail,
            )
        )

        if check.passed:
            state.evidence_status = "passed"
            return

        if round_index < MAX_RETRIEVAL_ROUNDS and state.complexity == "complex":
            round_queries = build_retry_queries(state.question, state.intent)
            state.trace.append(
                TraceStep(
                    name="retry_planning",
                    status="ok",
                    detail=f"Evidence Agent 决定重查，重试 query：{' / '.join(round_queries)}",
                )
            )
            state.agents.append("Evidence Agent")
        else:
            state.evidence_status = check.status


def merge_hits(target: dict[tuple[str, int], RetrievalHit], hits: list[RetrievalHit]) -> None:
    for hit in hits:
        if hit.score <= 0:
            continue
        key = (hit.chunk.document_id, hit.chunk.chunk_index)
        existing = target.get(key)
        if existing is None or hit.score > existing.score:
            target[key] = hit
        elif existing:
            existing.matched_queries = deduplicate_preserve_order(existing.matched_queries + hit.matched_queries)


def hits_to_sources(
    hits: dict[tuple[str, int], RetrievalHit],
    question: str = "",
) -> list[Source]:
    ranked = sorted(
        hits.values(),
        key=lambda item: item.score + title_term_boost(question, item.chunk.title),
        reverse=True,
    )[:MAX_SOURCES]
    return [
        Source(
            document_id=hit.chunk.document_id,
            filename=hit.chunk.filename,
            chunk_index=hit.chunk.chunk_index,
            score=hit.score,
            content=hit.chunk.content,
            title=hit.chunk.title,
        )
        for hit in ranked
    ]


def build_response(state: AgenticRagState, answer: str) -> ChatResponse:
    summary = AgentSummary(
        workflow="agentic",
        intent=state.intent,
        complexity=state.complexity,
        retrieval_rounds=state.retrieval_rounds,
        queries=state.queries,
        evidence_status=state.evidence_status,
        citation_status=state.citation_status,
        agents=deduplicate_preserve_order(state.agents),
        tool_calls=state.tool_calls,
        pending_approval=len(state.pending_actions) > 0,
        graph_entities=state.graph_entities,
        graph_paths=state.graph_paths,
    )
    # B1/B2: LLM 路由/规划/工具选择的真实 token 并入成本核算
    token_usage = state.token_usage
    if state.router_prompt_tokens or state.router_completion_tokens:
        router_cost = get_llm_pricing().estimate_cost(
            state.router_prompt_tokens, state.router_completion_tokens
        )
        if token_usage is None:
            token_usage = TokenUsage(
                prompt_tokens=state.router_prompt_tokens,
                completion_tokens=state.router_completion_tokens,
                total_tokens=state.router_prompt_tokens + state.router_completion_tokens,
                estimated_cost_usd=router_cost,
                source="router",
            )
        else:
            token_usage = TokenUsage(
                prompt_tokens=token_usage.prompt_tokens + state.router_prompt_tokens,
                completion_tokens=token_usage.completion_tokens + state.router_completion_tokens,
                total_tokens=token_usage.total_tokens + state.router_prompt_tokens + state.router_completion_tokens,
                estimated_cost_usd=token_usage.estimated_cost_usd + router_cost,
                source=token_usage.source,
            )
    return ChatResponse(
        answer=answer,
        sources=state.sources,
        trace=state.trace,
        agent_summary=summary,
        pending_actions=state.pending_actions,
        token_usage=token_usage,
    )
