from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from functools import cache
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langsmith import tracing_context

from app.analysis_models import (
    AnalysisStageResult,
    EvidenceRef,
    OpenQuestion,
    PrdDraft,
    PrdRequirement,
)
from app.config import get_settings
from app.retrievers import Chunk


@dataclass(frozen=True)
class DomainSpecialistResult:
    key: str
    label: str
    findings: tuple[str, ...]
    evidence: tuple[Chunk, ...]
    error: str | None = None


@dataclass(frozen=True)
class AnalysisRun:
    stages: list[AnalysisStageResult]
    open_questions: list[OpenQuestion]
    prd: PrdDraft | None
    specialist_results: tuple[DomainSpecialistResult, ...] = ()


class _AnalysisState(TypedDict):
    """Per-call state only; durable checkpoints remain in analysis_store."""

    objective: str
    chunks: list[Chunk]
    answers: dict[str, str]
    corpus: str
    evidence: list[EvidenceRef]
    stages: list[AnalysisStageResult]
    stakeholder_findings: list[str]
    risk_findings: list[str]
    conflicts: list[str]
    failed_count: int
    specialist_results: tuple[DomainSpecialistResult, ...]
    open_questions: list[OpenQuestion]
    prd: PrdDraft | None


@dataclass(frozen=True)
class _SpecialistConfig:
    key: str
    label: str
    pattern: str


_SPECIALIST_CONFIGS = (
    _SpecialistConfig("business", "业务", r"客户|用户|产品|流程|审批|运营|目标|转化|效率"),
    _SpecialistConfig("data", "数据与安全", r"数据|字段|指标|报表|隐私|权限|tenant|owner|存储|保留"),
    _SpecialistConfig("technology", "技术与集成", r"接口|API|系统|服务|集成|性能|延迟|并发|缓存|数据库"),
    _SpecialistConfig("rules", "规则与合规", r"规则|合规|法律|审批|必须|禁止|优先|P[0-3]|权限"),
)
_CONFLICT_PATTERN = re.compile(r"冲突|矛盾|不一致|两种口径|不同意见|口径未统一", re.I)
_SPECIALIST_EXECUTOR = ThreadPoolExecutor(max_workers=get_settings().specialist_workers, thread_name_prefix="analysis-domain")


def run_six_stage_analysis(
    objective: str,
    chunks: list[Chunk],
    confirmations: dict[str, str] | None = None,
) -> AnalysisRun:
    """Run all six graph stages over an already authorized evidence snapshot."""
    return _invoke_analysis(objective, chunks, _clean_answers(confirmations), [])


def resume_six_stage_analysis(
    objective: str,
    chunks: list[Chunk],
    previous_stages: list[AnalysisStageResult],
    confirmations: dict[str, str],
) -> AnalysisRun:
    """Re-enter at convergence using the persisted business checkpoint."""
    if [stage.stage for stage in previous_stages[:4]] != [
        "intent", "stakeholders", "domain", "risks",
    ]:
        raise ValueError("Analysis checkpoint does not contain completed stages 1-4.")
    first_four = previous_stages[:4]
    if any(stage.status != "COMPLETED" for stage in first_four):
        raise ValueError("Analysis checkpoint stages 1-4 must be completed.")
    return _invoke_analysis(objective, chunks, _clean_answers(confirmations), first_four)


def _invoke_analysis(
    objective: str,
    chunks: list[Chunk],
    answers: dict[str, str],
    first_four: list[AnalysisStageResult],
) -> AnalysisRun:
    bounded = chunks[:200]
    domain_findings = first_four[2].findings if first_four else []
    state = _AnalysisState(
        objective=objective, chunks=bounded, answers=answers,
        corpus="\n".join(chunk.content for chunk in bounded),
        evidence=[_evidence(chunk) for chunk in bounded[:12]],
        stages=first_four,
        # Keep the existing resume semantics; fresh nodes set raw findings.
        stakeholder_findings=first_four[1].findings if first_four else [],
        risk_findings=first_four[3].findings if first_four else [],
        conflicts=[finding for finding in domain_findings if finding.startswith("[冲突]")],
        failed_count=sum(finding.startswith("[specialist失败]") for finding in domain_findings),
        specialist_results=(), open_questions=[], prd=None,
    )
    # A host's LangSmith environment must not export this workflow's evidence.
    with tracing_context(enabled=False, parent=False):
        result = _analysis_graph().invoke(state, config={"callbacks": [], "recursion_limit": 16})
    return AnalysisRun(
        stages=result["stages"], open_questions=result["open_questions"],
        prd=result["prd"], specialist_results=result["specialist_results"],
    )


