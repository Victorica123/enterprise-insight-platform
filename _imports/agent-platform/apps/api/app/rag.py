from dataclasses import dataclass
import logging
import math
import re
from uuid import uuid4

from app.config import get_llm_pricing
from app.database import connect, init_db, insert_document, list_document_rows
from app.graph_store import delete_document_and_rebuild, index_document_graph, init_graph_store
from app.models import ChatResponse, DocumentSummary, DocumentUploadResponse, Source, TokenUsage, TraceStep
from app.llm import generate_answer, is_llm_configured
from app.local_answer import build_fallback_answer, extract_delay_reason
from app.retrievers import RetrievalHit, get_retriever


logger = logging.getLogger(__name__)


CHUNK_SIZE = 600
CHUNK_OVERLAP = 100
# A4: 来源数 3 -> 4。结构感知切块后文档被分成更细的章节块，
# 多主题问题的答案常跨 3 个以上块（如"工单处理要求"涉及分级/升级/规范），
# Top-3 会把关键块截掉；4 个来源在证据门控与引用审核下仍然可控。
MAX_SOURCES = 4
# A2: 一般问题的证据最低分 6 -> 15（满分 100 的覆盖率口径）。
# 旧值 6 形同虚设；锚点门控已拦截"配置/BGP"类词面重合问题，
# 15 给合法但字面重合低的题目留空间，真正的噪声题分数都在个位数。
DEFAULT_MIN_TOP_SCORE = 15
DEFAULT_MIN_INTENT_COVERAGE = 0.3


@dataclass
class EvidenceCheck:
    passed: bool
    status: str
    detail: str


@dataclass
class EvidencePolicy:
    intent: str
    min_top_score: int
    min_related_source_count: int
    min_intent_coverage: float


def ingest_document(filename: str, content: str) -> DocumentUploadResponse:
    document_id = str(uuid4())
    document_chunks = split_text(content)
    init_db()
    init_graph_store()
    # 文档、chunk、embedding 与派生图谱共享一个事务：任一步失败都不
    # 暴露半完成文档，也不需要事后补偿删除。
    with connect() as conn:
        chunk_count = insert_document(
            document_id=document_id,
            filename=filename,
            chunks=document_chunks,
            conn=conn,
        )
        index_document_graph(document_id, conn=conn)

    return DocumentUploadResponse(
        document_id=document_id,
        filename=filename,
        chunk_count=chunk_count,
    )


def list_documents() -> list[DocumentSummary]:
    return [
        DocumentSummary(
            document_id=row["id"],
            filename=row["filename"],
            chunk_count=row["chunk_count"],
            created_at=row["created_at"],
        )
        for row in list_document_rows()
    ]


def delete_document(document_id: str) -> bool:
    return delete_document_and_rebuild(document_id)


def split_text(text: str) -> list[tuple[str, str]]:
    """A4 结构感知切块：按标题与句子边界切分，返回 (标题, 内容) 列表。

    旧版按 600 字符硬切，字段/句子会被拦腰截断（"调整后交付日|期:2026年7月8日"），
    检索与图谱抽取质量都受损。新版规则：
    - markdown 标题行（# ...）成为所在块的标题，随 chunk 入库；
    - 句子优先打包，块目标大小 CHUNK_SIZE，块间携带 CHUNK_OVERLAP 字符的句子重叠；
    - 单句超过块大小才硬切（此时保留标题前缀）。
    """
    normalized = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if not normalized:
        return []

    blocks: list[tuple[str, list[str]]] = []  # (标题层级链, 句子列表)
    heading_stack: list[str] = []
    current_sentences: list[str] = []

    for line in normalized.split("\n"):
        if line.startswith("#"):
            if current_sentences:
                blocks.append((" / ".join(heading_stack), current_sentences))
                current_sentences = []
            level = len(line) - len(line.lstrip("#"))
            title = line.lstrip("#").strip()[:80]
            # 标题层级链：h1 > h2 组成 "文档标题 / 章节标题"，
            # 让章节 chunk 也携带文档级关键词（"运维工单处理手册 / 工单分级与时限"）。
            heading_stack = heading_stack[: level - 1] + [title]
            continue
        for sentence in re.split(r"(?<=[。！？!?；;])\s*", line):
            sentence = sentence.strip()
            if not sentence:
                continue
            if sentence.startswith("#"):
                if current_sentences:
                    blocks.append((" / ".join(heading_stack), current_sentences))
                    current_sentences = []
                level = len(sentence) - len(sentence.lstrip("#"))
                title = sentence.lstrip("#").strip()[:80]
                heading_stack = heading_stack[: level - 1] + [title]
                continue
            current_sentences.append(sentence)
    if current_sentences:
        blocks.append((" / ".join(heading_stack), current_sentences))

    chunks: list[tuple[str, str]] = []
    for title, sentences in blocks:
        chunks.extend(_pack_sentences(title, sentences))
    return chunks


