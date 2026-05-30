"""Vercel Python serverless entrypoint.

Exposes the FastAPI app so @vercel/python serves it as a single ASGI function.
The `app/` package sits one level up from this file; add it to sys.path so the
import works regardless of Vercel's working directory.
"""

from __future__ import annotations

import os
import sys

_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from app.main import app  # noqa: E402

# Vercel's Python runtime detects a module-level ASGI `app`.
__all__ = ["app"]