def _intent_node(state: _AnalysisState) -> dict[str, object]:
    stage = AnalysisStageResult(
        stage="intent", status="COMPLETED",
        summary=f"分析目标已确定：{state['objective'].strip()}",
        findings=["交付物：证据化需求分析与 PRD 草稿", f"冻结证据范围：{len(state['chunks'])} 个片段"],
        evidence=state["evidence"][:3],
    )
    return {"stages": [stage]}


def _stakeholders_node(state: _AnalysisState) -> dict[str, object]:
    findings = _unique(chunk.speaker for chunk in state["chunks"] if chunk.speaker) or _matched_terms(
        state["corpus"], ["客户", "用户", "产品", "研发", "测试", "负责人"],
    )
    stage = AnalysisStageResult(
        stage="stakeholders", status="COMPLETED",
        summary="已识别有证据支持的参与者；未明确的决策权不会由 Agent 猜测。",
        findings=findings or ["材料未明确标注干系人身份"],
        evidence=[ref for ref in state["evidence"] if ref.speaker][:6] or state["evidence"][:2],
    )
    return {"stages": [*state["stages"], stage], "stakeholder_findings": findings}


def _domain_node(state: _AnalysisState) -> dict[str, object]:
    results = _run_domain_specialists(tuple(state["chunks"]))
    findings = [finding for result in results for finding in result.findings]
    evidence = _unique_chunks(chunk for result in results for chunk in result.evidence)
    conflicts = _conflict_findings(state["chunks"])
    failed_count = sum(result.error is not None for result in results)
    stage = AnalysisStageResult(
        stage="domain", status="COMPLETED",
        summary=(
            "4 个有界领域 specialist 已按固定顺序合并；"
            f"发现 {len(conflicts)} 个显式冲突，{failed_count} 个执行失败。"
        ),
        findings=(findings + conflicts) or ["当前材料不足以形成领域结论"],
        evidence=[_evidence(chunk) for chunk in evidence[:12]] or state["evidence"][:8],
    )
    return {
        "stages": [*state["stages"], stage], "specialist_results": results,
        "conflicts": conflicts, "failed_count": failed_count,
    }


def _risks_node(state: _AnalysisState) -> dict[str, object]:
    findings = _unique(_risk_findings(state["chunks"]) + state["conflicts"])
    stage = AnalysisStageResult(
        stage="risks", status="COMPLETED",
        summary="已检查冲突、依赖、交付与合规风险。",
        findings=findings or ["未发现材料中被明确表述的风险；这不等同于不存在风险"],
        evidence=[_evidence(chunk) for chunk in state["chunks"] if _is_risk(chunk.content)][:8],
    )
    return {"stages": [*state["stages"], stage], "risk_findings": findings}


def _convergence_node(state: _AnalysisState) -> dict[str, object]:
    questions = _open_questions(
        state["corpus"], state["answers"], bool(state["chunks"]),
        conflict_count=len(state["conflicts"]), failed_count=state["failed_count"],
    )
    stage = AnalysisStageResult(
        stage="convergence", status="WAITING_CONFIRMATION" if questions else "COMPLETED",
        summary=(
            "存在影响 PRD 正确性的事实缺口，需要人工确认。"
            if questions else "关键事实已达到生成可评审 PRD 草稿的最低条件。"
        ),
        findings=[f"已确认：{key} = {value}" for key, value in state["answers"].items()],
        evidence=state["evidence"][:4], open_questions=questions,
    )
    return {"stages": [*state["stages"][:4], stage], "open_questions": questions}


