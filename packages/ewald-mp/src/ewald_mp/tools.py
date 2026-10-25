"""The AI's read-only Materials Project search (Ask AI, ``ewald ask``, the MCP server).

It lists materials and never sees the API key. To open one the AI writes a notebook cell
``pipe = load("mp:mp-149")`` (or ``mp:mp-149/bands``, ...), as for every other change.
"""
from __future__ import annotations

from ewald.plugins import ai_tool

from .search import search


@ai_tool(
    "mp_search",
    "Search the Materials Project (read-only; uses the user's API key, which you never see). query: a formula "
    "('LiFePO4', 'ABO3'), a chemical system ('Li-P-S'), elements a material contains ('Li P S') or ids "
    "('mp-149, mp-13'). Optional: is_stable, energy_above_hull [min, max] eV/atom, band_gap [min, max] eV. "
    "Returns uri, material_id, formula, nsites, energy_above_hull, band_gap, spacegroup, most stable first. "
    "To open one, write and run a notebook cell: pipe = load(\"<uri>\"); append /bands, /dos, /electronic, "
    "/chgcar or /relax (relaxation trajectory) for more.",
    {"type": "object", "required": ["query"], "properties": {
        "query": {"type": "string"},
        "is_stable": {"type": "boolean"},
        "energy_above_hull": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
        "band_gap": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
        "limit": {"type": "integer", "description": "at most this many (default 20, max 100)"}}})
def mp_search(toolset, query, is_stable=None, energy_above_hull=None, band_gap=None, limit=20):
    filters = {}
    if is_stable is not None:
        filters["is_stable"] = bool(is_stable)
    for name, value in (("energy_above_hull", energy_above_hull), ("band_gap", band_gap)):
        if value is not None:
            filters[name] = (float(value[0]), float(value[1]))
    res = search(query, limit=max(1, min(int(limit or 20), 100)), **filters)
    return {"criteria": {k: list(v) if isinstance(v, tuple) else v for k, v in res.criteria.items()},
            "hits": [h.as_dict() for h in res]}
