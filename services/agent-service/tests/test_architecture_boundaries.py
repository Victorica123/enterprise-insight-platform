import unittest
from unittest.mock import Mock

from app.architecture.context import RequestContext
from app.architecture.manifest import PANORAMA_LAYERS, panorama_manifest
from app.architecture.orchestration import ConversationInput, ConversationOrchestrator
from app.auth import ActorPrincipal
from app.models import ChatResponse
from app.retrievers import RetrievalScope


class ArchitectureBoundaryTests(unittest.TestCase):
    def test_panorama_manifest_describes_six_layers(self) -> None:
        manifest = panorama_manifest()
        self.assertEqual(
            [layer["key"] for layer in manifest],
            ["orchestration", "retrieval", "execution", "knowledge", "governance", "guardrails"],
        )
        self.assertEqual(len(manifest), len(PANORAMA_LAYERS))
        for layer in manifest:
            self.assertTrue(layer["title"])
            self.assertTrue(layer["responsibility"])
            self.assertTrue(layer["modules"])

    def test_request_context_preserves_signed_scope(self) -> None:
        principal = ActorPrincipal(
            user_id="user-7",
            tenant_id="tenant-9",
            role="operator",
            auth_mode="jwt",
            workspace_type="personal",
        )

        context = RequestContext.from_principal(principal)
        self.assertEqual(context.tenant_id, "tenant-9")
        self.assertEqual(context.owner_id, "user-7")
        self.assertEqual(context.actor_user, "user-7")
        self.assertEqual(context.retrieval_scope(["asset-1", "asset-1"]).asset_ids, ("asset-1",))

    def test_orchestrator_routes_standard_and_agentic_without_scope_leak(self) -> None:
        standard = Mock(return_value=ChatResponse(answer="standard", sources=[]))
        agentic = Mock(return_value=ChatResponse(answer="agentic", sources=[]))
        orchestrator = ConversationOrchestrator(
            standard_handler=standard,
            agentic_handler=agentic,
        )

        orchestrator.answer(ConversationInput(
            question="状态？",
            workflow_mode="standard",
            answer_mode="local",
            retriever_mode="keyword",
        ))
        standard.assert_called_once_with(
            "状态？", answer_mode="local", retriever_mode="keyword",
        )

        orchestrator.answer(ConversationInput(
            question="为什么延期？",
            workflow_mode="agentic",
            answer_mode="local",
            retriever_mode="hybrid",
            actor_role="viewer",
            actor_user="user-7",
            workspace_type="team",
            retrieval_scope=RetrievalScope(tenant_id="tenant-9"),
        ))
        agentic.assert_called_once_with(
            "为什么延期？",
            answer_mode="local",
            retriever_mode="hybrid",
            actor_role="viewer",
            actor_user="user-7",
            workspace_type="team",
            retrieval_scope=RetrievalScope(tenant_id="tenant-9"),
        )
