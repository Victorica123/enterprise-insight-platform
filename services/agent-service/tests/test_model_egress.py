import os
import unittest
from unittest.mock import patch

from app.model_egress import (
    ModelEgressDenied,
    bind_model_egress_tenant,
    is_model_egress_allowed,
    require_model_egress_allowed,
    reset_model_egress_tenant,
)


class ModelEgressPolicyTests(unittest.TestCase):
    def test_production_is_deny_by_default_even_with_global_allow(self):
        with patch.dict(
            os.environ,
            {"APP_ENV": "production", "MODEL_EGRESS_POLICY": "allow", "MODEL_EGRESS_ALLOWED_TENANTS": ""},
        ):
            self.assertFalse(is_model_egress_allowed("tenant-a"))

    def test_production_allows_only_named_tenant(self):
        with patch.dict(
            os.environ,
            {"APP_ENV": "production", "MODEL_EGRESS_ALLOWED_TENANTS": "tenant-a,tenant-b"},
        ):
            self.assertTrue(is_model_egress_allowed("tenant-a"))
            self.assertFalse(is_model_egress_allowed("tenant-c"))

    def test_bound_context_is_required_by_llm_call_gate(self):
        with patch.dict(
            os.environ,
            {"APP_ENV": "production", "MODEL_EGRESS_ALLOWED_TENANTS": "tenant-a"},
        ):
            token = bind_model_egress_tenant("tenant-c")
            try:
                with self.assertRaises(ModelEgressDenied):
                    require_model_egress_allowed()
            finally:
                reset_model_egress_tenant(token)


if __name__ == "__main__":
    unittest.main()
