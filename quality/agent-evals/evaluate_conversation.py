"""Conversation behavior gate: bounded memory, ambiguity and fresh authorized facts.

Synthetic data only; CI uses hash retrieval and never calls an external model.
Transport/auth/provider streaming have separate service and localhost tests.
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/agent-service"))

from app import database  # noqa: E402
from app.architecture.orchestration import answer_agentic_question, answer_question  # noqa: E402
from app.auth import ActorPrincipal  # noqa: E402
from app.chat_metrics import infer_standard_outcome  # noqa: E402
from app.chat_service import execute_chat, prepare_chat  # noqa: E402
from app.models import ChatRequest  # noqa: E402
from app.rag import delete_document, ingest_document  # noqa: E402
from app.retrievers import clear_chunk_cache  # noqa: E402


def run_case(case: dict, index: int) -> bool:
    tenant, owner = f"conversation-eval-{index}", "alice"
    principal = ActorPrincipal(user_id=owner, tenant_id=tenant, role="operator", workspace_type="personal")
    doc_a = ingest_document("a.md", "客户A的项目延期原因是测试环境部署失败。客户A项目负责人是李四。", tenant_id=tenant, owner_id=owner)
    doc_b = ingest_document("b.md", "客户B的项目延期原因是审批进展缓慢。客户B项目负责人是王五。", tenant_id=tenant, owner_id="bob" if case.get("private_b") else owner)
    authorized = {doc_a.document_id} | ({doc_b.document_id} if not case.get("private_b") else set())
    if case.get("shared_parent"):
        delete_document(doc_a.document_id, tenant_id=tenant, owner_id=owner)
        delete_document(doc_b.document_id, tenant_id=tenant, owner_id=owner)
        shared_id = f"{tenant}-shared"
        database.insert_document(shared_id, "meeting.md", [
            ("项目进度", "客户A项目负责人是李四。"),
            ("项目进度", "客户B项目负责人是王五。"),
        ], tenant_id=tenant, owner_id=owner)
        authorized = {shared_id}
    questions = [case["questions"][0]] * (1 + case.get("warmup_turns", 0)) + case["questions"][1:]
    identifier = None
    for turn, question in enumerate(questions):
        if turn == len(questions) - 1 and case.get("before_last"):
            delete_document(doc_a.document_id, tenant_id=tenant, owner_id=owner)
            authorized.remove(doc_a.document_id)
            if case["before_last"] == "replace_a":
                changed = ingest_document("a-new.md", "客户A项目负责人是赵六。", tenant_id=tenant, owner_id=owner)
                authorized.add(changed.document_id)
        prepared = prepare_chat(ChatRequest(
            question=question, answer_mode="local", workflow_mode="standard", retriever_mode="hybrid",
            conversation_id=identifier, memory_mode=case["mode"],
        ), principal)
        response = execute_chat(prepared, metric_recorder=lambda **_: None,
                                agentic_handler=answer_agentic_question, standard_handler=answer_question)
        identifier = response.conversation_id
    decision = ("clarify" if response.agent_summary and response.agent_summary.execution_mode == "clarify"
                else "answered" if infer_standard_outcome(response) == "answered" else "refused")
    passed = (decision == case["decision"]
              and (not case.get("contains") or case["contains"] in response.answer)
              and (not case.get("excludes") or case["excludes"] not in response.answer)
              and (not case.get("follow_up_contains") or any(case["follow_up_contains"] in question for question in response.follow_up))
              and (not case.get("follow_up_excludes") or all(case["follow_up_excludes"] not in question for question in response.follow_up))
              and (not case.get("no_follow_up") or not response.follow_up)
              and len(response.follow_up) <= 3
              and all(source.document_id in authorized for source in response.sources))
    print(f"{'PASS' if passed else 'FAIL'} {case['id']}: decision={decision}, sources={len(response.sources)}")
    return passed


def main() -> int:
    cases = [json.loads(line) for line in (Path(__file__).parent / "golden/conversation_v1.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
        "AGENT_DATABASE_URL": "", "APP_ENV": "test", "LLM_ROUTER_ENABLED": "0",
    }), patch("app.database.DB_PATH", Path(directory) / "conversation.sqlite3"), patch("app.embeddings.REAL_EMBEDDING_MODEL", ""), patch("app.embeddings.RERANKER_MODEL", ""):
        clear_chunk_cache()
        try:
            results = [run_case(case, index) for index, case in enumerate(cases)]
        finally:
            clear_chunk_cache()
    print(f"Conversation V1: {sum(results)}/{len(results)}, quality_gate={'passed' if all(results) else 'failed'}")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