def _pack_sentences(title: str, sentences: list[str]) -> list[tuple[str, str]]:
    """把句子打包成不超过 CHUNK_SIZE 的块，块间句子级重叠 CHUNK_OVERLAP。"""
    chunks: list[tuple[str, str]] = []
    buffer: list[str] = []
    buffer_len = 0

    def emit() -> None:
        if buffer:
            chunks.append((title, "\n".join(buffer)))

    for sentence in sentences:
        # 单句超长：硬切，保留标题前缀帮助溯源
        if len(sentence) > CHUNK_SIZE:
            emit()
            buffer, buffer_len = [], 0
            for start in range(0, len(sentence), CHUNK_SIZE - CHUNK_OVERLAP):
                piece = sentence[start : start + CHUNK_SIZE]
                chunks.append((title, piece))
                if start + CHUNK_SIZE >= len(sentence):
                    break
            continue

        if buffer_len + len(sentence) > CHUNK_SIZE and buffer:
            emit()
            # 句子级重叠：把末尾句子带进下一块，直到达到重叠预算
            overlap: list[str] = []
            overlap_len = 0
            for carried in reversed(buffer):
                if overlap_len + len(carried) > CHUNK_OVERLAP:
                    break
                overlap.insert(0, carried)
                overlap_len += len(carried)
            buffer = overlap
            buffer_len = overlap_len

        buffer.append(sentence)
        buffer_len += len(sentence)

    emit()
    return chunks


