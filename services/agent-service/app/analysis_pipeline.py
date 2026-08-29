from __future__ import annotations

import re
from dataclasses import dataclass

from app.analysis_models import (
    AnalysisStageResult, EvidenceRef, OpenQuestion, PrdDraft, PrdRequirement,
)
from app.retrievers import Chunk


@dataclass(frozen=True)
class AnalysisRun:
    stages: list[AnalysisStageResult]
    open_questions: list[OpenQuestion]
    prd: PrdDraft | None


def run_six_stage_analysis(
    objective: str,
    chunks: list[Chunk],
    confirmations: dict[str, str] | None = None,
) -> AnalysisRun:
    answers = {key: value.strip() for key, value in (confirmations or {}).items() if value.strip()}
    bounded = chunks[:200]
    evidence = [_evidence(chunk) for chunk in bounded[:12]]
    corpus = "\n".join(chunk.content for chunk in bounded)
    speakers = _unique(chunk.speaker for chunk in bounded if chunk.speaker)

    intent = AnalysisStageResult(
        stage="intent", status="COMPLETED",
        summary=f"分析目标已确定：{objective.strip()}",
        findings=["交付物：证据化需求分析与 PRD 草稿", f"证据范围：{len(bounded)} 个片段"],
        evidence=evidence[:3],
    )
    stakeholder_findings = speakers or _matched_terms(corpus, ["客户", "用户", "产品", "研发", "测试", "负责人"])
    stakeholders = AnalysisStageResult(
        stage="stakeholders", status="COMPLETED",
        summary="已识别有证据支持的参与者；未明确的决策权不会由 Agent 猜测。",
        findings=stakeholder_findings or ["材料未明确标注干系人身份"],
        evidence=[ref for ref in evidence if ref.speaker][:6] or evidence[:2],
    )
    themes = _extract_findings(bounded, limit=6)
    domain = AnalysisStageResult(
        stage="domain", status="COMPLETED",
        summary="已从选定材料提取业务诉求、约束与术语。",
        findings=themes or ["当前材料不足以形成领域结论"], evidence=evidence[:8],
    )
    risk_findings = _risk_findings(bounded)
    risks = AnalysisStageResult(
        stage="risks", status="COMPLETED",
        summary="已检查冲突、依赖、交付与合规风险。",
        findings=risk_findings or ["未发现材料中被明确表述的风险；这不等同于不存在风险"],
        evidence=[_evidence(chunk) for chunk in bounded if _is_risk(chunk.content)][:8],
    )

    questions = _open_questions(corpus, answers, bool(bounded))
    convergence = AnalysisStageResult(
        stage="convergence",
        status="WAITING_CONFIRMATION" if questions else "COMPLETED",
        summary="存在影响 PRD 正确性的事实缺口，需要人工确认。" if questions else "关键事实已达到生成可评审 PRD 草稿的最低条件。",
        findings=[f"已确认：{key} = {value}" for key, value in answers.items()],
        evidence=evidence[:4], open_questions=questions,
    )
    stages = [intent, stakeholders, domain, risks, convergence]
    if questions:
        return AnalysisRun(stages=stages, open_questions=questions, prd=None)

    prd = _build_prd(objective, bounded, stakeholder_findings, risk_findings, answers)
    stages.append(AnalysisStageResult(
        stage="prd", status="COMPLETED", summary="PRD 草稿已生成，仍需人工评审后才能发布。",
        findings=[f"生成 {len(prd.requirements)} 条需求", "当前状态：DRAFT"],
        evidence=evidence[:8],
    ))
    return AnalysisRun(stages=stages, open_questions=[], prd=prd)


def _open_questions(corpus: str, answers: dict[str, str], has_evidence: bool) -> list[OpenQuestion]:
    candidates: list[OpenQuestion] = []
    if not has_evidence:
        candidates.append(OpenQuestion(question_id="evidence_scope", question="需要纳入哪些视频或文档作为分析证据？", reason="当前范围没有可访问证据"))
    if not re.search(r"决策|负责人|拍板|审批人|owner", corpus, re.I):
        candidates.append(OpenQuestion(question_id="decision_maker", question="谁是本次需求的最终决策者？", reason="材料未明确决策权归属"))
    if not re.search(r"验收|成功标准|完成标准|acceptance", corpus, re.I):
        candidates.append(OpenQuestion(question_id="acceptance_criteria", question="哪些可量化条件代表需求验收通过？", reason="材料未给出可测试的验收口径"))
    if not re.search(r"优先|P[0-3]|必须|最高|次要|priority", corpus, re.I):
        candidates.append(OpenQuestion(question_id="priority_rule", question="需求优先级按什么规则排序？", reason="材料未给出优先级依据"))
    return [question for question in candidates if question.question_id not in answers]


def _build_prd(objective: str, chunks: list[Chunk], stakeholders: list[str], risks: list[str], answers: dict[str, str]) -> PrdDraft:
    requirements: list[PrdRequirement] = []
    for index, chunk in enumerate(chunks[:8], start=1):
        description = _clean(chunk.content)[:500]
        if not description:
            continue
        acceptance = answers.get("acceptance_criteria") or _sentence_with(chunk.content, r"验收|成功标准|完成标准")
        criteria = [acceptance] if acceptance else ["由产品与测试基于该证据补充可量化验收指标"]
        requirements.append(PrdRequirement(
            requirement_id=f"REQ-{index:03d}", title=_title(description), description=description,
            acceptance_criteria=criteria, evidence=[_evidence(chunk)],
            assumptions=[] if acceptance else ["验收指标尚未在原始材料中明确"],
        ))
    return PrdDraft(
        title=f"{objective.strip()} · PRD 草稿",
        executive_summary=f"本草稿基于 {len(chunks)} 个授权证据片段生成；未获证据支持的内容保持为假设。",
        goals=[objective.strip()],
        stakeholders=stakeholders or [answers.get("decision_maker", "待确认")],
        requirements=requirements,
        risks=risks or ["材料未明确风险，发布前需人工复核"],
    )


def _evidence(chunk: Chunk) -> EvidenceRef:
    return EvidenceRef(
        source_type="video" if chunk.source_type == "video" else "document",
        document_id=chunk.document_id, filename=chunk.filename, chunk_index=chunk.chunk_index,
        excerpt=_clean(chunk.content)[:300], asset_id=chunk.asset_id, segment_id=chunk.segment_id,
        start_ms=chunk.start_ms, end_ms=chunk.end_ms, speaker=chunk.speaker,
    )


def _extract_findings(chunks: list[Chunk], limit: int) -> list[str]:
    return _unique(_title(_clean(chunk.content)) for chunk in chunks if _clean(chunk.content))[:limit]


def _risk_findings(chunks: list[Chunk]) -> list[str]:
    return _unique(_clean(chunk.content)[:240] for chunk in chunks if _is_risk(chunk.content))[:8]


def _is_risk(text: str) -> bool:
    return bool(re.search(r"风险|延期|阻塞|依赖|冲突|缺少|无法|不能|合规|隐私|失败", text, re.I))


def _matched_terms(text: str, terms: list[str]) -> list[str]:
    return [term for term in terms if term.lower() in text.lower()]


def _sentence_with(text: str, pattern: str) -> str:
    return next((part.strip() for part in re.split(r"[。！？\n]", text) if re.search(pattern, part, re.I)), "")


def _title(text: str) -> str:
    first = re.split(r"[。！？；\n]", text, maxsplit=1)[0].strip()
    return first[:80] or "未命名需求"


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _unique(values) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
