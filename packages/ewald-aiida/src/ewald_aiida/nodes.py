"""AiiDA nodes to EWALD frames. Read-only: nothing here stores or changes a node."""
from __future__ import annotations

import numpy as np

from ewald import Cell, DataCollection

from .uri import AiidaURI, load_profile, parse

VIEWS = ("trajectory", "phonons", "bands", "structures", "input")

_PER_ATOM = {"forces": "Force", "force": "Force", "velocities": "Velocity", "velocity": "Velocity",
             "charges": "Charge", "magnetic_moments": "Magnetic Moment"}
_SKIP = {"positions", "cells", "steps", "times", "symbols"}


# ----------------------------------------------------------------------- loading
def load(text_or_uri, profile: str | None = None):
    """The node an ``aiida:`` string names, after following its links."""
    uri = text_or_uri if isinstance(text_or_uri, AiidaURI) else parse(text_or_uri)
    load_profile(profile or uri.profile)
    from aiida import orm

    try:
        node = orm.load_node(uri.node)
    except Exception as exc:  # NotExistent, MultipleObjectsError
        raise LookupError(f"{uri}: {exc}") from exc
    for label in uri.links:
        node = follow(node, label)
    return node


def follow(node, label: str):
    """The output (or called process, or input) of ``node`` named ``label``. Nested output
    namespaces are written with ``/`` or AiiDA's ``__``."""
    label = label.replace("/", "__")
    for triple in _outgoing(node):
        if triple.link_label == label:
            return triple.node
    for child in node.called if _is_process(node) else []:
        if _call_label(child) == label:   # a step of a WorkChain / task of a WorkGraph
            return child
    for triple in node.base.links.get_incoming().all():
        if triple.link_label == label:
            return triple.node
    names = sorted({t.link_label for t in _outgoing(node)})
    raise LookupError(f"node {node.pk} has no output {label!r}" + (f"; outputs: {', '.join(names)}" if names else ""))


def _call_label(process) -> str:
    from aiida.common.links import LinkType

    calls = process.base.links.get_incoming(link_type=(LinkType.CALL_CALC, LinkType.CALL_WORK)).all()
    return calls[0].link_label if calls else ""


def _outgoing(node):
    from aiida.common.links import LinkType

    if _is_process(node):
        return node.base.links.get_outgoing(link_type=(LinkType.CREATE, LinkType.RETURN)).all()
    return []


def _is_process(node) -> bool:
    from aiida import orm

    return isinstance(node, orm.ProcessNode)


def _type(node, name: str) -> bool:
    """isinstance against an orm class, or a plugin data class by its entry-point suffix
    (``phonopy.phonopy`` for aiida-phonopy's PhonopyData) without importing the plugin."""
    from aiida import orm

    cls = getattr(orm, name, None)
    if cls is not None:
        return isinstance(node, cls)
    return node.node_type.split(".")[-2:-1] == [name] or name in node.node_type


# ----------------------------------------------------------------------- info
def info(node, uri: str = "", **extra) -> dict:
    """``attributes["AiiDA"]``: what a frame came from."""
    out = {"pk": node.pk, "uuid": node.uuid, "node_type": node.node_type, "label": node.label}
    if _is_process(node):
        out.update(process_label=node.process_label, process_state=_value(node.process_state),
                   exit_status=node.exit_status)
    if uri:
        out["uri"] = uri
    out.update({k: v for k, v in extra.items() if v is not None})
    return out


def _value(state):
    return getattr(state, "value", state)


def scalars(node) -> dict:
    """Plain numbers (and short strings) from the ``Dict`` outputs of a process, flat."""
    out = {}
    if not _is_process(node):
        return out
    from aiida import orm

    for triple in _outgoing(node):
        if isinstance(triple.node, orm.Dict):
            for key, value in triple.node.get_dict().items():
                if isinstance(value, (bool, int, float)) and not isinstance(value, bool):
                    out[key] = float(value) if isinstance(value, float) else value
        elif isinstance(triple.node, (orm.Float, orm.Int)):
            out[triple.link_label] = triple.node.value
    return out


