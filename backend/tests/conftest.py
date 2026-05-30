"""Shared test configuration.

F3 (external Crossref/OpenAlex calls) is disabled for the whole suite by default
so tests never touch the network. The dedicated F3 tests inject a respx-mocked
client directly into ``verify_reference``.
"""

from __future__ import annotations

import os

os.environ.setdefault("F3_ENABLED", "false")
os.environ.setdefault("CROSSREF_POLITE_EMAIL", "test@example.com")
os.environ.setdefault("LLM_PROVIDER", "none")

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()
