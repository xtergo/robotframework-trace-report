"""Dataclass-to-dict conversion with enum and private-field handling."""

from __future__ import annotations

import dataclasses
from enum import Enum
from typing import Any


def serialize(obj: Any) -> Any:
    """Recursively convert *obj* to a JSON-safe structure.

    * :class:`~enum.Enum` → ``.value``
    * dataclass instance → ``dict`` (fields prefixed with ``_`` are excluded)
    * ``list`` → recursed
    * ``dict`` → recursed
    * everything else (``int``, ``float``, ``str``, ``bool``, ``None``) → as-is
    """
    if isinstance(obj, Enum):
        return obj.value
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {
            f.name: serialize(getattr(obj, f.name))
            for f in dataclasses.fields(obj)
            if not f.name.startswith("_")
        }
    if isinstance(obj, list):
        return [serialize(item) for item in obj]
    if isinstance(obj, dict):
        return {k: serialize(v) for k, v in obj.items()}
    return obj
