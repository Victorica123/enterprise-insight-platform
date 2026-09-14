from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

import update_knowledge  # noqa: E402


class PrimaryDependencyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.service = self.root / "services" / "agent-service"
        self.service.mkdir(parents=True)

    def test_primary_dependencies_include_extras_and_orchestration_framework(self) -> None:
        (self.service / "requirements.txt").write_text(
            "# Direct dependencies\n"
            "FastAPI==0.115.6\n"
            "uvicorn[standard] == 0.34.0\n"
            "pydantic==2.10.4 ; python_version >= '3.12'\n"
            "langgraph==1.2.11  # Orchestration\n"
            "openai==1.93.0\n",
            encoding="utf-8",
        )

        with patch.object(update_knowledge, "ROOT", self.root):
            self.assertEqual(
                update_knowledge.python_dependencies(),
                {"fastapi": "0.115.6", "uvicorn": "0.34.0", "pydantic": "2.10.4", "langgraph": "1.2.11"},
            )

    def test_pip_directives_do_not_expand_the_primary_dependency_snapshot(self) -> None:
        (self.service / "requirements.lock").write_text(
            "pydantic==2.10.4\nlangchain-core==1.6.3\n", encoding="utf-8"
        )
        (self.service / "optional.txt").write_text("pytest==9.0.0\n", encoding="utf-8")
        for directive in ("-c requirements.lock", "--constraint=requirements.lock", "-r optional.txt"):
            with self.subTest(directive=directive):
                (self.service / "requirements.txt").write_text(
                    f"{directive}\n\n# langgraph==1.2.11\nfastapi==0.115.6\n", encoding="utf-8"
                )
                with patch.object(update_knowledge, "ROOT", self.root):
                    self.assertEqual(update_knowledge.python_dependencies(), {"fastapi": "0.115.6"})


if __name__ == "__main__":
    unittest.main()
