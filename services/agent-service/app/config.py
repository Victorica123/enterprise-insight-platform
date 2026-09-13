"""Typed deployment settings with environment-aware caching.

Only this module reads process configuration. Explicit environment overrides
invalidate the cache, including overrides used by tests and offline evaluators.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse


@dataclass(frozen=True)
class LLMSettings:
    provider: str
    api_key: str | None = field(repr=False)
    base_url: str
    model: str
    timeout_seconds: float = 30.0
    max_retries: int = 2
    max_completion_tokens: int = 1200


@dataclass(frozen=True)
class LLMPricing:
    """USD per million tokens; configurable estimates, not provider invoices."""

    prompt_per_1m_usd: float
    completion_per_1m_usd: float

    def estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        return round((prompt_tokens * self.prompt_per_1m_usd
                      + completion_tokens * self.completion_per_1m_usd) / 1_000_000, 6)


@dataclass(frozen=True)
class CallLimits:
    max_model_calls: int = 8
    max_tool_calls: int = 6


@dataclass(frozen=True)
class EvidenceBudgetSettings:
    per_source_chars: int = 2200
    total_chars: int = 5200


@dataclass(frozen=True)
class Settings:
    environment: str
    auth_mode: str
    jwt_algorithm: str
    jwt_secret: str = field(repr=False)
    jwt_issuer: str
    jwt_audience: str
    jwt_jwks_url: str
    jwt_clock_skew_seconds: int
    database_url: str = field(repr=False)
    database_path: Path
    require_mysql: bool
    default_answer_mode: str
    retriever_mode: str
    llm: LLMSettings
    llm_pricing: LLMPricing
    llm_router_enabled: bool
    llm_response_format: str
    call_limits: CallLimits
    evidence_budget: EvidenceBudgetSettings
    embedding_model: str
    reranker_model: str
    embedding_rebuild_batch_size: int
    embedding_backfill_interval_seconds: int
    approval_sod_enforced: bool
    max_upload_bytes: int
    media_ingest_service_token: str = field(repr=False)
    prompt_dir: str
    log_format_text: bool
    log_level: str
    model_egress_policy: str
    model_egress_allowed_tenants: frozenset[str]
    retention_enabled: bool
    retention_transcript_days: int
    retention_audit_days: int
    retention_batch_size: int
    retention_scan_interval_seconds: int
    workers: int
    thread_pool_size: int
    specialist_workers: int
    conversation_lease_seconds: int
    errors: tuple[str, ...] = field(repr=False)

    def validate(self) -> None:
        errors = list(self.errors)
        if self.database_url and urlparse(self.database_url).scheme not in {"mysql", "mysql+pymysql"}:
            errors.append("AGENT_DATABASE_URL must use mysql:// or mysql+pymysql://")
        if urlparse(self.llm.base_url).scheme not in {"http", "https"}:
            errors.append("The configured LLM base URL must use http(s)")
        if self.prompt_dir and not Path(self.prompt_dir).is_dir():
            errors.append("AGENT_PROMPT_DIR must be an existing directory")
        if self.model_egress_policy not in {"allow", "allowlist", "deny"}:
            errors.append("MODEL_EGRESS_POLICY must be allow, allowlist or deny")
        if errors:
            # Names/reasons only: configuration errors must not disclose secrets.
            raise RuntimeError("Invalid Agent configuration: " + "; ".join(errors))


_NAMES = """
APP_ENV AGENT_AUTH_MODE JWT_ALGORITHM SHARED_JWT_SECRET APP_JWT_SECRET
APP_JWT_ISSUER APP_JWT_AUDIENCE JWT_JWKS_URL JWT_CLOCK_SKEW_SECONDS
AGENT_DATABASE_URL AGENT_DATABASE_PATH AGENT_REQUIRE_MYSQL DEFAULT_ANSWER_MODE RETRIEVER_MODE
LLM_PROVIDER OPENAI_API_KEY OPENAI_BASE_URL OPENAI_MODEL DEEPSEEK_API_KEY DEEPSEEK_BASE_URL DEEPSEEK_MODEL
LLM_TIMEOUT_SECONDS LLM_MAX_RETRIES LLM_MAX_COMPLETION_TOKENS LLM_ROUTER_ENABLED LLM_RESPONSE_FORMAT
LLM_PROMPT_PRICE_PER_1M_USD LLM_COMPLETION_PRICE_PER_1M_USD AGENT_MAX_MODEL_CALLS AGENT_MAX_TOOL_CALLS
EVIDENCE_SOURCE_CHAR_BUDGET EVIDENCE_TOTAL_CHAR_BUDGET EMBEDDING_MODEL RERANKER_MODEL
EMBEDDING_REBUILD_BATCH_SIZE EMBEDDING_BACKFILL_INTERVAL_SECONDS APPROVAL_SOD_ENFORCED
MAX_UPLOAD_BYTES MEDIA_INGEST_SERVICE_TOKEN AGENT_PROMPT_DIR LOG_FORMAT_TEXT LOG_LEVEL
MODEL_EGRESS_POLICY MODEL_EGRESS_ALLOWED_TENANTS RETENTION_ENABLED RETENTION_TRANSCRIPT_DAYS
RETENTION_AUDIT_DAYS RETENTION_BATCH_SIZE RETENTION_SCAN_INTERVAL_SECONDS
AGENT_WORKERS AGENT_THREAD_POOL_SIZE AGENT_SPECIALIST_WORKERS CONVERSATION_LEASE_SECONDS
""".split()


class _Environment:
    def __init__(self, values: dict[str, str | None]):
        self.values = values
        self.errors: list[str] = []

    def text(self, name: str, default: str = "") -> str:
        value = self.values.get(name)
        return value.strip() if value is not None else default

    def choice(self, name: str, default: str, choices: set[str]) -> str:
        value = self.text(name, default).lower()
        if value not in choices:
            self.errors.append(f"{name} must be one of {', '.join(sorted(choices))}")
            return default
        return value

    def flag(self, name: str, default: bool) -> bool:
        value = self.text(name, "1" if default else "0").lower()
        if value not in {"1", "true", "yes", "on", "0", "false", "no", "off", ""}:
            self.errors.append(f"{name} must be a boolean")
            return default
        return value in {"1", "true", "yes", "on"}

    def number(self, name: str, default: float, minimum: float, maximum: float | None = None, *, integer: bool = False):
        raw = self.text(name)
        try:
            value = (int(raw) if integer else float(raw)) if raw else default
            if not math.isfinite(value):
                raise ValueError()
        except ValueError:
            self.errors.append(f"{name} must be a finite {'integer' if integer else 'number'}")
            return default
        if value < minimum or (maximum is not None and value > maximum):
            self.errors.append(f"{name} is outside its supported range")
        value = max(minimum, value)
        return min(maximum, value) if maximum is not None else value

    def integer(self, name: str, default: int, minimum: int = 1, maximum: int | None = None) -> int:
        return int(self.number(name, default, minimum, maximum, integer=True))


@lru_cache(maxsize=8)
def _settings_from_environment(snapshot: tuple[str | None, ...]) -> Settings:
    env = _Environment(dict(zip(_NAMES, snapshot, strict=True)))
    environment = env.text("APP_ENV", "development").lower()
    provider = env.choice("LLM_PROVIDER", "deepseek", {"deepseek", "openai"})
    prefix = provider.upper()
    llm = LLMSettings(
        provider, env.text(f"{prefix}_API_KEY") or None,
        env.text(f"{prefix}_BASE_URL", "https://api.openai.com/v1" if provider == "openai" else "https://api.deepseek.com"),
        env.text(f"{prefix}_MODEL", "gpt-4.1-mini" if provider == "openai" else "deepseek-v4-flash"),
        env.number("LLM_TIMEOUT_SECONDS", 30.0, 1.0),
        env.integer("LLM_MAX_RETRIES", 2, 0, 5),
        env.integer("LLM_MAX_COMPLETION_TOKENS", 1200, 64, 32768),
    )
    prompt_price, completion_price = (0.40, 1.60) if provider == "openai" else (0.27, 1.10)
    values = dict(
        environment=environment,
        auth_mode=env.choice("AGENT_AUTH_MODE", "jwt", {"development", "jwt"}),
        jwt_algorithm=env.text("JWT_ALGORITHM", "HS256").upper(),
        jwt_secret=env.values.get("SHARED_JWT_SECRET") or env.values.get("APP_JWT_SECRET") or "",
        jwt_issuer=env.text("APP_JWT_ISSUER", "enterprise-insight"),
        jwt_audience=env.text("APP_JWT_AUDIENCE", "enterprise-insight-api"),
        jwt_jwks_url=env.text("JWT_JWKS_URL"),
        jwt_clock_skew_seconds=env.integer("JWT_CLOCK_SKEW_SECONDS", 30, 0),
        database_url=env.text("AGENT_DATABASE_URL"),
        database_path=Path(env.text("AGENT_DATABASE_PATH", str(Path(__file__).resolve().parents[1] / "data" / "knowledge_base.sqlite3"))),
        require_mysql=env.flag("AGENT_REQUIRE_MYSQL", False),
        default_answer_mode=env.choice("DEFAULT_ANSWER_MODE", "local", {"local", "api", "auto"}),
        retriever_mode=env.choice("RETRIEVER_MODE", "keyword", {"keyword", "embedding", "hybrid"}),
        llm=llm,
        llm_pricing=LLMPricing(env.number("LLM_PROMPT_PRICE_PER_1M_USD", prompt_price, 0), env.number("LLM_COMPLETION_PRICE_PER_1M_USD", completion_price, 0)),
        llm_router_enabled=env.flag("LLM_ROUTER_ENABLED", True),
        llm_response_format=env.choice("LLM_RESPONSE_FORMAT", "auto", {"auto", "off", "none", "disabled", "json_object", "json_schema"}),
        call_limits=CallLimits(env.integer("AGENT_MAX_MODEL_CALLS", 8, 1, 64), env.integer("AGENT_MAX_TOOL_CALLS", 6, 1, 64)),
        evidence_budget=EvidenceBudgetSettings(env.integer("EVIDENCE_SOURCE_CHAR_BUDGET", 2200, 200, 50_000), env.integer("EVIDENCE_TOTAL_CHAR_BUDGET", 5200, 400, 200_000)),
        embedding_model=env.text("EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5"),
        reranker_model=env.text("RERANKER_MODEL"),
        embedding_rebuild_batch_size=env.integer("EMBEDDING_REBUILD_BATCH_SIZE", 64),
        embedding_backfill_interval_seconds=env.integer("EMBEDDING_BACKFILL_INTERVAL_SECONDS", 60, 5, 3600),
        approval_sod_enforced=env.flag("APPROVAL_SOD_ENFORCED", True),
        max_upload_bytes=env.integer("MAX_UPLOAD_BYTES", 50 * 1024 * 1024),
        media_ingest_service_token=env.text("MEDIA_INGEST_SERVICE_TOKEN"),
        prompt_dir=env.text("AGENT_PROMPT_DIR"),
        log_format_text=env.flag("LOG_FORMAT_TEXT", False),
        log_level=env.choice("LOG_LEVEL", "info", {"debug", "info", "warning", "error", "critical"}).upper(),
        model_egress_policy=env.text("MODEL_EGRESS_POLICY", "allowlist" if environment in {"production", "prod"} else "allow").lower(),
        model_egress_allowed_tenants=frozenset(value.strip() for value in env.text("MODEL_EGRESS_ALLOWED_TENANTS").split(",") if value.strip()),
        retention_enabled=env.flag("RETENTION_ENABLED", False),
        retention_transcript_days=env.integer("RETENTION_TRANSCRIPT_DAYS", 180),
        retention_audit_days=env.integer("RETENTION_AUDIT_DAYS", 365),
        retention_batch_size=env.integer("RETENTION_BATCH_SIZE", 200, 1, 1000),
        retention_scan_interval_seconds=env.integer("RETENTION_SCAN_INTERVAL_SECONDS", 3600),
        workers=env.integer("AGENT_WORKERS", 1, 1, 32),
        thread_pool_size=env.integer("AGENT_THREAD_POOL_SIZE", 40, 1, 256),
        specialist_workers=env.integer("AGENT_SPECIALIST_WORKERS", 4, 1, 32),
        conversation_lease_seconds=env.integer("CONVERSATION_LEASE_SECONDS", 120, 30, 3600),
    )
    return Settings(**values, errors=tuple(env.errors))


def get_settings() -> Settings:
    return _settings_from_environment(tuple(os.getenv(name) for name in _NAMES))


def load_local_env() -> None:
    api_dir = Path(__file__).resolve().parents[1]
    for env_path in (api_dir.parent.parent / ".env", api_dir / ".env"):
        load_env_file(env_path)


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


# Compatibility API: callers and tests can keep their established imports.
def get_default_answer_mode() -> str:
    return get_settings().default_answer_mode


def get_retriever_mode() -> str:
    return get_settings().retriever_mode


def get_llm_settings() -> LLMSettings:
    return get_settings().llm


def get_llm_pricing() -> LLMPricing:
    return get_settings().llm_pricing


def get_call_limits() -> CallLimits:
    return get_settings().call_limits


def get_evidence_budget_settings() -> EvidenceBudgetSettings:
    return get_settings().evidence_budget
