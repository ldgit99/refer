"""Multi-agent layer (research.md §7).

The deterministic specialist logic lives in app.citation / app.verifier / app.writers.
This package wraps them as a LangGraph StateGraph (graph.py) plus critics that
independently re-check specialist output. LangGraph is an optional dependency
(``pip install -e .[agents]``); graph.py imports it lazily so the core API works
without it.
"""