def _prd_node(state: _AnalysisState) -> dict[str, object]:
    prd = _build_prd(
        state["objective"], state["chunks"], state["stakeholder_findings"],
        state["risk_findings"], state["answers"],
    )
    stage = AnalysisStageResult(
        stage="prd", status="COMPLETED", summary="PRD 草稿已生成，仍需人工评审后才能发布。",
        findings=[f"生成 {len(prd.requirements)} 条需求", "当前状态：DRAFT"],
        evidence=state["evidence"][:8],
    )
    return {"stages": [*state["stages"], stage], "prd": prd}


@cache
def _analysis_graph():
    """Cache topology, never request state; no framework persistence is enabled."""
    builder = StateGraph(_AnalysisState)
    nodes = {
        "intent": _intent_node, "stakeholders": _stakeholders_node,
        "domain": _domain_node, "risks": _risks_node,
        "convergence": _convergence_node, "prd": _prd_node,
    }
    for name, node in nodes.items():
        builder.add_node(name, node)
    builder.add_conditional_edges(
        START, lambda state: "convergence" if state["stages"] else "intent",
        {"intent": "intent", "convergence": "convergence"},
    )
    names = list(nodes)
    for source, target in zip(names[:4], names[1:5], strict=True):
        builder.add_edge(source, target)
    builder.add_conditional_edges(
        "convergence", lambda state: "wait" if state["open_questions"] else "ready",
        {"wait": END, "ready": "prd"},
    )
    builder.add_edge("prd", END)
    return builder.compile()


def _run_domain_specialists(chunks: tuple[Chunk, ...]) -> tuple[DomainSpecialistResult, ...]:
    results: dict[str, DomainSpecialistResult] = {}
    futures = {
        _SPECIALIST_EXECUTOR.submit(_run_one_specialist, config, chunks): config
        for config in _SPECIALIST_CONFIGS
    }
    for future in as_completed(futures):
        config = futures[future]
        try:
            results[config.key] = future.result()
        except Exception as exc:  # isolate one specialist from the other dimensions
            results[config.key] = DomainSpecialistResult(
                key=config.key,
                label=config.label,
                findings=(f"[specialist失败] {config.label}维度需要人工复核",),
                evidence=(),
                error=type(exc).__name__,
            )
    return tuple(results[config.key] for config in _SPECIALIST_CONFIGS)


def _run_one_specialist(
    config: _SpecialistConfig,
    chunks: tuple[Chunk, ...],
) -> DomainSpecialistResult:
    matched = tuple(chunk for chunk in chunks if re.search(config.pattern, chunk.content, re.I))[:4]
    findings = tuple(
        f"[{config.label}] {_title(_clean(chunk.content))}" for chunk in matched
    )
    if not findings:
        findings = (f"[{config.label}] 材料未提供该维度的明确事实",)
    return DomainSpecialistResult(
        key=config.key, label=config.label, findings=findings, evidence=matched,
    )


def _open_questions(
    corpus: str,
    answers: dict[str, str],
    has_evidence: bool,
    *,
    conflict_count: int = 0,
    failed_count: int = 0,
) -> list[OpenQuestion]:
    candidates: list[OpenQuestion] = []
    if not has_evidence:
        candidates.append(OpenQuestion(
            question_id="evidence_scope", question="请选定可访问的视频或文档并重新创建分析。",
            reason="当前冻结范围没有可访问的正分证据，仅填写文字不能扩大授权或改写快照",
        ))
    if not re.search(r"决策|负责人|拍板|审批人|owner", corpus, re.I):
        candidates.append(OpenQuestion(
            question_id="decision_maker", question="谁是本次需求的最终决策者？",
            reason="材料未明确决策权归属",
        ))
    if not re.search(r"验收|成功标准|完成标准|acceptance", corpus, re.I):
        candidates.append(OpenQuestion(
            question_id="acceptance_criteria", question="哪些可量化条件代表需求验收通过？",
            reason="材料未给出可测试的验收口径",
        ))
    if not re.search(r"优先|P[0-3]|必须|最高|次要|priority", corpus, re.I):
        candidates.append(OpenQuestion(
            question_id="priority_rule", question="需求优先级按什么规则排序？",
            reason="材料未给出优先级依据",
        ))
    if conflict_count:
        candidates.append(OpenQuestion(
            question_id="domain_conflict", question="材料存在冲突口径，最终采用哪一种？",
            reason=f"领域 specialist 识别到 {conflict_count} 个显式冲突",
        ))
    if failed_count:
        candidates.append(OpenQuestion(
            question_id="specialist_review", question="失败的领域维度由谁人工复核并补充结论？",
            reason=f"{failed_count} 个领域 specialist 执行失败，系统没有静默忽略",
        ))
    return [
        question for question in candidates
        if question.question_id == "evidence_scope" or question.question_id not in answers
    ]


