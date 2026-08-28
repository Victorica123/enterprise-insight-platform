"""Deterministic local-answer templates and field extraction rules."""
import re

from app.models import Source


def build_fallback_answer(sources: list[Source], note: str) -> str:
    evidence = "\n\n".join(
        f"[来源 {index + 1}: {source.filename} / chunk {source.chunk_index}"
        + (f" / 章节：{source.title}" if source.title else "")
        + f"]\n{source.content}"
        for index, source in enumerate(sources)
    )
    return (
        "根据当前知识库检索到的资料，最相关的信息如下。\n\n"
        f"{evidence}\n\n"
        f"{note}"
    )


def extract_delay_reason(question: str, sources: list[Source]) -> str | None:
    if not is_delay_reason_question(question):
        return None

    source_sentences = collect_sentences_by_source(sources)
    causal_match = find_delay_causal_sentence(source_sentences)
    if not causal_match:
        return None

    source_id, causal_sentence = causal_match
    sentences = source_sentences[source_id]
    cause = extract_cause(causal_sentence)
    source_text = collect_text_by_source(sources)[source_id]
    original_plan = extract_field(source_text, ["原计划交付日期", "原计划", "计划"])
    changed_plan = extract_field(source_text, ["调整后交付日期", "推迟到", "延期到", "延迟到"])
    owner = extract_field(source_text, ["项目负责人", "负责人"])
    risk = extract_section(source_text, ["合同风险", "风险提示"]) or find_first_sentence(
        sentences,
        ["风险", "延期超过", "合同"],
    )

    lines = []
    if cause:
        lines.append(f"结论：项目延期原因是：{cause}。")
    else:
        lines.append("结论：资料显示项目发生延期，但当前规则没有抽取到完整原因。")

    lines.append(f"依据：{causal_sentence}")

    details = []
    if original_plan:
        details.append(f"原计划：{original_plan}")
    if changed_plan and changed_plan != causal_sentence:
        details.append(f"调整后：{changed_plan}")
    if owner:
        details.append(f"负责人：{owner}")
    if risk:
        details.append(f"风险提示：{risk}")

    if details:
        lines.append("\n补充信息：")
        lines.extend(f"- {detail}" for detail in details)

    lines.append("\n说明：这是 V1 的规则式因果抽取结果，后续会升级为大模型基于证据的自然语言推理。")
    return "\n".join(lines)


def is_delay_reason_question(question: str) -> bool:
    delay_words = ["延期", "延迟", "推迟", "延误", "逾期"]
    reason_words = ["为什么", "原因", "为何", "因为什么", "怎么回事"]
    return any(word in question for word in delay_words) and any(word in question for word in reason_words)


def collect_sentences(sources: list[Source]) -> list[str]:
    grouped = collect_sentences_by_source(sources)
    sentences: list[str] = []
    for values in grouped.values():
        sentences.extend(values)

    return sentences


def collect_sentences_by_source(sources: list[Source]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for source in sources:
        content = source.content.replace("\n", "。")
        parts = re.split(r"(?<=[。！？!?])\s*", content)
        grouped[source.document_id] = [part.strip() for part in parts if part.strip()]

    return grouped


def collect_text_by_source(sources: list[Source]) -> dict[str, str]:
    return {source.document_id: source.content for source in sources}


def find_delay_causal_sentence(source_sentences: dict[str, list[str]]) -> tuple[str, str] | None:
    delay_words = ["延期", "延迟", "推迟", "延误", "逾期"]
    causal_words = ["由于", "因为", "原因是", "导致", "造成", "受", "受到"]

    # A2: 选择优先级修正——旧版第二轮"任意含因果词的句子"会抢答：
    # "为什么延期超过十五天要提交风险说明"被周会里的"部署失败的原因是网络策略"
    # 抢走因果句，答案丢掉合同条款。现在按 延迟词+因果词 > 延迟词+延期原因标签
    # > 仅延迟词 > 仅因果词 的顺序选句。
    for source_id, sentences in source_sentences.items():
        for sentence in sentences:
            has_delay = any(word in sentence for word in delay_words)
            has_cause = any(word in sentence for word in causal_words)
            if has_delay and has_cause:
                return source_id, sentence

    for source_id, sentences in source_sentences.items():
        for sentence in sentences:
            if any(word in sentence for word in delay_words) and "延期原因" in sentence:
                return source_id, sentence

    for source_id, sentences in source_sentences.items():
        for sentence in sentences:
            if any(word in sentence for word in delay_words):
                return source_id, sentence

    for source_id, sentences in source_sentences.items():
        for sentence in sentences:
            if any(word in sentence for word in causal_words):
                return source_id, sentence

    return None


def extract_cause(sentence: str) -> str | None:
    patterns = [
        r"延期原因\s*[:：]\s*([^，,。；;]{2,40})",
        r"由于(.+?)[，,。；;]",
        r"因为(.+?)[，,。；;]",
        r"原因是(.+?)[，,。；;]",
        r"受(.+?)影响",
        r"受到(.+?)影响",
        r"(.+?)导致",
        r"(.+?)造成",
    ]

    for pattern in patterns:
        match = re.search(pattern, sentence)
        if match:
            cause = match.group(1).strip()
            return cleanup_cause(cause)

    return None


def cleanup_cause(cause: str) -> str:
    return cause.strip(" ，,。；;：:")


def find_first_sentence(sentences: list[str], keywords: list[str]) -> str | None:
    for sentence in sentences:
        if any(keyword in sentence for keyword in keywords):
            return sentence

    return None


def extract_field(text: str, labels: list[str]) -> str | None:
    for label in labels:
        pattern = rf"{re.escape(label)}\s*[:：]?\s*(.+?)(?={field_boundary_pattern()}|[。\n]|$)"
        match = re.search(pattern, text)
        if match:
            value = match.group(1).strip(" ,，。；;")
            if value:
                return f"{label}：{value}"

    return None


def extract_section(text: str, labels: list[str]) -> str | None:
    for label in labels:
        pattern = rf"{re.escape(label)}\s*[:：]\s*(.+?)(?={field_boundary_pattern()}|。|$)"
        match = re.search(pattern, text)
        if match:
            value = match.group(1).strip(" ,，。；;")
            if value:
                return f"{label}：{value}"

    return None


def field_boundary_pattern() -> str:
    labels = [
        "客户",
        "项目",
        "原计划交付日期",
        "调整后交付日期",
        "项目负责人",
        "延期原因",
        "合同风险",
        "建议动作",
    ]
    return "|".join(rf"{label}\s*[:：]" for label in labels)
