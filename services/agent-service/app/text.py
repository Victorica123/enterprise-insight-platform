"""Shared text normalization helpers used by chunking, retrieval and planning.

These functions are deterministic and dependency-free so both the offline
evaluation gates and the request path share exactly one tokenizer.
"""

from __future__ import annotations

import re

# A2: 停用词——去掉只贡献噪声、不贡献主题的通用词/字，
# 减少"配置""情况"这类通用词制造的字面重合虚高分。
STOP_TERMS = frozenset({
    "什么", "怎么", "如何", "哪些", "这个", "那个", "一下",
    "情况", "问题", "为什么", "请问", "多少", "哪里", "方案", "时候",
})

CHAR_STOPS = frozenset({
    "的", "了", "是", "在", "与", "和", "及", "或", "吗", "呢",
    "啊", "请", "把", "被", "对", "从", "向", "就", "都", "也",
    "还", "会", "个", "有", "要", "为",
})

QUESTION_STOP_BIGRAMS = frozenset({
    "什么", "情况", "问题", "一下", "这个", "那个", "方案", "怎么", "如何",
    "哪里", "哪些", "多少", "请问",
})

_SEPARATORS = " \n\t\r,.;:!?，。！？；：、（）()[]{}<>\"'“”‘’"


def deduplicate_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = value.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def title_term_boost(question: str, title: str) -> int:
    """Existing title prior; applied before fusion, never after a final rerank."""
    if not title:
        return 0
    compact = re.sub(r"\s+", "", question.lower())
    bigrams = {
        compact[i : i + 2]
        for i in range(len(compact) - 1)
        if "\u4e00" <= compact[i] <= "\u9fff" or "\u4e00" <= compact[i + 1] <= "\u9fff"
    } - QUESTION_STOP_BIGRAMS
    title_lower = title.lower()
    return 25 if any(bigram in title_lower for bigram in bigrams) else 0


def normalize_text(text: str) -> str:
    normalized = text.lower()
    for separator in _SEPARATORS:
        normalized = normalized.replace(separator, " ")
    return normalized


def tokenize_words(text: str) -> set[str]:
    return {term for term in text.split(" ") if term}


def char_ngrams(text: str, size: int) -> set[str]:
    if size <= 0 or len(text) < size:
        return set()
    return {text[index : index + size] for index in range(len(text) - size + 1)}


def extract_search_terms(text: str) -> set[str]:
    """Words plus 1/2-gram CJK characters, minus stop words."""
    normalized = normalize_text(text)
    terms = tokenize_words(normalized)
    compact = "".join(normalized.split())
    terms.update(char_ngrams(compact, size=1))
    terms.update(char_ngrams(compact, size=2))
    return {term for term in terms if term not in STOP_TERMS and term not in CHAR_STOPS}


def cjk_bigrams(question: str) -> set[str]:
    """Question bigrams that contain at least one CJK character, minus question filler."""
    compact = re.sub(r"\s+", "", question.lower())
    bigrams = {
        compact[i : i + 2]
        for i in range(len(compact) - 1)
        if "一" <= compact[i] <= "鿿" or "一" <= compact[i + 1] <= "鿿"
    }
    return bigrams - QUESTION_STOP_BIGRAMS


def extract_cjk_windows(compact: str, size: int) -> list[str]:
    """Contiguous pure-CJK windows of ``size`` characters."""
    windows: list[str] = []
    for run in re.findall(r"[一-龥]+", compact):
        if len(run) >= size:
            windows.extend(run[i : i + size] for i in range(len(run) - size + 1))
    return windows


def content_anchors(question: str) -> list[str]:
    """Entity-like anchors a question must carry to be answerable without clarification."""
    compact = re.sub(r"\s+", "", question.lower())
    anchors: list[str] = []
    anchors.extend(re.findall(r"客户\s*[a-z0-9甲乙丙丁一二三四五六七八九十]{1,8}", compact))
    anchors.extend(re.findall(r"[a-z]{3,}", compact))
    anchors.extend(re.findall(r"\d{2,}", compact))
    for run in re.findall(r"[一-龥]+", compact):
        if len(run) >= 2 and run not in QUESTION_STOP_BIGRAMS:
            anchors.append(run)
    return deduplicate_preserve_order(anchors)


__all__ = [
    "CHAR_STOPS",
    "QUESTION_STOP_BIGRAMS",
    "STOP_TERMS",
    "char_ngrams",
    "cjk_bigrams",
    "content_anchors",
    "deduplicate_preserve_order",
    "extract_cjk_windows",
    "extract_search_terms",
    "normalize_text",
    "tokenize_words",
]
