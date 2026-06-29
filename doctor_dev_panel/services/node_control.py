from __future__ import annotations

"""Node control-plane helpers for the panel.

This module is intentionally dependency-light. The next refactor step can move
`_read_node_api`, `_post_node_api`, and related functions from `app.py` here
without changing endpoint behavior.
"""

class NodeAPIError(RuntimeError):
    """Expected/clean node API failure shown to the UI without a traceback."""


