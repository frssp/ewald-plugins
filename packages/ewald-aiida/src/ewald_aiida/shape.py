"""What each step of a workflow computed, read from its inputs, not from its name.

A step's ``inputs`` (:func:`ewald_aiida.export.calc_inputs`: the code's parameters, k-points,
structure and parents) give it one ``kind`` and a few ``flags``, so analyses can find "the
slab statics with a planar average" or "the bulk statics at several volumes" in any workflow,
whoever built it and whatever its steps are called. The rules read VASP INCAR tags (IBRION, NSW,
ISIF, ICHARG, LVHAR, NELECT); a step of another code gets kind ``""`` and no flags.

VASP tag meanings: https://www.vasp.at/wiki/index.php/IBRION, .../ICHARG, .../LVHAR.
"""
from __future__ import annotations

#: kinds in the order the rules try them
KINDS = ("md", "phonon", "relax", "bands", "dos", "static")


def _int(params: dict, tag: str, default=None):
    value = params.get(tag, params.get(tag.lower(), default))
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _true(params: dict, tag: str) -> bool:
    value = params.get(tag, params.get(tag.lower()))
    return value is True or str(value).strip(".").upper() in ("TRUE", "T")


def kind(inputs: dict) -> str:
    """``md``, ``phonon``, ``relax``, ``bands``, ``dos`` or ``static`` for a VASP step; ``""``
    when the step has no INCAR-like parameters."""
    params = inputs.get("parameters")
    if not isinstance(params, dict) or not any(str(k).upper() in ("IBRION", "NSW", "ENCUT", "ISMEAR", "EDIFF",
                                                                   "ICHARG", "PREC", "ALGO") for k in params):
        return ""
    ibrion, nsw = _int(params, "IBRION", -1), _int(params, "NSW", 0)
    if ibrion == 0 and nsw > 0:
        return "md"
    if ibrion in (5, 6, 7, 8):
        return "phonon"
    if nsw > 0 and ibrion in (1, 2, 3):
        return "relax"
    if _int(params, "ICHARG") == 11:
        return "bands" if "path" in (inputs.get("kpoints") or {}) else "dos"
    return "static"


def flags(inputs: dict, files=()) -> list:
    """``cell_relax`` (ISIF >= 3), ``slab`` (the structure has a vacuum gap), ``potential``
    (LVHAR, or a planar average among the files), ``charged`` (NELECT set) for a step."""
    params = inputs.get("parameters") if isinstance(inputs.get("parameters"), dict) else {}
    out = []
    if kind(inputs) == "relax" and (_int(params, "ISIF", 2) or 0) >= 3:
        out.append("cell_relax")
    if (inputs.get("structure") or {}).get("vacuum_axis") is not None:
        out.append("slab")
    if _true(params, "LVHAR") or _true(params, "LVTOT") or any("planar" in f for f in files):
        out.append("potential")
    if "NELECT" in params or "nelect" in params:
        out.append("charged")
    return out


def describe(inputs: dict, files=()) -> dict:
    """``{"kind", "flags", "formula", "sites", "volume"}`` of a step, for its side bar row and
    for analyses that look for steps by what they computed."""
    s = inputs.get("structure") or {}
    return {"kind": kind(inputs), "flags": flags(inputs, files), "formula": s.get("formula") or "",
            "sites": s.get("sites"), "volume": s.get("volume")}
