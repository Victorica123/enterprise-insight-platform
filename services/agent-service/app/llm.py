from dataclasses import dataclass

from app.config import get_llm_settings
from app.evidence import source_location
from app.llm_client import create_chat_completion
from app.models import Source
from app.prompts import load_prompt, render_prompt


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
    return _has_usable_api_key(settings.api_key)


def _has_usable_api_key(api_key: str | None) -> bool:
    if not api_key or not api_key.strip():
        return False
    normalized = api_key.strip().lower()
    return not any(marker in normalized for marker in ("change_me", "your-", "replace-with"))


def generate_answer(
    question: str,
    sources: list[Source],
    extra_contexts: list[str] | None = None,
) -> LLMAnswer:
    settings = get_llm_settings()
    if not _has_usable_api_key(settings.api_key):
        raise RuntimeError(f"未配置 {settings.provider} API Key。")

    response = create_chat_completion(
        messages=[
            {"role": "system", "content": build_system_prompt()},
            {"role": "user", "content": build_user_prompt(question, sources, extra_contexts)},
        ],
        temperature=0.2,
        purpose="answer",
    )

    content = response.choices[0].message.content or "模型没有返回可用内容。"
    usage = getattr(response, "usage", None)
    return LLMAnswer(
        content=content,
        prompt_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
        completion_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
    )


def build_system_prompt() -> str:
    """阶段 0.7：提示词外置在 app/prompts/*.txt，这里只做加载（进程内缓存）。"""
    return load_prompt("answer_system")


def build_user_prompt(
    question: str,
    sources: list[Source],
    extra_contexts: list[str] | None = None,
) -> str:
    """只做变量填充：来源条目、补充上下文与问题分别套用各自模板。"""
    evidence = "\n\n".join(
        render_prompt(
            "answer_source_item",
            index=index + 1,
            source_type=source.source_type,
            location=source_location(source),
            video_lines=(
                f"资产 ID：{source.asset_id}\n片段 ID：{source.segment_id}\n"
                if source.source_type == "video"
                else ""
            ),
            content=source.content,
        )
        for index, source in enumerate(sources)
    )

    blocks = [block.strip() for block in (extra_contexts or []) if block and block.strip()]
    context_section = (
        "\n\n" + render_prompt("answer_context_section", blocks="\n\n".join(blocks))
        if blocks
        else ""
    )
    return render_prompt(
        "answer_user",
        question=question,
        evidence=evidence,
        context_section=context_section,
    )
