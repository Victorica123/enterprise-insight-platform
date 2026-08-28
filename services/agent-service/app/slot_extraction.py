"""工具调用的槽位抽取：从用户问题与检索证据中提取工单字段。

从 agentic_rag 拆出的独立关注点。修复要点：
- 工单 ID 支持大写 UUID 并统一小写归一；
- 目标状态无法识别时返回空串（由调用方拒绝生成草稿），
  不再静默默认 resolved；
- 优先级判定合并冗余分支。
"""
from __future__ import annotations

import re

from app.models import Source


def extract_ticket_title(question: str, sources: list[Source]) -> str:
    """从问题和证据中提取工单标题。"""
    title_patterns = [
        r"(?:关于|针对|跟进)[：:\s]*(.+?)(?:的|，|。|？|\?|$)",
        r"(?:创建|生成)[：:\s]*(.+?)(?:工单|的|，|。|$)",
    ]
    for pattern in title_patterns:
        match = re.search(pattern, question)
        if match:
            return match.group(1).strip()[:100]

    if sources:
        content = sources[0].content[:200]
        for prefix in ["客户", "项目"]:
            match = re.search(rf"{prefix}[：:\s]*(\S+)", content)
            if match:
                return f"{prefix}{match.group(1)} - 跟进工单"

    return "项目跟进工单"


def extract_ticket_description(question: str, sources: list[Source]) -> str:
    """从问题和证据中提取工单描述。"""
    parts = [f"问题：{question}"]

    if sources:
        parts.append("\n相关证据：")
        for i, source in enumerate(sources[:2], 1):
            parts.append(f"[来源 {i}] {source.content[:300]}")

    return "\n".join(parts)[:2000]


def extract_priority(question: str, sources: list[Source]) -> str:
    """从问题与证据中提取优先级（question 已包含在 combined 中，合并判断）。"""
    combined = question + " ".join(s.content[:200] for s in sources)
    if any(w in combined for w in ["紧急", "严重", "风险", "违约", "延期超过", "赔偿", "重大"]):
        return "high"
    if any(w in combined for w in ["延期", "问题"]):
        return "medium"
    return "medium"


def extract_risk_level(question: str, sources: list[Source]) -> str:
    """提取风险等级。"""
    combined = question + " ".join(s.content[:200] for s in sources)
    if any(w in combined for w in ["严重", "违约", "赔偿", "重大风险"]):
        return "高"
    if any(w in combined for w in ["风险", "延期超过"]):
        return "中"
    return ""


def extract_assignee(question: str, sources: list[Source]) -> str:
    """提取指派人。"""
    for source in sources:
        match = re.search(r"负责人[：:\s]*(\S+)", source.content)
        if match:
            return match.group(1)
    return ""


def extract_ticket_id(question: str) -> str:
    """从问题中提取工单 ID（hex/连字符，兼容大写，统一小写归一）。"""
    match = re.search(r"(?:工单|ticket|编号|ID|id)[：:\s#]*([a-fA-F0-9][a-fA-F0-9-]{7,})", question)
    if match:
        return match.group(1).rstrip("-").lower()
    return ""


def extract_target_status(question: str) -> str:
    """从问题中提取目标状态；无法识别时返回空串，调用方必须拒绝草拟。

    旧版默认返回 resolved，会把"更新一下工单"这类语义模糊的请求
    静默草拟成"已解决"，在工单场景是业务风险。
    """
    status_map = {
        "重新打开": "open",
        "关闭": "closed",
        "解决": "resolved",
        "处理": "in_progress",
        "开始": "in_progress",
    }
    for kw, status in status_map.items():
        if kw in question:
            return status
    return ""
