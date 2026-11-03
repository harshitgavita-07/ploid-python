"""Response models.

Responses are wrapped in :class:`PloidObject`, a dict subclass with
attribute access that recurses into nested objects and lists. It never
validates against a fixed schema, so additive API changes (new fields)
keep working without an SDK upgrade.
"""
from __future__ import annotations

from typing import Any, Iterator


class PloidObject(dict):
    """A dict with attribute access, recursively wrapping JSON values."""

    _http_status: int = 200

    def __init__(self, data: Any = None, *, _status: int = 200) -> None:
        super().__init__()
        object.__setattr__(self, "_http_status", _status)
        for key, value in (data or {}).items():
            self[key] = self._wrap(value)

    @classmethod
    def _wrap(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return cls(value)
        if isinstance(value, list):
            return [cls._wrap(v) for v in value]
        return value

    # Payload keys shadow dict methods (e.g. a response field named "items"
    # wins over dict.items) - API payloads, not method names, are the common
    # case. Use ["items"] style access if you ever need a shadowed method.
    _RESERVED = frozenset({"to_dict", "http_status", "_wrap"})

    def __getattribute__(self, name: str) -> Any:
        if name.startswith("_") or name in PloidObject._RESERVED:
            return object.__getattribute__(self, name)
        try:
            return dict.__getitem__(self, name)
        except KeyError:
            return object.__getattribute__(self, name)

    def __getattr__(self, name: str) -> Any:
        raise AttributeError(name)

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = self._wrap(value)

    @property
    def http_status(self) -> int:
        """The HTTP status of the response that produced this object."""
        return self._http_status

    def to_dict(self) -> dict:
        """Deep plain-dict copy (nested PloidObjects unwrapped)."""
        def unwrap(v: Any) -> Any:
            if isinstance(v, PloidObject):
                return {k: unwrap(x) for k, x in v.items()}
            if isinstance(v, list):
                return [unwrap(x) for x in v]
            return v
        return {k: unwrap(v) for k, v in self.items()}

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        keys = ", ".join(list(self.keys())[:6])
        more = ", ..." if len(self) > 6 else ""
        return f"PloidObject({keys}{more})"


def page_items(page: Any) -> Iterator[Any]:
    """Yield items from a list page regardless of the envelope key used."""
    if isinstance(page, dict):
        for key in ("items", "rows", "monitors", "runs", "results", "data"):
            if isinstance(page.get(key), list):
                yield from page[key]
                return
    if isinstance(page, list):
        yield from page


def next_cursor(page: Any) -> Any:
    if isinstance(page, dict):
        return page.get("next_cursor") or page.get("nextCursor")
    return None
