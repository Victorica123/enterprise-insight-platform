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


def _topics(text: str) -> list[str]:
    return list(dict.fromkeys(re.sub(r"\s+", "", value) for value in _TOPIC.findall(text)))


def build_follow_up_questions(question: str, sources: list[Source], *,
                              recent_questions: tuple[str, ...] = ()) -> list[str]:
    text = "\n".join(f"{source.title} {source.content}" for source in sources)
    topics = _topics(question)
    topic_keys = {topic.casefold() for topic in topics}
    covered_questions = [question.lower()]
    # Suppress only the same explicit subject set. A prior customer's question
    # or a model summary is not proof that this subject has already been asked.
    if topic_keys:
        covered_questions.extend(previous.lower() for previous in recent_questions[-4:]
                                 if {topic.casefold() for topic in _topics(previous)} == topic_keys)
    # Keep multiple explicit subjects together instead of silently choosing one.
    prefix = "与".join(topics) + "的" if topics else ""
    return [
        prefix + suggestion
        for triggers, answered, suggestion in _RULES
        if any(term in text for term in triggers)
        and not any(term in previous for previous in covered_questions for term in answered)
    ][:3]
