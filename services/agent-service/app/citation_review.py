"""Answer citation normalization and lightweight claim grounding checks."""
import re

from app.models import Source


def review_citations(answer: str, sources: list[Source]) -> tuple[str, str, str]:
    if not answer.strip() or not sources:
        return answer, "failed", "Reviewer Agent 未发现可验证的答案或来源。"

    citation_lines = [
        f"- [来源 {index}] {source.filename} / chunk {source.chunk_index}"
        for index, source in enumerate(sources, start=1)
    ]
    expected_markers = [f"[来源 {index}]" for index in range(1, len(sources) + 1)]
    has_standard_citation = any(marker in answer for marker in expected_markers)

    # B3: 声明级溯源——含数字/日期/百分比的事实句必须在来源中找到锚点
    unsupported = find_unsupported_claims(answer, sources)
    claim_note = ""
    if unsupported:
        claim_note = (
            f" Reviewer Agent 发现 {len(unsupported)} 条陈述在来源中找不到数字锚点"
            f"（如：{unsupported[0][:40]}），已附审核提示，请人工核对。"
        )

    if has_standard_citation:
        detail = "Reviewer Agent 检查通过：答案包含标准来源引用。" + claim_note
        if unsupported:
            answer = answer.rstrip() + "\n\n⚠️ 审核提示：部分陈述未在来源中找到锚点，请人工核对。"
        return answer, "passed", detail

    reviewed = answer.rstrip() + "\n\n证据引用：\n" + "\n".join(citation_lines)
    if unsupported:
        reviewed = reviewed + "\n\n⚠️ 审核提示：部分陈述未在来源中找到锚点，请人工核对。"
    return reviewed, "repaired", "Reviewer Agent 为答案补充了标准化来源引用。" + claim_note


def find_unsupported_claims(answer: str, sources: list[Source]) -> list[str]:
    """B3 声明级溯源：找出含事实数字/日期/百分比但来源中无锚点的陈述句。

    阈值刻意宽松：只对"带事实数字且完全无锚点"的句子报警，
    local 模板答案全部来自来源内容，不会误报；API 答案的数字幻觉会显形。
    """
    evidence = re.sub(r"\s+", "", "\n".join(f"{source.title} {source.content}" for source in sources).lower())

    claims: list[str] = []
    for sentence in re.split(r"(?<=[。！？!?；;\n])", answer):
        stripped = sentence.strip()
        if not stripped:
            continue
        facts = re.findall(
            r"\d{4}\s*[年/.-]\s*\d{1,2}\s*[月/.-]\s*\d{1,2}\s*日?|\d{2,}(?:\.\d+)?%?|\d+\.\d+%?",
            stripped,
        )
        if not facts:
            continue
        if not any(re.sub(r"\s+", "", fact.lower()) in evidence for fact in facts):
            claims.append(stripped[:120])
    return claims[:3]
