# Semantic project knowledge

Read this reference when changing project knowledge, retrieval, embedding, caching, or the maintainer Skill.

## Retrieval workflow

1. Keep product facts in human-maintained `knowledge/*.md`, ADRs and machine contracts.
2. Run the Skill wrapper with the concrete task. It locates the repository and calls `scripts/knowledge_index.py query`.
3. Treat returned path, heading and line range as routing metadata. Read the source file before making a decision.
4. If the index is missing or stale, run `python scripts/update_knowledge.py`; if mutation is not in scope, fall back to `knowledge/INDEX.md` and report the drift.
5. Do not paste `SEMANTIC_INDEX.json` vectors into prompts or edit the generated file.

## Index and cache contract

- Corpus: repository knowledge, ADRs, current docs, contracts, README, AGENTS and this Skill's textual references only.
- Exclusions: `docs/archive`, customer databases, media, runtime directories, secrets, logs and query text.
- Embedding: deterministic 192-dimensional hash n-gram + domain-topic features, stored as signed-int8 Base64. It is a routing embedding, not the business BGE model.
- Incremental key: chunk content fingerprint plus algorithm version and dimension.
- Query-cache key: corpus revision + SHA-256(normalized query) + Top-K + algorithm. The value contains only ranked source metadata and previews.
- Invalidation: any indexed source, index/chunking algorithm, embedding algorithm or dimension change produces a new corpus revision. Runtime cache is bounded and Git-ignored.

## KV cache boundary

Use precise names:

- content-addressed vector reuse avoids re-embedding unchanged knowledge chunks;
- revision-aware query cache avoids reranking an unchanged query/corpus pair;
- Agent chunk LRU avoids repeated SQLite row materialization for the same authorization scope and content revision;
- Agent embedding LRU avoids repeated BGE inference for the same model and text digest;
- approved business knowledge is customer-runtime data materialized only after governance; it must never be copied into the repository Skill index;
- attention KV cache belongs to the model runtime/provider. Do not claim it exists or is effective without provider metrics such as cached input tokens.

Keep stable instructions and schemas before dynamic Top-K evidence when constructing prompts. This is prefix-cache-friendly, but it is not proof of a model KV-cache hit.

## Verification

```powershell
python -m unittest discover -s scripts/tests -q
python scripts/update_knowledge.py
python scripts/update_knowledge.py --check
python scripts/knowledge_index.py query "Workspace JWT tenant isolation" --top-k 5
python <skill-creator>/scripts/quick_validate.py skills/enterprise-insight-maintainer
```

For changes to business embeddings, also run the Agent Service regression tests and the affected keyword/embedding/hybrid evaluation gates.
