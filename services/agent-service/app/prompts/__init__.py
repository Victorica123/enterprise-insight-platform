"""Prompt templates live as text files next to this module (optimisation plan 0.7).

``llm.py`` and ``llm_router.py`` only fill variables.  Templates use
``string.Template`` placeholders (``${name}``) so the JSON examples inside the
prompts stay literal.  Files are read once per process and cached;
``AGENT_PROMPT_DIR`` may point at a directory whose ``<name>.txt`` files
override the packaged defaults, so wording can be tuned per deployment without
rebuilding the image.  A missing placeholder raises at render time instead of
silently sending a half-filled prompt.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from string import Template

PROMPT_DIR = Path(__file__).resolve().parent
PROMPT_SUFFIX = ".txt"

# Placeholders each packaged template must declare; verified by tests/test_prompts.py.
PROMPT_CATALOG: dict[str, frozenset[str]] = {
    "answer_system": frozenset(),
    "answer_user": frozenset({"question", "evidence", "context_section"}),
    "answer_source_item": frozenset({"index", "source_type", "location", "video_lines", "content"}),
    "answer_context_section": frozenset({"blocks"}),
    "router_system": frozenset(),
    "router_user": frozenset({"question"}),
    "planner_system": frozenset(),
    "planner_user": frozenset({"question", "intent"}),
    "tool_selector_system": frozenset({"tools_json"}),
    "tool_selector_user": frozenset({"question"}),
}


def _candidate_paths(name: str) -> list[Path]:
    override_dir = os.getenv("AGENT_PROMPT_DIR", "").strip()
    candidates = [Path(override_dir) / f"{name}{PROMPT_SUFFIX}"] if override_dir else []
    candidates.append(PROMPT_DIR / f"{name}{PROMPT_SUFFIX}")
    return candidates


@lru_cache(maxsize=64)
def load_prompt(name: str) -> str:
    """Raw template text (trailing newline stripped); override directory wins."""
    for path in _candidate_paths(name):
        if path.is_file():
            return path.read_text(encoding="utf-8").rstrip("\r\n")
    raise FileNotFoundError(f"prompt template not found: {name}{PROMPT_SUFFIX}")


def render_prompt(name: str, **variables: object) -> str:
    return Template(load_prompt(name)).substitute(variables)


def prompt_placeholders(name: str) -> frozenset[str]:
    return frozenset(Template(load_prompt(name)).get_identifiers())


def list_packaged_prompts() -> list[str]:
    return sorted(path.stem for path in PROMPT_DIR.glob(f"*{PROMPT_SUFFIX}"))


def clear_prompt_cache() -> None:
    """Test / deployment hook after editing templates or changing the override dir."""
    load_prompt.cache_clear()


__all__ = [
    "PROMPT_CATALOG",
    "PROMPT_DIR",
    "clear_prompt_cache",
    "list_packaged_prompts",
    "load_prompt",
    "prompt_placeholders",
    "render_prompt",
]
