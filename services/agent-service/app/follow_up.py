"""Small, deterministic follow-up hints from this turn's authorized evidence."""

import re

from app.models import Source

_TOPIC = re.compile(r"(?:客户|项目)\s*[A-Za-z0-9][A-Za-z0-9_-]*", re.IGNORECASE)
# Evidence triggers, question intents already covered, suggested next question.
_RULES = (
    (("负责人",), ("负责人", "谁负责", "owner"), "负责人是谁？"),
    (("延期", "延迟", "推迟"), ("延期", "延迟", "推迟", "原因", "为什么", "为何"), "延期原因是什么？"),
    (("风险", "违约", "赔偿"), ("风险", "违约", "赔偿"), "有哪些风险？"),
    (("验收标准", "验收条件", "验收要求"), ("验收", "质量门槛"), "验收标准是什么？"),
    (("交付日期", "交付时间", "交付截止"), ("交付日期", "交付时间", "几号", "什么时候"), "交付日期是什么时候？"),
    (("响应时限", "响应时间"), ("响应时限", "响应时间"), "响应时限是多少？"),
    (("巡检",), ("巡检", "频率"), "巡检频率是多少？"),
)


def build_follow_up_questions(question: str, sources: list[Source]) -> list[str]:
    text = "\n".join(f"{source.title} {source.content}" for source in sources)
    topics = list(dict.fromkeys(re.sub(r"\s+", "", value) for value in _TOPIC.findall(question)))
    # Keep multiple explicit subjects together instead of silently choosing one.
    prefix = "与".join(topics) + "的" if topics else ""
    return [
        prefix + suggestion
        for triggers, answered, suggestion in _RULES
        if any(term in text for term in triggers)
        and not any(term in question.lower() for term in answered)
    ][:3]
