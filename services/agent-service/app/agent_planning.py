"""Rule-based routing and retrieval planning fallback."""
import re


def detect_intents(question: str) -> list[str]:
    rules = [
        ("risk", ["风险", "违约", "赔偿"]),
        ("causal", ["为什么", "原因", "为何", "延期", "延迟", "推迟", "延误", "导致", "造成"]),
        ("fact", ["负责人", "谁负责", "日期", "什么时候", "多久", "几号", "编号", "多少"]),
        ("summary", ["总结", "概括", "主要内容", "整体情况"]),
    ]
    return [intent for intent, words in rules if any(word in question for word in words)]


def is_complex_question(question: str, intents: list[str]) -> bool:
    connectors = ["以及", "并且", "同时", "还有", "是否", "要不要", "分别"]
    return len(intents) > 1 or any(word in question for word in connectors) or len(question) >= 45


def rewrite_question(question: str) -> str:
    replacements = {
        "为什么": "原因",
        "为何": "原因",
        "有没有": "是否存在",
        "谁负责": "负责人",
        "啥时候": "日期",
        "怎么回事": "原因和过程",
        "延误": "延期",
        "多久": "时间",
    }
    rewritten = question.strip()
    for original, replacement in replacements.items():
        rewritten = rewritten.replace(original, replacement)
    return rewritten


def split_complex_question(question: str) -> list[str]:
    normalized = re.sub(r"(以及|并且|同时|还有|要不要)", "；", question)
    return [part.strip(" ，,。？?；;") for part in re.split(r"[；;？?]", normalized) if len(part.strip()) >= 4]


def build_intent_queries(intent: str) -> list[str]:
    mapping = {
        "risk": ["合同条款 延期风险 违约责任 赔偿 风险说明"],
        "causal": ["延期原因 根因 影响因素 交付推迟"],
        "fact": ["项目负责人 交付日期 当前状态"],
        "summary": ["项目概况 关键事实 风险 建议"],
        "general": ["相关记录 事实依据 处理结果"],
    }
    return mapping[intent] if intent in mapping else mapping["general"]


def build_retry_queries(question: str, intent: str) -> list[str]:
    retry_queries = build_intent_queries(intent)
    retry_queries.append(f"{rewrite_question(question)} 证据 记录")
    if intent in {"risk", "causal"}:
        retry_queries.append("原计划 调整后 延期原因 合同风险 负责人 建议动作")
    return list(dict.fromkeys(retry_queries))
