"""Feature registry — decorator-based; loads modules from features/ on demand."""
from __future__ import annotations

import importlib
import pkgutil
from typing import Type

from . import __name__ as _features_pkg_name
from .base import Feature


_REGISTRY: dict[str, Type[Feature]] = {}


def register(cls: Type[Feature]) -> Type[Feature]:
    if not getattr(cls, "name", None):
        raise ValueError(f"Feature class {cls!r} missing class-var ``name``")
    _REGISTRY[cls.name] = cls
    return cls


def _autoload() -> None:
    """Import every module in features/ so decorators run."""
    pkg = importlib.import_module(_features_pkg_name)
    for mod in pkgutil.iter_modules(pkg.__path__):
        if mod.name in {"base", "registry"}:
            continue
        importlib.import_module(f"{_features_pkg_name}.{mod.name}")


def load(name: str) -> Feature:
    if not _REGISTRY:
        _autoload()
    if name not in _REGISTRY:
        _autoload()
    if name not in _REGISTRY:
        raise KeyError(f"unknown feature: {name!r} (registered: {sorted(_REGISTRY)})")
    return _REGISTRY[name]()


def all_names() -> list[str]:
    if not _REGISTRY:
        _autoload()
    return sorted(_REGISTRY)