def answer_question(question: str, answer_mode: str = "auto", retriever_mode: str | None = None) -> ChatResponse:
    queries = expand_queries(question)
    trace: list[TraceStep] = [
        TraceStep(
            name="question_received",
            status="ok",
            detail=f"收到问题，回答模式为 {answer_mode}，检索模式为 {retriever_mode or 'keyword'}。",
        ),
        TraceStep(
            name="query_expansion",
            status="ok",
            detail=f"生成 {len(queries)} 个检索 query：{' / '.join(queries)}",
        )
    ]
    retriever = get_retriever(retriever_mode)
    retrieval_result = retriever.search(queries)
    ranked_hits = retrieval_result.hits

    if not ranked_hits:
        trace.append(
            TraceStep(
                name="retrieve",
                status="empty",
                detail=f"使用 {retriever.name} 检索器，知识库中没有可检索的 chunk。",
            )
        )
        return ChatResponse(
            answer="当前知识库中还没有可用资料。请先上传 txt 或 md 文档。",
            sources=[],
            trace=trace,
        )

    useful_hits = [hit for hit in ranked_hits if hit.score > 0]
    trace.append(
        TraceStep(
            name="retrieve",
            status="ok" if useful_hits else "no_match",
            detail=(
                f"使用 {retriever.name} 检索器，共扫描 {retrieval_result.scanned_count} 个 chunk，"
                f"命中 {len(useful_hits)} 个分数大于 0 的 chunk。"
            ),
        )
    )
    if not useful_hits:
        return ChatResponse(
            answer="我没有在已上传资料中找到足够相关的内容，因此暂时不能可靠回答这个问题。",
            sources=[],
            trace=trace,
        )

    selected = sorted(
        useful_hits,
        key=lambda hit: hit.score + title_term_boost(question, hit.chunk.title),
        reverse=True,
    )[:MAX_SOURCES]
    sources = [
        Source(
            document_id=hit.chunk.document_id,
            filename=hit.chunk.filename,
            chunk_index=hit.chunk.chunk_index,
            score=hit.score,
            content=hit.chunk.content,
            title=hit.chunk.title,
        )
        for hit in selected
    ]
    selected_query_detail = build_matched_query_detail(selected)
    trace.append(
        TraceStep(
            name="select_sources",
            status="ok",
            detail=f"选择前 {len(sources)} 个来源作为回答证据，最高分为 {sources[0].score}。{selected_query_detail}",
        )
    )

    evidence_check = check_evidence(question, sources)
    trace.append(
        TraceStep(
            name="evidence_check",
            status=evidence_check.status,
            detail=evidence_check.detail,
        )
    )
    if not evidence_check.passed:
        return ChatResponse(
            answer=build_insufficient_evidence_answer(evidence_check),
            sources=sources,
            trace=trace,
        )

    answer, answer_trace, token_usage = build_answer(question, sources, answer_mode)
    trace.extend(answer_trace)

    return ChatResponse(answer=answer, sources=sources, trace=trace, token_usage=token_usage)


def expand_queries(question: str) -> list[str]:
    queries = [question]

    if any(word in question for word in ["延期", "延迟", "推迟", "延误", "逾期"]):
        queries.extend(
            [
                "延期原因 由于 因为 导致 推迟",
                "原计划交付日期 调整后交付日期 项目负责人 合同风险",
            ]
        )

    if any(word in question for word in ["风险", "违约"]):
        queries.append("合同风险 延期超过 风险说明 违约")

    if any(word in question for word in ["负责人", "谁负责", "owner"]):
        queries.append("项目负责人 负责人 owner")

    return deduplicate_preserve_order(queries)


def title_term_boost(question: str, title: str) -> int:
    """A4 选择阶段加成：问题的双字词命中块标题（标题层级链）时 +25。

    只影响来源选择排序，Source.score 展示仍为原始分。
    例："工单处理要求"命中"运维工单处理手册 / 工单分级与时限"标题，
    让分级时限块进入 Top-K，而不是被无关 query 拉起的其他块挤掉。
    """
    if not title:
        return 0
    compact = re.sub(r"\s+", "", question.lower())
    stop = {"什么", "情况", "问题", "一下", "这个", "那个", "方案", "怎么", "如何", "哪里", "哪些", "多少", "请问"}
    bigrams = {
        compact[i : i + 2]
        for i in range(len(compact) - 1)
        if "\u4e00" <= compact[i] <= "\u9fff" or "\u4e00" <= compact[i + 1] <= "\u9fff"
    }
    bigrams -= stop
    title_lower = title.lower()
    return 25 if any(bigram in title_lower for bigram in bigrams) else 0


def deduplicate_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = value.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)

    return result


def build_matched_query_detail(selected_hits: list[RetrievalHit]) -> str:
    if not selected_hits:
        return ""

    entries = deduplicate_preserve_order(
        [
            (
                f"{hit.chunk.filename}#chunk{hit.chunk.chunk_index}=score{hit.score}"
                f"，query={format_matched_queries(hit.matched_queries)}"
            )
            for hit in selected_hits
        ]
    )
    return "命中来源：" + "；".join(entries)


def format_matched_queries(queries: list[str]) -> str:
    if not queries:
        return "无"

    return " / ".join(queries[:2])


