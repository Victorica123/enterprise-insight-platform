from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

import knowledge_index  # noqa: E402


class KnowledgeIndexTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        (self.root / "knowledge").mkdir()
        (self.root / "knowledge" / "ARCHITECTURE.md").write_text(
            "# 身份架构\nJWT 由 Media Service 签发，tenant 与 owner 在查询阶段完成权限隔离。\n",
            encoding="utf-8",
        )
        (self.root / "knowledge" / "OPERATIONS.md").write_text(
            "# 运维\n本地发布支持 SQLite 备份、校验和恢复。\n",
            encoding="utf-8",
        )
        (self.root / "docs" / "archive").mkdir(parents=True)
        (self.root / "docs" / "archive" / "OLD.md").write_text(
            "# 旧方案\n历史文档不能进入当前维护索引。\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_incremental_build_reuses_unchanged_vectors(self) -> None:
        first, first_stats = knowledge_index.build_index(self.root)
        second, second_stats = knowledge_index.build_index(self.root, first)
        self.assertEqual(first, second)
        self.assertGreater(first_stats["computed"], 0)
        self.assertEqual(second_stats["computed"], 0)
        self.assertEqual(second_stats["reused"], len(second["chunks"]))
        self.assertNotIn("docs/archive/OLD.md", {source["path"] for source in second["sources"]})

    def test_semantic_query_routes_identity_to_architecture(self) -> None:
        index, _ = knowledge_index.build_index(self.root)
        encoded = index["chunks"][0]["vector_b64"]
        self.assertEqual(len(knowledge_index.decode_vector(encoded)), knowledge_index.EMBEDDING_DIMENSION)
        results = knowledge_index.search_index(index, "Workspace JWT 租户身份隔离", top_k=1)
        self.assertEqual(results[0]["path"], "knowledge/ARCHITECTURE.md")

        manifest = knowledge_index.source_manifest(self.root)
        current_revision = knowledge_index.corpus_revision(manifest)
        with patch.object(knowledge_index, "CHUNKING_ALGORITHM", "markdown-next-version"):
            self.assertNotEqual(current_revision, knowledge_index.corpus_revision(manifest))

    def test_query_cache_is_revision_aware(self) -> None:
        knowledge_index.update_index(self.root)
        cache_path = self.root / "query-cache.json"
        first, first_hit, first_revision = knowledge_index.query_index(
            self.root, "如何备份恢复", 2, cache_path
        )
        second, second_hit, second_revision = knowledge_index.query_index(
            self.root, "如何备份恢复", 2, cache_path
        )
        self.assertFalse(first_hit)
        self.assertTrue(second_hit)
        self.assertEqual(first, second)
        self.assertEqual(first_revision, second_revision)

        operations = self.root / "knowledge" / "OPERATIONS.md"
        operations.write_text(operations.read_text(encoding="utf-8") + "恢复前校验 SHA-256。\n", encoding="utf-8")
        knowledge_index.update_index(self.root)
        _, third_hit, third_revision = knowledge_index.query_index(
            self.root, "如何备份恢复", 2, cache_path
        )
        self.assertFalse(third_hit)
        self.assertNotEqual(first_revision, third_revision)


if __name__ == "__main__":
    unittest.main()
