"""P0 加固回归测试：上传大小限制、上下文注入、SQLite WAL、按 provider 计费。

每个用例都对应一个已修复的风险项，防止后续改动悄悄回退：
- 上传无大小限制（内存 DoS）            -> 413 + 流式分块读取
- 图谱/工具上下文只拼接不进 prompt      -> API 模式进入 prompt，local 模式保留追加
- SQLite 无 WAL/busy_timeout             -> 多 worker 下 database is locked
- 成本单价不随 provider 切换             -> 成本面板错误
"""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.config import get_llm_pricing
from app.database import connect, init_db
from app.llm import LLMAnswer, build_user_prompt
from app.main import app
from app.models import Source
from app.rag import build_answer


def _make_sources() -> list[Source]:
    return [
        Source(
            document_id="d1",
            filename="a.md",
            chunk_index=0,
            score=10,
            content="项目负责人：李四。",
        )
    ]


class UploadLimitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_upload_over_limit_returns_413(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch(
            "app.database.DB_PATH", Path(tmp) / "upload.sqlite3"
        ), patch("app.routes.documents.MAX_UPLOAD_BYTES", 1024):
            response = self.client.post(
                "/documents",
                files={"file": ("big.txt", b"x" * 2048, "text/plain")},
                headers={"X-User-Role": "operator"},
            )
        self.assertEqual(response.status_code, 413)

    def test_upload_within_limit_succeeds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch(
            "app.database.DB_PATH", Path(tmp) / "upload.sqlite3"
        ), patch("app.routes.documents.MAX_UPLOAD_BYTES", 1024 * 1024):
            response = self.client.post(
                "/documents",
                files={"file": ("ok.txt", "客户:测试客户\n项目:测试项目".encode("utf-8"), "text/plain")},
                headers={"X-User-Role": "operator"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertIn("document_id", response.json())


class ContextInjectionTests(unittest.TestCase):
    def test_api_mode_passes_contexts_into_llm_prompt(self) -> None:
        """图谱/工具上下文必须进入 generate_answer 调用，而不是回答后拼接。"""
        fake = LLMAnswer(content="模型答案", prompt_tokens=12, completion_tokens=3)
        with patch("app.rag.generate_answer", return_value=fake) as mocked:
            answer, _trace, usage = build_answer(
                "项目负责人是谁？",
                _make_sources(),
                "api",
                ["【关系图谱】命中实体：客户A"],
            )
        mocked.assert_called_once_with("项目负责人是谁？", _make_sources(), ["【关系图谱】命中实体：客户A"])
        self.assertEqual(answer, "模型答案")
        self.assertNotIn("【关系图谱】", answer)
        self.assertEqual(usage.prompt_tokens, 12)
        self.assertEqual(usage.source, "api")

    def test_local_mode_appends_contexts(self) -> None:
        answer, _trace, _usage = build_answer(
            "项目负责人是谁？",
            _make_sources(),
            "local",
            ["【关系图谱】命中实体：客户A"],
        )
        self.assertTrue(answer.rstrip().endswith("【关系图谱】命中实体：客户A"))

    def test_user_prompt_contains_extra_context_section(self) -> None:
        prompt = build_user_prompt("项目负责人是谁？", _make_sources(), ["【关系图谱】命中实体：客户A"])
        self.assertIn("系统补充上下文", prompt)
        self.assertIn("【关系图谱】", prompt)
        plain = build_user_prompt("项目负责人是谁？", _make_sources(), None)
        self.assertNotIn("系统补充上下文", plain)


class SqliteHardeningTests(unittest.TestCase):
    def test_wal_and_busy_timeout_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "wal-test.sqlite3"
            with patch("app.database.DB_PATH", db_path):
                init_db()
                with connect() as conn:
                    journal_mode = conn.execute("pragma journal_mode").fetchone()[0]
                    busy_timeout = conn.execute("pragma busy_timeout").fetchone()[0]
        self.assertEqual(str(journal_mode).lower(), "wal")
        self.assertEqual(busy_timeout, 5000)


class PricingByProviderTests(unittest.TestCase):
    def test_openai_defaults(self) -> None:
        with patch.dict(
            os.environ,
            {
                "LLM_PROVIDER": "openai",
                "LLM_PROMPT_PRICE_PER_1M_USD": "",
                "LLM_COMPLETION_PRICE_PER_1M_USD": "",
            },
            clear=False,
        ):
            pricing = get_llm_pricing()
        self.assertEqual(pricing.prompt_per_1m_usd, 0.40)
        self.assertEqual(pricing.completion_per_1m_usd, 1.60)

    def test_deepseek_defaults(self) -> None:
        with patch.dict(
            os.environ,
            {
                "LLM_PROVIDER": "deepseek",
                "LLM_PROMPT_PRICE_PER_1M_USD": "",
                "LLM_COMPLETION_PRICE_PER_1M_USD": "",
            },
            clear=False,
        ):
            pricing = get_llm_pricing()
        self.assertEqual(pricing.prompt_per_1m_usd, 0.27)
        self.assertEqual(pricing.completion_per_1m_usd, 1.10)

    def test_env_override_wins(self) -> None:
        with patch.dict(
            os.environ,
            {
                "LLM_PROVIDER": "openai",
                "LLM_PROMPT_PRICE_PER_1M_USD": "0.123",
                "LLM_COMPLETION_PRICE_PER_1M_USD": "0.456",
            },
            clear=False,
        ):
            pricing = get_llm_pricing()
        self.assertEqual(pricing.prompt_per_1m_usd, 0.123)
        self.assertEqual(pricing.completion_per_1m_usd, 0.456)


if __name__ == "__main__":
    unittest.main()