def _build_prd(
    objective: str,
    chunks: list[Chunk],
    stakeholders: list[str],
    risks: list[str],
    answers: dict[str, str],
) -> PrdDraft:
    requirements: list[PrdRequirement] = []
    for index, chunk in enumerate(chunks[:8], start=1):
        description = _clean(chunk.content)[:500]
        if not description:
            continue
        acceptance = answers.get("acceptance_criteria") or _sentence_with(
            chunk.content, r"验收|成功标准|完成标准",
        )
        criteria = [acceptance] if acceptance else ["由产品与测试基于该证据补充可量化验收指标"]
        requirements.append(PrdRequirement(
            requirement_id=f"REQ-{index:03d}", title=_title(description), description=description,
            acceptance_criteria=criteria, evidence=[_evidence(chunk)],
            assumptions=[] if acceptance else ["验收指标尚未在原始材料中明确"],
        ))
    return PrdDraft(
        title=f"{objective.strip()} · PRD 草稿",
        executive_summary=f"本草稿基于 {len(chunks)} 个冻结授权证据片段生成；未获证据支持的内容保持为假设。",
        goals=[objective.strip()],
        stakeholders=stakeholders or [answers.get("decision_maker", "待确认")],
        requirements=requirements,
        risks=risks or ["材料未明确风险，发布前需人工复核"],
    )


def _conflict_findings(chunks: list[Chunk]) -> list[str]:
    return _unique(
        f"[冲突] {_clean(chunk.content)[:220]}"
        for chunk in chunks if _CONFLICT_PATTERN.search(chunk.content)
    )[:8]


def _evidence(chunk: Chunk) -> EvidenceRef:
    return EvidenceRef(
        source_type="video" if chunk.source_type == "video" else "document",
        document_id=chunk.document_id, filename=chunk.filename, chunk_index=chunk.chunk_index,
        excerpt=_clean(chunk.content)[:300], asset_id=chunk.asset_id, segment_id=chunk.segment_id,
        start_ms=chunk.start_ms, end_ms=chunk.end_ms, speaker=chunk.speaker,
    )


def _risk_findings(chunks: list[Chunk]) -> list[str]:
    return _unique(_clean(chunk.content)[:240] for chunk in chunks if _is_risk(chunk.content))[:8]


def _is_risk(text: str) -> bool:
    return bool(re.search(r"风险|延期|阻塞|依赖|冲突|矛盾|不一致|缺少|无法|不能|合规|隐私|失败", text, re.I))


def _matched_terms(text: str, terms: list[str]) -> list[str]:
    return [term for term in terms if term.lower() in text.lower()]


def _sentence_with(text: str, pattern: str) -> str:
    return next((part.strip() for part in re.split(r"[。！？\n]", text) if re.search(pattern, part, re.I)), "")


def _title(text: str) -> str:
    first = re.split(r"[。！？；\n]", text, maxsplit=1)[0].strip()
    return first[:80] or "未命名需求"


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _clean_answers(confirmations: dict[str, str] | None) -> dict[str, str]:
    return {
        key: value.strip() for key, value in (confirmations or {}).items() if value.strip()
    }


def _unique(values) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _unique_chunks(values) -> list[Chunk]:
    seen: set[tuple[str, int]] = set()
    result: list[Chunk] = []
    for chunk in values:
        key = (chunk.document_id, chunk.chunk_index)
        if key not in seen:
            seen.add(key)
            result.append(chunk)
    return result
