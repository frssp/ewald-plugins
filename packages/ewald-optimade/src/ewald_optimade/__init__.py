"""Moved into EWALD: OPTIMADE support is built in since 2026-10-28 (``ewald.optimade``).

This package is kept so that ``from ewald_optimade import search`` and
``import ewald_optimade.providers`` keep working; each name is the one in ``ewald.optimade``.
It registers nothing (EWALD's built-in group "optimade" has the reader, side bar, AI tool and
settings page), so it can be uninstalled: ``pip uninstall ewald-optimade``.
"""
import importlib
import sys

__version__ = "0.2.0"

try:
    _core = importlib.import_module("ewald.optimade")
except ImportError as exc:
    raise ImportError("ewald-optimade 0.2 needs an EWALD with OPTIMADE built in (after 0.2.0, 2026-10-28): "
                      "pip install -U ewald, or use ewald-optimade 0.1.0 with an older EWALD",
                      name=__name__) from exc

from ewald.optimade import *  # noqa: E402,F401,F403
from ewald.optimade import __all__  # noqa: E402,F401

for _name in ("client", "convert", "providers", "query", "reader", "search", "tools", "uri", "panel"):
    sys.modules[f"{__name__}.{_name}"] = importlib.import_module(f"ewald.optimade.{_name}")
