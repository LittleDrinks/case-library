"""Database counter compatibility exports."""

from backend.db import counters as _legacy

globals().update(
    {name: getattr(_legacy, name) for name in dir(_legacy) if not name.startswith("__")}
)

__all__ = [name for name in globals() if not name.startswith("__") and name != "_legacy"]
