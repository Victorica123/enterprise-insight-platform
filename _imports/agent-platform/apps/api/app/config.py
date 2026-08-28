import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LLMSettings:
    provider: str
    api_key: str | None
    base_url: str
    model: str
    timeout_seconds: float = 30.0
    max_retries: int = 2
    max_completion_tokens: int = 1200


@dataclass(frozen=True)
class LLMPricing:
    """每百万 token 的美元单价，用于 V5 成本核算。"""

    prompt_per_1m_usd: float
    completion_per_1m_usd: float

    def estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        cost = (
            prompt_tokens * self.prompt_per_1m_usd
            + completion_tokens * self.completion_per_1m_usd
        ) / 1_000_000
        return round(cost, 6)


def load_local_env() -> None:
    api_dir = Path(__file__).resolve().parents[1]
    # 容器内 /app/app/config.py 只有 3 层父级，不能用 parents[3]（会 IndexError）
    workspace_dir = api_dir.parent.parent

    for env_path in (workspace_dir / ".env", api_dir / ".env"):
        load_env_file(env_path)


def load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def get_default_answer_mode() -> str:
    return os.getenv("DEFAULT_ANSWER_MODE", "local").strip().lower()


def get_retriever_mode() -> str:
    mode = os.getenv("RETRIEVER_MODE", "keyword").strip().lower()
    if mode not in {"keyword", "embedding", "hybrid"}:
        return "keyword"

    return mode


def get_llm_settings() -> LLMSettings:
    provider = os.getenv("LLM_PROVIDER", "deepseek").strip().lower()
    shared = {
        "timeout_seconds": _read_float("LLM_TIMEOUT_SECONDS", 30.0, minimum=1.0),
        "max_retries": _read_int("LLM_MAX_RETRIES", 2, minimum=0, maximum=5),
        "max_completion_tokens": _read_int(
            "LLM_MAX_COMPLETION_TOKENS", 1200, minimum=64, maximum=32768
        ),
    }

    if provider == "openai":
        return LLMSettings(
            provider=provider,
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            **shared,
        )

    return LLMSettings(
        provider="deepseek",
        api_key=os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
        **shared,
    )


def get_llm_pricing() -> LLMPricing:
    """按 provider 取默认单价（环境变量可覆盖），local 模式不计成本。

    修复说明：旧实现无论 LLM_PROVIDER 是什么都取 DeepSeek 价，
    配置 OpenAI 时成本面板全部算错。现在默认价跟随 provider，
    LLM_PROMPT_PRICE_PER_1M_USD / LLM_COMPLETION_PRICE_PER_1M_USD 仍可覆盖。
    """
    provider = get_llm_settings().provider
    if provider == "openai":
        # gpt-4.1-mini 公开价（与 OPENAI_MODEL 默认值对应）
        prompt_default, completion_default = 0.40, 1.60
    else:
        # DeepSeek 公开价（与 DEEPSEEK_MODEL 默认值对应）
        prompt_default, completion_default = 0.27, 1.10
    return LLMPricing(
        prompt_per_1m_usd=_read_float("LLM_PROMPT_PRICE_PER_1M_USD", prompt_default),
        completion_per_1m_usd=_read_float("LLM_COMPLETION_PRICE_PER_1M_USD", completion_default),
    )


def _read_float(name: str, fallback: float, *, minimum: float | None = None) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return fallback
    try:
        value = float(raw)
        return max(minimum, value) if minimum is not None else value
    except ValueError:
        return fallback


def _read_int(
    name: str,
    fallback: int,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return fallback
    try:
        value = int(raw)
    except ValueError:
        return fallback
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value
