"""Test-only defaults; production defaults are intentionally fail-closed."""
import os

os.environ.setdefault("AGENT_AUTH_MODE", "development")
os.environ.setdefault("APP_ENV", "test")
