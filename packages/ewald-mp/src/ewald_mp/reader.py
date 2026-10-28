"""The ``mp:`` reader: ``load("mp:mp-149")``, ``load("mp:mp-149/bands")``, ...

``mp:ID[/WHAT]`` with ``WHAT`` one of :data:`VIEWS`:

``structure`` (default)  the final structure, one frame (``conventional=True`` for the
                         conventional standard cell)
``initial``              the structures the material's calculations started from, one frame each
``bands``, ``dos``       the structure with an ``ElectronicStructure`` (tables "Bands" / "DOS",
                         ``electronic`` both), as EWALD's VASP readers give it
``chgcar``               the structure with the charge density grid (and magnetization)
``relax``                the relaxation trajectory, one frame per ionic step with forces and energy;
                         ``task=`` picks the task, else the material's structure optimization
                         (r2SCAN, then GGA+U, then GGA); needs mp-api (``ewald-mp[full]``)
"""
from __future__ import annotations

from ewald.io.base import FrameReader

from . import client
from . import convert as C

VIEWS = ("structure", "initial", "bands", "dos", "electronic", "chgcar", "relax")
_RELAX_ORDER = ("r2SCAN", "GGA+U", "GGA")


def parse(path: str) -> tuple[str, str]:
    """``mp:mp-149/bands`` -> ``("mp-149", "bands")``. An address, split on "/" on every platform."""
    if not path.lower().startswith("mp:"):
        raise ValueError(f"not an mp: path: {path!r}")
    mid, _, what = path[3:].strip("/").partition("/")
    mid, what = mid.strip().lower(), (what.strip().lower() or "structure")
    if not mid:
        raise ValueError("mp: needs a Materials Project id, e.g. mp:mp-149")
    if mid.isdigit():
        mid = f"mp-{mid}"
    if what not in VIEWS:
        raise ValueError(f"{path!r}: unknown view {what!r}; one of {', '.join(VIEWS)}")
    return mid, what


def relax_task(mpr, material_id: str, run_type: str | None = None) -> str:
    """The task id of the material's structure optimization (``run_type`` first if given)."""
    docs = mpr.materials.search(material_ids=[material_id], fields=["calc_types"])
    if not docs:
        raise ValueError(f"the Materials Project has no material {material_id}")
    doc = docs[0]
    calc_types = doc["calc_types"] if isinstance(doc, dict) else getattr(doc, "calc_types", None)
    relax = {t: str(getattr(c, "value", c)) for t, c in (calc_types or {}).items() if "Structure Optimization" in str(getattr(c, "value", c))}
    if not relax:
        raise ValueError(f"{material_id} has no structure optimization task")
    order = ((run_type,) if run_type else ()) + _RELAX_ORDER
    for rt in order:
        hits = sorted(t for t, c in relax.items() if c.split(" Structure")[0] == rt)
        if hits:
            return hits[-1]
    return sorted(relax)[-1]


class MPReader(FrameReader):
    """Materials Project data by material id (your API key): ``mp:mp-149`` the
    structure, ``mp:mp-149/bands``, ``/dos``, ``/electronic``, ``/chgcar``, ``/relax``,
    ``/initial``. Every frame carries ``attributes["Materials Project"]`` (id, view, task).
    Read once and kept in memory; read-only."""

    schemes = ("mp",)
    description = ("Materials Project by id with your API key (mp:mp-149, mp:mp-149/bands, /dos, /chgcar, "
                   "/relax): structures, band structures, DOS, charge densities, relaxation trajectories")

    def __init__(self, path, conventional: bool = False, task: str | None = None, run_type: str | None = None):
        self.path = str(path)
        self.conventional, self.task, self.run_type = conventional, task, run_type
        self.material_id, self.what = parse(self.path)
        self._frames = client.call(self._fetch)
        if not self._frames:
            raise ValueError(f"{self.path}: nothing to show")

    def _fetch(self, mpr) -> list:
        mid, what = self.material_id, self.what
        info = {"material_id": mid, "view": what, "uri": self.path}
        if what in ("structure", "bands", "dos", "electronic", "initial"):
            got = mpr.get_structure_by_material_id(mid, final=what != "initial",
                                                   conventional_unit_cell=self.conventional)
            frames = [C.structure(s) for s in (got if isinstance(got, list) else [got])]
        if what in ("bands", "dos", "electronic"):
            from ewald.electronic import ElectronicStructure

            data = frames[0]
            es = ElectronicStructure(types=list(data.types), source=f"Materials Project {mid}")
            if what in ("bands", "electronic"):
                bs = mpr.get_bandstructure_by_material_id(mid)
                if bs is None:
                    raise ValueError(f"the Materials Project has no band structure for {mid}")
                C.bands(bs, es)
                frames = [C.structure(bs.structure)] if getattr(bs, "structure", None) is not None else frames
            if what in ("dos", "electronic"):
                d = mpr.get_dos_by_material_id(mid)
                if d is None:
                    raise ValueError(f"the Materials Project has no density of states for {mid}")
                C.dos(d, es, frames[0].count)
            es.types = list(frames[0].types)
            frames = [es.attach(frames[0])]
        elif what == "chgcar":
            chg = mpr.get_charge_density_from_material_id(mid)
            if chg is None:
                raise ValueError(f"the Materials Project has no charge density for {mid}")
            frames = [C.charge_density(chg)]
        elif what == "relax":
            from .rest import FULL_HINT, NeedsMPApi, Rester

            if isinstance(mpr, Rester):
                raise NeedsMPApi(f"{self.path}: relaxation trajectories are only in MP's Delta tables, which "
                                 f"mp-api reads; {FULL_HINT}")
            task = self.task or relax_task(mpr, mid, self.run_type)
            info["task_id"] = task
            frames = C.trajectory(mpr.materials.tasks.get_trajectory(task))
        for f in frames:
            f.attributes["Materials Project"] = dict(info)
        return frames

    def __len__(self) -> int:
        return len(self._frames)

    def read(self, index: int):
        return self._frames[index]