def check_evidence(question: str, sources: list[Source]) -> EvidenceCheck:
    if not sources:
        return EvidenceCheck(
            passed=False,
            status="failed",
            detail="没有可用来源，不能回答。",
        )

    top_score = max(source.score for source in sources)
    policy = choose_evidence_policy(question)
    related_sources = [source for source in sources if source.score >= policy.min_top_score]
    intent_groups = extract_intent_terms(question)
    # A4: 证据文本包含块标题——"保密条款""违约责任"等关键信息可能在标题而非正文
    evidence_text = "\n".join(f"{source.title} {source.content}" for source in sources)
    # A2: 意图覆盖按同义词组判定——组内任一词命中即覆盖该组，
    # 避免"为什么/为何/原因"全命中这种过度要求误拒。
    matched_groups = [group for group in intent_groups if any(term in evidence_text for term in group)]
    intent_coverage = len(matched_groups) / len(intent_groups) if intent_groups else 1.0

    reasons = [
        f"问题类型 {policy.intent}",
        f"最高分 {top_score}",
        f"强相关来源 {len(related_sources)} 个",
    ]
    if intent_groups:
        reasons.append(f"意图覆盖率 {intent_coverage:.0%} ({len(matched_groups)}/{len(intent_groups)})")

    # A2: 主题锚点先于分数门控检查——错题即使分数达标也判 topic_mismatch，
    # 给可观测面板更准确的拒绝原因（而不是 weak_score 掩盖真正的问题）。
    if not _topic_anchors_match(question, evidence_text):
        return EvidenceCheck(
            passed=False,
            status="topic_mismatch",
            detail="主题锚点未命中：" + "，".join(reasons) + "。问题核心主题在证据中未找到落点。",
        )

    if top_score < policy.min_top_score:
        return EvidenceCheck(
            passed=False,
            status="weak_score",
            detail="证据不足：" + "，".join(reasons) + f"。当前问题最低最高分要求为 {policy.min_top_score}。",
        )

    if len(related_sources) < policy.min_related_source_count:
        return EvidenceCheck(
            passed=False,
            status="not_enough_sources",
            detail="证据不足：" + "，".join(reasons) + f"。当前问题至少需要 {policy.min_related_source_count} 个强相关来源。",
        )

    if intent_groups and intent_coverage < policy.min_intent_coverage:
        return EvidenceCheck(
            passed=False,
            status="intent_coverage_low",
            detail="证据不足：" + "，".join(reasons) + f"。当前问题最低意图覆盖率要求为 {policy.min_intent_coverage:.0%}。",
        )

    return EvidenceCheck(
        passed=True,
        status="passed",
        detail="证据检查通过：" + "，".join(reasons) + "。",
    )


def choose_evidence_policy(question: str) -> EvidencePolicy:
    # A2: 风险意图只看风险词本身；裸"合同"是中性词，
    # 会把"合同的首付款比例是多少"这类事实题误路由到高风险门槛并拒答。
    if any(word in question for word in ["风险", "违约", "赔偿"]):
        return EvidencePolicy(
            intent="risk",
            min_top_score=8,
            min_related_source_count=1,
            min_intent_coverage=0.4,
        )

    # A2: 补齐"延误/导致/造成"等同义表述，避免落到 general 政策的高门槛。
    if any(word in question for word in ["延期", "延迟", "推迟", "延误", "逾期", "原因", "为什么", "为何", "导致", "造成"]):
        return EvidencePolicy(
            intent="causal",
            min_top_score=6,
            min_related_source_count=1,
            min_intent_coverage=0.3,
        )

    # A2: 补齐"多久/几号/编号"等事实型问法。
    if any(word in question for word in ["负责人", "谁负责", "日期", "什么时候", "多久", "几号", "编号", "owner"]):
        return EvidencePolicy(
            intent="fact",
            min_top_score=4,
            min_related_source_count=1,
            min_intent_coverage=0.2,
        )

    return EvidencePolicy(
        intent="general",
        min_top_score=DEFAULT_MIN_TOP_SCORE,
        min_related_source_count=1,
        min_intent_coverage=DEFAULT_MIN_INTENT_COVERAGE,
    )