# ----------------------------------------------------------------------- data nodes
def structure_frame(node) -> DataCollection:
    """One frame from a ``StructureData``."""
    sites = node.sites
    kinds = {k.name: k for k in node.kinds}
    symbols = [_symbol(kinds[s.kind_name]) for s in sites]
    positions = np.array([s.position for s in sites], float).reshape(-1, 3)
    data = DataCollection(positions, symbols, Cell(np.array(node.cell, float), pbc=np.array(node.pbc, bool)))
    if any(kinds[s.kind_name].name != _symbol(kinds[s.kind_name]) for s in sites):
        data.particles["Kind"] = np.array([s.kind_name for s in sites])  # Fe1/Fe2 magnetic kinds
    return data


def _symbol(kind) -> str:
    return kind.symbol if kind.is_alloy is False and not kind.has_vacancies else kind.symbols[int(np.argmax(kind.weights))]


class Trajectory:
    """The arrays of a ``TrajectoryData``, read once; :meth:`frame` builds frame ``i``."""

    def __init__(self, node):
        self.node = node
        names = set(node.get_arraynames())
        self.positions = node.get_positions()
        self.symbols = list(node.symbols)
        self.cells = node.get_cells() if "cells" in names else None
        self.steps = node.get_stepids() if "steps" in names else np.arange(len(self.positions))
        self.times = node.get_times() if "times" in names else None
        pbc = node.base.attributes.get("pbc", None)
        self.pbc = np.array(pbc, bool) if pbc is not None else np.array([self.cells is not None] * 3)
        self.per_atom, self.per_step = {}, {}
        n, natoms = self.positions.shape[:2]
        for name in sorted(names - _SKIP):
            a = node.get_array(name)
            if a.ndim >= 2 and a.shape[:2] == (n, natoms):
                self.per_atom[_PER_ATOM.get(name.lower(), name)] = a
            elif a.ndim == 1 and len(a) == n:
                self.per_step[name] = a

    def __len__(self) -> int:
        return len(self.positions)

    def frame(self, i: int) -> DataCollection:
        cell = Cell(self.cells[i], pbc=self.pbc) if self.cells is not None else Cell(pbc=self.pbc)
        data = DataCollection(self.positions[i], self.symbols, cell)
        for name, a in self.per_atom.items():
            data.particles[name] = a[i]
        data.attributes["Timestep"] = int(self.steps[i])
        if self.times is not None:
            data.attributes["Time"] = float(self.times[i])
        for name, a in self.per_step.items():
            data.attributes[name] = a[i].item()
        return data


def electronic_bands(bands, structure=None, efermi: float | None = None):
    """``ewald.electronic.ElectronicStructure`` from an electronic ``BandsData`` (eV)."""
    from ewald.electronic import ElectronicStructure, pretty_label

    e = np.asarray(bands.get_bands(), float)
    e = e[None] if e.ndim == 2 else e                         # (nspin, nk, nb)
    kpts = np.asarray(bands.get_kpoints(), float)
    try:
        cart = np.asarray(bands.get_kpoints(cartesian=True), float) / (2 * np.pi)
    except Exception:  # no cell on the node
        cart = kpts
    step = np.linalg.norm(np.diff(cart, axis=0), axis=1)
    labels = list(bands.labels or [])
    breaks = [b for (a, _), (b, _) in zip(labels, labels[1:]) if b == a + 1]  # two labels side by side
    for b in breaks:
        step[b - 1] = 0.0                                     # a jump in the path is not distance
    dist = np.concatenate([[0.0], np.cumsum(step)])
    occ = bands.get_array("occupations") if "occupations" in bands.get_arraynames() else None
    types = np.array([] if structure is None else structure_frame(structure).types)
    es = ElectronicStructure(types, efermi=float(efermi or 0.0), kpoints=kpts, eigenvalues=e,
                             occupations=None if occ is None else np.asarray(occ, float).reshape(e.shape),
                             distances=dist, ticks=[(float(dist[i]), pretty_label(l)) for i, l in labels],
                             breaks=breaks, source=f"AiiDA BandsData {bands.pk}")
    return es


