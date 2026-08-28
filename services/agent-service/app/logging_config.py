"""统一日志配置：JSON 行格式，便于后续接入日志采集。

零新增依赖，stdlib logging 实现。LOG_FORMAT_TEXT=1 时退回人类可读格式（本地调试）。
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging() -> None:
    """应用启动时调用一次；重复调用无副作用。"""
    root = logging.getLogger()
    if getattr(root, "_app_logging_configured", False):
        return
    handler = logging.StreamHandler(sys.stdout)
    if os.getenv("LOG_FORMAT_TEXT", "").strip().lower() in {"1", "true", "yes"}:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    else:
        handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO")
    # 第三方库降噪
    for noisy in ("httpx", "httpcore", "openai", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    root._app_logging_configured = True  # type: ignore[attr-defined]