def extract_intent_terms(question: str) -> list[list[str]]:
    """提取问题的意图同义词组（A2：组内任一词命中证据即覆盖该组）。"""
    groups = [
        ["延期", "延迟", "推迟", "延误", "逾期"],
        ["原因", "为什么", "为何"],
        ["风险", "合同", "违约"],
        ["负责人", "谁负责", "owner"],
        ["交付", "日期", "计划"],
    ]

    matched_groups: list[list[str]] = []
    for group in groups:
        if any(term in question for term in group):
            matched_groups.append(group)

    return matched_groups


def build_insufficient_evidence_answer(evidence_check: EvidenceCheck) -> str:
    return (
        "我找到了部分相关资料，但证据强度不足，暂时不能可靠回答这个问题。\n\n"
        f"判断依据：{evidence_check.detail}\n\n"
        "你可以尝试上传更相关的资料，或把问题改得更具体一些。"
    )


def estimate_tokens(text: str) -> int:
    """离线估算：中文约 0.7 token/字，用于 local 模式的规模统计。"""
    return math.ceil(len(text) * 0.7) if text else 0


def build_local_usage(question: str, sources: list[Source], answer: str, source: str) -> TokenUsage:
    prompt_text = question + "".join(item.content for item in sources)
    return TokenUsage(
        prompt_tokens=estimate_tokens(prompt_text),
        completion_tokens=estimate_tokens(answer),
        total_tokens=estimate_tokens(prompt_text) + estimate_tokens(answer),
        estimated_cost_usd=0.0,
        source=source,
    )


def build_answer(
    question: str,
    sources: list[Source],
    answer_mode: str,
    extra_contexts: list[str] | None = None,
) -> tuple[str, list[TraceStep], TokenUsage]:
    """生成回答。extra_contexts（图谱/工具上下文）在 API 模式进入 prompt，
    local 模式追加到答案末尾（模板答案无法推理，保持可读展示）。"""
    normalized_mode = answer_mode.lower()
    trace: list[TraceStep] = []

    if normalized_mode in {"auto", "local"}:
        delay_reason = extract_delay_reason(question, sources)
        if delay_reason:
            trace.append(
                TraceStep(
                    name="answer",
                    status="rule_matched",
                    detail="命中延期原因规则，使用内部规则式因果抽取生成回答。",
                )
            )
            return (
                append_extra_contexts(delay_reason, extra_contexts),
                trace,
                build_local_usage(question, sources, delay_reason, "local_rule"),
            )

    if normalized_mode == "local":
        trace.append(
            TraceStep(
                name="answer",
                status="local",
                detail="用户选择 local 模式，使用内部 RAG 模板生成回答。",
            )
        )
        answer = build_fallback_answer(
            sources,
            note="当前选择了 local 模式，因此使用内部 RAG 规则/模板生成答案。",
        )
        return (
            append_extra_contexts(answer, extra_contexts),
            trace,
            build_local_usage(question, sources, answer, "local_template"),
        )

    if normalized_mode == "api" or (normalized_mode == "auto" and is_llm_configured()):
        try:
            llm_answer = generate_answer(question, sources, extra_contexts)
            trace.append(
                TraceStep(
                    name="answer",
                    status="api",
                    detail=f"使用模型 API 基于 {len(sources)} 个来源生成回答。",
                )
            )
            usage = TokenUsage(
                prompt_tokens=llm_answer.prompt_tokens,
                completion_tokens=llm_answer.completion_tokens,
                total_tokens=llm_answer.total_tokens,
                estimated_cost_usd=get_llm_pricing().estimate_cost(
                    llm_answer.prompt_tokens, llm_answer.completion_tokens
                ),
                source="api",
            )
            return llm_answer.content, trace, usage
        except Exception as exc:
            # 供应商报错原文只进服务端日志，不进用户可见的答案/trace（信息泄漏）
            logger.exception("LLM answer generation failed; falling back to template answer")
            trace.append(
                TraceStep(
                    name="answer",
                    status="api_failed",
                    detail="API 生成失败，退回内部模板（失败原因已记录到服务端日志）。",
                )
            )
            answer = build_fallback_answer(
                sources,
                note="API 生成失败，已退回到内部 RAG 模板答案。配置或网络恢复后可重试。",
            )
            return (
                append_extra_contexts(answer, extra_contexts),
                trace,
                build_local_usage(question, sources, answer, "local_template"),
            )

    trace.append(
        TraceStep(
            name="answer",
            status="local_fallback",
            detail="未配置可用 API Key，使用内部 RAG 模板生成回答。",
        )
    )
    answer = build_fallback_answer(
        sources,
        note="当前未配置可用 API Key，因此使用内部 RAG 模板答案。配置后可通过 answer_mode=api 调用模型生成总结。",
    )
    return (
        append_extra_contexts(answer, extra_contexts),
        trace,
        build_local_usage(question, sources, answer, "local_template"),
    )