def is_phonon_bands(bands) -> bool:
    units = (bands.base.attributes.get("units", "") or "").lower()
    return units in ("thz", "cm-1", "cm^-1", "mev") or "phonon" in (bands.label or "").lower()


# ----------------------------------------------------------------------- processes
def descendants(process) -> list:
    """Every process ``process`` called, depth first, in the order they were created."""
    out = []
    for child in sorted(process.called, key=lambda n: (n.ctime, n.pk)):
        out.append(child)
        out += descendants(child)
    return out


def outputs_of(process, cls_name: str) -> list:
    return [t for t in _outgoing(process) if _type(t.node, cls_name)]


def find_view(node, what: str | None = None) -> tuple[str, list]:
    """``(view, items)`` for ``node``: the first of :data:`VIEWS` it has, or ``what``.

    ``items`` are ``(label, node, source_process)`` triples. A trajectory is the node's own
    ``TrajectoryData`` output, else those of the processes it called, in call order (one
    relaxation restarted three times reads as one trajectory).
    """
    from aiida import orm

    if what is not None and what not in VIEWS:
        raise ValueError(f"what= must be one of {', '.join(VIEWS)}")
    if not _is_process(node):
        for view, cls in (("trajectory", "TrajectoryData"), ("structures", "StructureData"),
                          ("bands", "BandsData")):
            if isinstance(node, getattr(orm, cls)) and what in (None, view):
                if view == "bands" and is_phonon_bands(node):
                    view = "phonons"
                return view, [("", node, None)]
        if _is_phonopy(node) and what in (None, "phonons"):
            return "phonons", [("", node, None)]
        raise ValueError(f"node {node.pk} is a {type(node).__name__}; ewald-aiida opens structures, "
                         "trajectories, bands, phonopy data and the processes that made them")
    procs = [node] + descendants(node)
    tried = VIEWS if what is None else (what,)
    for view in tried:
        items = []
        if view == "trajectory":
            own = outputs_of(node, "TrajectoryData")
            src = [(t.link_label, t.node, node) for t in own] or \
                  [(t.link_label, t.node, p) for p in procs[1:] for t in outputs_of(p, "TrajectoryData")]
            items = _unique(src)
        elif view == "phonons":
            items = _unique([(t.link_label, t.node, p) for p in procs for t in _outgoing(p)
                             if _is_phonopy(t.node)])
        elif view == "bands":
            items = _unique([(t.link_label, t.node, p) for p in procs for t in outputs_of(p, "BandsData")
                             if not is_phonon_bands(t.node)])[-1:]
        elif view == "structures":
            own = outputs_of(node, "StructureData")
            src = [(t.link_label, t.node, node) for t in own] or \
                  [(t.link_label, t.node, p) for p in procs[1:] for t in outputs_of(p, "StructureData")]
            items = _unique(src)
        elif view == "input":
            items = [(t.link_label, t.node, node) for t in node.base.links.get_incoming().all()
                     if isinstance(t.node, orm.StructureData)][:1]
        if items:
            return view, items
    raise LookupError(f"process {node.pk} ({node.process_label}) has no {what or 'structure, trajectory, bands '
                                                                         'or phonon'} output")


def _is_phonopy(node) -> bool:
    t = node.node_type
    return "phonopy" in t and ("PhonopyData" in t or "ForceConstantsData" in t)


def _unique(items):
    seen, out = set(), []
    for label, node, src in items:
        if node.pk not in seen:
            seen.add(node.pk)
            out.append((label, node, src))
    return out


def structure_of(node):
    """The structure a bands/phonon result belongs to: an input or sibling output."""
    from aiida import orm

    proc = node if _is_process(node) else node.creator
    while proc is not None:
        for t in list(_outgoing(proc)) + proc.base.links.get_incoming().all():
            if isinstance(t.node, orm.StructureData):
                return t.node
        proc = proc.caller
    return None


def resolve(text, what: str | None = None, profile: str | None = None):
    """``(node, view, items)`` for an ``aiida:`` string (see :func:`find_view`)."""
    node = load(text, profile)
    view, items = find_view(node, what)
    return node, view, items
