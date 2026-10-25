"""``search("Li-P-S", is_stable=True)``: Materials Project materials, as a short list to pick from."""
from __future__ import annotations

import re
from dataclasses import dataclass

from . import client

FIELDS = ["material_id", "formula_pretty", "nsites", "energy_above_hull", "band_gap", "symmetry", "is_stable",
          "theoretical"]
_ID = re.compile(r"^(mp|mvc)-\d+$", re.I)


@dataclass
class Hit:
    material_id: str
    formula: str = ""
    nsites: int | None = None
    energy_above_hull: float | None = None   # eV/atom
    band_gap: float | None = None            # eV
    spacegroup: str = ""
    theoretical: bool | None = None

    @property
    def uri(self) -> str:
        """The path that opens it: ``load(hit.uri)``; add ``/bands``, ``/dos``, ... for more."""
        return f"mp:{self.material_id}"

    def as_dict(self) -> dict:
        return {"uri": self.uri, "material_id": self.material_id, "formula": self.formula, "nsites": self.nsites,
                "energy_above_hull": self.energy_above_hull, "band_gap": self.band_gap,
                "spacegroup": self.spacegroup, "theoretical": self.theoretical}


class Results(list):
    def __init__(self, hits=(), criteria=None):
        super().__init__(hits)
        self.criteria = criteria or {}

    def __repr__(self) -> str:
        head = f"{len(self)} materials ({', '.join(f'{k}={v}' for k, v in self.criteria.items())})"
        rows = [f"  {h.uri:<16} {h.formula:<14} {h.spacegroup:<10} "
                f"E_hull {'' if h.energy_above_hull is None else f'{h.energy_above_hull:.3f}':>6}  "
                f"gap {'' if h.band_gap is None else f'{h.band_gap:.2f}':>5}" for h in self]
        return "\n".join([head, *rows])


def criteria(query: str) -> dict:
    """Search box text -> ``summary.search`` arguments: ``mp-149`` (ids, comma separated), a
    formula (``LiFePO4``, also ``ABO3`` or ``Si*``), a chemical system (``Li-P-S``) or
    elements the material contains (``Li P S``)."""
    text = (query or "").strip()
    if not text:
        raise ValueError("type a formula (LiFePO4), a chemical system (Li-P-S), elements (Li P S) or an id (mp-149)")
    parts = [p for p in re.split(r"[\s,]+", text) if p]
    if all(_ID.match(p) for p in parts):
        return {"material_ids": [p.lower() for p in parts]}
    if len(parts) > 1:
        return {"elements": parts}
    if "-" in text:
        return {"chemsys": text}
    return {"formula": text}


def _get(doc, name):
    return doc.get(name) if isinstance(doc, dict) else getattr(doc, name, None)


def hit(doc) -> Hit:
    sym = _get(doc, "symmetry")
    sg = (_get(sym, "symbol") if sym is not None else "") or ""
    e = _get(doc, "energy_above_hull")
    g = _get(doc, "band_gap")
    return Hit(str(_get(doc, "material_id")), _get(doc, "formula_pretty") or "", _get(doc, "nsites"),
               None if e is None else float(e), None if g is None else float(g), str(sg), _get(doc, "theoretical"))


def search(query: str = "", limit: int | None = None, **filters) -> Results:
    """Materials Project materials matching ``query`` (see :func:`criteria`) and any other
    ``summary.search`` argument (``is_stable=True``, ``energy_above_hull=(0, 0.05)``,
    ``band_gap=(1, 3)``, ...), most stable first. Open one with ``load(hit.uri)``."""
    crit = {**(criteria(query) if query else {}), **filters}
    if not crit:
        criteria("")      # says what to type
    limit = limit or client.page_size()

    def run(mpr):
        return mpr.materials.summary.search(**crit, fields=FIELDS, num_chunks=1, chunk_size=min(limit, 1000))

    hits = sorted((hit(d) for d in client.call(run)),
                  key=lambda h: (h.energy_above_hull is None, h.energy_above_hull or 0.0, h.material_id))
    return Results(hits[:limit], crit)
