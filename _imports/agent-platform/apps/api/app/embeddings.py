import hashlib
import json
import math
import os
import re


DEFAULT_EMBEDDING_DIMENSION = 64

# A3: 真实语义 embedding（fastembed/BGE-small-zh，512 维，ONNX 本地推理，无 torch 依赖）。
# 环境变量 EMBEDDING_MODEL 置空字符串可完全退回哈希 n-gram（离线/无模型场景）。
REAL_EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")

# A3: reranker（cross-encoder 精排），默认关闭以守住延迟预算。
# 设置 RERANKER_MODEL（如 jinaai/jina-reranker-v2-base-multilingual）即启用。
RERANKER_MODEL = os.getenv("RERANKER_MODEL", "")

_real_model_state: dict[str, object] = {}
_reranker_state: dict[str, object] = {}


def get_real_embedding_model():
    """惰性加载 fastembed 模型；不可用时返回 None（调用方回退哈希 embedding）。"""
    if "status" not in _real_model_state:
        if not REAL_EMBEDDING_MODEL:
            _real_model_state["status"] = "disabled"
            _real_model_state["model"] = None
            return None
        try:
            from fastembed import TextEmbedding

            _real_model_state["model"] = TextEmbedding(REAL_EMBEDDING_MODEL)
            _real_model_state["status"] = "ready"
        except Exception as exc:  # pragma: no cover - 依赖缺失/下载失败
            _real_model_state["status"] = "unavailable"
            _real_model_state["error"] = str(exc)
            _real_model_state["model"] = None
    return _real_model_state["model"] if _real_model_state["status"] == "ready" else None


def is_real_embedding_available() -> bool:
    return get_real_embedding_model() is not None


def warm_up_embeddings() -> None:
    """预加载真实 embedding 模型，避免首个请求承担模型加载延迟（A3 延迟口径修正）。

    模型不可用时为空操作；服务启动与离线门禁的计时循环前调用。
    注意必须跑一次真实推理：fastembed 的 ONNX 会话在首次 embed() 才初始化，
    只加载模型对象不足以消除首个请求的冷启动（曾导致 v2 门禁 p95 临界抖动）。
    """
    model = get_real_embedding_model()
    if model is None:
        return
    try:
        list(model.embed(["预热"]))
    except Exception:  # pragma: no cover - 预热失败不影响功能，首次真实调用会再尝试
        pass


def embed_real(texts: list[str]) -> list[list[float]] | None:
    """批量真实 embedding；任何失败返回 None，调用方回退哈希版。"""
    model = get_real_embedding_model()
    if model is None:
        return None
    try:
        safe_texts = [text if text and text.strip() else " " for text in texts]
        return [[float(value) for value in vector] for vector in model.embed(safe_texts)]
    except Exception:  # pragma: no cover - 推理失败时降级
        return None


def get_reranker():
    """惰性加载 cross-encoder reranker；未配置或不可用时返回 None。"""
    if "status" not in _reranker_state:
        if not RERANKER_MODEL:
            _reranker_state["status"] = "disabled"
            _reranker_state["model"] = None
            return None
        try:
            from fastembed.rerank.cross_encoder import TextCrossEncoder

            _reranker_state["model"] = TextCrossEncoder(RERANKER_MODEL)
            _reranker_state["status"] = "ready"
        except Exception as exc:  # pragma: no cover
            _reranker_state["status"] = "unavailable"
            _reranker_state["error"] = str(exc)
            _reranker_state["model"] = None
    return _reranker_state["model"] if _reranker_state["status"] == "ready" else None


def rerank_pairs(pairs: list[tuple[str, str]]) -> list[float] | None:
    """对 (query, text) 对批量打分；不可用时返回 None。

    实测（CPU）：BAAI/bge-reranker-base 约 48ms/对，Top-12 重排约 0.6s——
    这就是为什么默认关闭（RERANKER_MODEL 为空），由部署方按延迟预算决定开启。
    """
    model = get_reranker()
    if model is None or not pairs:
        return None
    try:
        return [float(score) for score in model.rerank_pairs(list(pairs))]
    except AttributeError:  # 兼容旧版 fastembed（predict API）
        try:
            return [float(score) for score in model.predict([list(pair) for pair in pairs])]
        except Exception:  # pragma: no cover
            return None
    except Exception:  # pragma: no cover
        return None


def build_embedding(text: str, dimension: int = DEFAULT_EMBEDDING_DIMENSION) -> list[float]:
    terms = extract_embedding_terms(text)
    vector = [0.0] * dimension
    if not terms:
        return vector

    for term in terms:
        digest = hashlib.sha256(term.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], byteorder="big") % dimension
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign

    return normalize_vector(vector)


def embedding_to_json(vector: list[float]) -> str:
    return json.dumps(vector, ensure_ascii=True, separators=(",", ":"))


def embedding_from_json(raw: str | None) -> list[float] | None:
    if not raw:
        return None

    try:
        values = json.loads(raw)
    except json.JSONDecodeError:
        return None

    if not isinstance(values, list):
        return None

    return [float(value) for value in values if isinstance(value, int | float)]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0

    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0

    return dot / (left_norm * right_norm)


def similarity_to_score(similarity: float) -> int:
    normalized = max(0.0, min(1.0, similarity))
    return round(normalized * 100)


def normalize_vector(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector

    return [value / norm for value in vector]


def extract_embedding_terms(text: str) -> set[str]:
    normalized = normalize_text(text)
    terms = {term for term in re.split(r"\s+", normalized) if term}

    compact = "".join(normalized.split())
    terms.update(char_ngrams(compact, 1))
    terms.update(char_ngrams(compact, 2))
    terms.update(char_ngrams(compact, 3))
    return terms


def normalize_text(text: str) -> str:
    separators = " \n\t\r,.;:!?，。！？；：、（）()[]{}<>\"'“”‘’"
    normalized = text.lower()
    for separator in separators:
        normalized = normalized.replace(separator, " ")

    return normalized


def char_ngrams(text: str, size: int) -> set[str]:
    if size <= 0 or len(text) < size:
        return set()

    return {text[index : index + size] for index in range(len(text) - size + 1)}
