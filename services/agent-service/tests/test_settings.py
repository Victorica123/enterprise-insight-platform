import os
import unittest
from unittest.mock import patch

from app.config import get_call_limits, get_llm_settings, get_settings
from app.model_egress import is_model_egress_allowed


class SettingsTests(unittest.TestCase):
    def test_retrieval_thresholds_deadlines_and_capacity_are_validated(self):
        with patch.dict(os.environ, {"HYBRID_KEYWORD_MIN_RATIO": "0.5", "HYBRID_HASH_MIN_SCORE": "12", "HYBRID_CHANNEL_WORKERS": "2"}):
            settings = get_settings()
            settings.validate()
            self.assertEqual(settings.hybrid_retrieval.keyword_min_ratio, 0.5)
            self.assertEqual(settings.hybrid_retrieval.hash_min_score, 12)
            self.assertEqual(settings.hybrid_retrieval.channel_workers, 2)
        for name, value in {"HYBRID_KEYWORD_MIN_RATIO": "1.1", "HYBRID_SEMANTIC_MIN_SCORE": "101",
                            "HYBRID_HASH_MIN_SCORE": "-1", "HYBRID_CHANNEL_TIMEOUT_SECONDS": "NaN",
                            "HYBRID_RERANK_TIMEOUT_SECONDS": "0", "HYBRID_CHANNEL_WORKERS": "0"}.items():
            with self.subTest(name=name), patch.dict(os.environ, {name: value}):
                with self.assertRaisesRegex(RuntimeError, name):
                    get_settings().validate()

    def test_environment_override_refreshes_settings_without_changing_the_model(self):
        with patch.dict(os.environ, {"DEEPSEEK_MODEL": "same-model", "LLM_PROVIDER": "deepseek", "AGENT_MAX_MODEL_CALLS": "3"}):
            first = get_settings()
            self.assertIs(first, get_settings())
            self.assertEqual(get_llm_settings().model, "same-model")
            self.assertEqual(get_call_limits().max_model_calls, 3)
            with patch.dict(os.environ, {"AGENT_MAX_MODEL_CALLS": "5"}):
                self.assertEqual(get_call_limits().max_model_calls, 5)
                self.assertEqual(get_llm_settings().model, "same-model")
            self.assertIs(first, get_settings())

    def test_startup_rejects_invalid_sizes_and_nonfinite_timeouts_without_secrets(self):
        with patch.dict(os.environ, {"AGENT_WORKERS": "0", "LLM_TIMEOUT_SECONDS": "NaN", "DEEPSEEK_API_KEY": "private-value", "SHARED_JWT_SECRET": "private-secret", "AGENT_DATABASE_URL": "mysql://user:password@localhost/db"}):
            settings = get_settings()
            with self.assertRaises(RuntimeError) as raised:
                settings.validate()
            self.assertIn("AGENT_WORKERS", str(raised.exception))
            self.assertIn("LLM_TIMEOUT_SECONDS", str(raised.exception))
            for secret in ("private-value", "private-secret", "password"):
                self.assertNotIn(secret, str(raised.exception))
                self.assertNotIn(secret, repr(settings))

    def test_production_egress_remains_allowlisted(self):
        with patch.dict(os.environ, {"APP_ENV": "production", "MODEL_EGRESS_POLICY": "allow", "MODEL_EGRESS_ALLOWED_TENANTS": "tenant-a"}):
            self.assertTrue(is_model_egress_allowed("tenant-a"))
            self.assertFalse(is_model_egress_allowed("tenant-b"))
            self.assertFalse(is_model_egress_allowed(None))

    def test_unknown_database_scheme_does_not_silently_select_sqlite(self):
        with patch.dict(os.environ, {"AGENT_DATABASE_URL": "postgres://private@localhost/db"}):
            with self.assertRaisesRegex(RuntimeError, "AGENT_DATABASE_URL"):
                get_settings().validate()
