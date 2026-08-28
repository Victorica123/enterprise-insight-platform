from dataclasses import dataclass

from app.config import get_llm_settings
from app.llm_client import create_chat_completion
from app.models import Source


@dataclass(frozen=True)
class LLMAnswer:
    """API 回答内容 + 真实 token 用量（供 V5 成本核算）。"""

    content: str
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


def is_llm_configured() -> bool:
    settings = get_llm_settings()
    return bool(settings.api_key)


def generate_answer(
    question: str,
    sources: list[Source],
    extra_contexts: list[str] | None = None,
) -> LLMAnswer:
    settings = get_llm_settings()
    if not settings.api_key:
        raise RuntimeError(f"未配置 {settings.provider} API Key。")

    response = create_chat_completion(
        messages=[
            {"role": "system", "content": build_system_prompt()},
            {"role": "user", "content": build_user_prompt(question, sources, extra_contexts)},
        ],
        temperature=0.2,
    )

    content = response.choices[0].message.content or "模型没有返回可用内容。"
    usage = getattr(response, "usage", None)
    return LLMAnswer(
        content=content,
        prompt_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
        completion_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
    )


def build_system_prompt() -> str:
    return (
        "你是企业知识库助手。你必须只基于用户提供的来源资料回答。"
        "如果来源资料不足以回答，就明确说资料不足。"
        "回答要先给结论，再给依据，最后给必要的补充信息。"
        "如果提供了系统补充上下文（关系图谱、工具调用结果），可以结合它进行推理，"
        "但事实依据仍以来源资料为准，不要编造来源或补充上下文中不存在的事实。"
    )


def build_user_prompt(
    question: str,
    sources: list[Source],
    extra_contexts: list[str] | None = None,
) -> str:
    evidence = "\n\n".join(
        f"来源 {index + 1}\n"
        f"文档：{source.filename}\n"
        + (f"章节：{source.title}\n" if source.title else "")
        + f"Chunk：{source.chunk_index}\n"
        f"内容：{source.content}"
        for index, source in enumerate(sources)
    )

    context_section = ""
    blocks = [block.strip() for block in (extra_contexts or []) if block and block.strip()]
    if blocks:
        context_section = (
            "\n\n系统补充上下文（关系图谱与工具调用结果，若与问题相关请纳入推理）：\n"
            + "\n\n".join(blocks)
        )

    return (
        f"用户问题：{question}\n\n"
        f"可用来源资料：\n{evidence}"
        f"{context_section}\n\n"
        "请基于这些来源资料和补充上下文回答，并在回答中说明依据来自哪些来源。"
    )