def append_extra_contexts(answer: str, extra_contexts: list[str] | None) -> str:
    """local 模式下把图谱/工具上下文追加到答案末尾（API 模式在 prompt 内注入，不追加）。"""
    blocks = [block.strip() for block in (extra_contexts or []) if block and block.strip()]
    if not blocks:
        return answer
    return answer.rstrip() + "\n\n" + "\n\n".join(blocks)


def _topic_anchors_match(question: str, evidence_text: str) -> bool:
    """检查问题的核心主题锚点是否在证据中出现（A2 强化版）。

    旧版 any-match 太宽松：任意一个通用词命中就放行，导致
    "如何配置思科路由器的BGP协议"被含"配置"二字的无关语料放行。
    A2 三级规则：
    1. 显式实体锚点（客户X / 项目编号类英文缩写）：必须全部出现在证据中；
    2. 没有显式实体时，至少一个 >=3 字的中文窗口锚点命中；
    3. 长锚点都不命中时，至少 2 个双字锚点命中才放行。
    """
    normalized = question.lower().strip()
    compact = re.sub(r"\s+", "", normalized)
    # 证据同样去空白，避免"客户B"锚点匹配不上带空格的"客户 B"。
    evidence_lower = re.sub(r"\s+", "", evidence_text.lower())

    # 1. 显式实体锚点：客户X、英文缩写（BGP 等）
    entity_anchors: list[str] = []
    entity_anchors.extend(re.findall(r"客户\s*[a-z0-9甲乙丙丁一二三四五六七八九十]{1,8}", compact))
    entity_anchors.extend(re.findall(r"[a-z]{3,}", compact))
    if entity_anchors:
        return all(anchor in evidence_lower for anchor in entity_anchors)

    # 2. 长锚点：3-6 字的连续中文窗口
    for size in (6, 5, 4, 3):
        for anchor in _extract_cjk_windows(compact, size):
            if anchor in evidence_lower:
                return True

    # 3. 双字锚点兜底：至少命中 2 个
    bigrams = [
        compact[i : i + 2]
        for i in range(len(compact) - 1)
        if all("\u4e00" <= c <= "\u9fff" for c in compact[i : i + 2])
    ]
    stop = {"什么", "情况", "问题", "一下", "这个", "那个", "方案", "怎么", "如何", "哪里", "哪些", "多少"}
    anchors = [a for a in bigrams if a not in stop]
    if not anchors:
        return True  # 无法提取锚点时放行
    return sum(1 for a in anchors if a in evidence_lower) >= 2


def _extract_cjk_windows(compact: str, size: int) -> list[str]:
    """提取连续的纯中文窗口（size 字），用于长锚点匹配。"""

    windows: list[str] = []
    for run in re.findall(r"[一-龥]+", compact):
        if len(run) >= size:
            windows.extend(run[i : i + size] for i in range(len(run) - size + 1))
    return windows
