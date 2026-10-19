"""The ``aiida:`` reader: ``load("aiida:1234")``."""
from __future__ import annotations

from ewald.io.base import FrameReader

from . import nodes


class AiidaReader(FrameReader):
    """AiiDA node by PK or UUID: ``aiida:[profile/]NODE[/link/...]`` (read-only).

    ``what`` picks the view of a process (``trajectory``, ``phonons``, ``bands``,
    ``structures``, ``input``); by default the first it has. ``frames`` is the number of
    frames in one period of an animated phonon mode.
    """

    schemes = ("aiida",)
    description = ("AiiDA node by PK/UUID (aiida:1234, aiida:profile/1234/link): structures, "
                   "trajectories, bands, aiida-phonopy results, workflows; read-only")

    def __init__(self, path, what: str | None = None, profile: str | None = None, frames: int = 24):
        self.path = str(path)
        self.what = what
        self.profile = profile
        self.node, self.view, self.items = nodes.resolve(self.path, what, profile)
        self.extra = nodes.scalars(self.node)
        self._inner = None
        self._index: list = []           # (item number, frame within item)
        self._trajs: dict = {}
        if self.view == "trajectory":
            for k, (_, node, _) in enumerate(self.items):
                self._trajs[k] = nodes.Trajectory(node)
                self._index += [(k, i) for i in range(len(self._trajs[k]))]
        elif self.view == "structures" or self.view == "input":
            self._index = [(k, 0) for k in range(len(self.items))]
        elif self.view == "bands":
            self._index = [(0, 0)]
        elif self.view == "phonons":
            self._inner = _phonon_reader(self.node, self.items, frames)
            self._index = [(0, i) for i in range(len(self._inner))]

    def __len__(self) -> int:
        return len(self._index)

    def read(self, index: int):
        k, i = self._index[index]
        label, node, source = self.items[k]
        if self.view == "trajectory":
            data = self._trajs[k].frame(i)
        elif self.view in ("structures", "input"):
            data = nodes.structure_frame(node)
        elif self.view == "bands":
            structure = nodes.structure_of(source or node)
            data = nodes.structure_frame(structure) if structure is not None else _empty()
            efermi = self.extra.get("fermi_energy")
            if efermi is None and source is not None:
                efermi = nodes.scalars(source).get("fermi_energy")
            nodes.electronic_bands(node, structure, efermi).attach(data)
        else:
            data = self._inner.read(i)
        for key, value in self.extra.items():
            data.attributes.setdefault(key, value)
        data.attributes["AiiDA"] = nodes.info(
            self.node, self.path, view=self.view, output=label or None, output_pk=node.pk,
            calc_pk=None if source is None or source.pk == self.node.pk else source.pk)
        return data


def _empty():
    from ewald import DataCollection

    return DataCollection([], [])


# ----------------------------------------------------------------------- phonons
def _phonon_reader(node, items, frames: int):
    """Phonon modes of an aiida-phonopy result through ewald-phonopy: the force constants
    become a ``phonopy.Phonopy``, whose band structure (along the path of the workflow's
    ``phonon_bands`` output, else seekpath's) is a looping trajectory."""
    try:
        from ewald_phonopy import reader_from_phonopy
    except ImportError as exc:
        raise ImportError("phonon modes need the ewald-phonopy plugin: pip install "
                          "'git+https://github.com/frssp/ewald-plugins#subdirectory=packages/ewald-phonopy'") from exc
    _, data, source = items[-1]
    top = node if nodes._is_process(node) else source
    phonon = phonopy_instance(data, top)
    path, labels = None, None
    bands = _phonon_bands(top)
    if bands is not None:
        path, labels = _bands_path(bands)
    return reader_from_phonopy(phonon, frames=frames, band_path=path, labels=labels,
                               source=f"AiiDA {data.__class__.__name__} {data.pk}")


def phonopy_instance(data, source=None):
    """``phonopy.Phonopy`` with force constants from aiida-phonopy nodes: ``PhonopyData``
    (+ a sibling ``force_constants`` output, or the forces of its supercells) or
    ``ForceConstantsData``."""
    try:
        phonon = data.get_phonopy_instance()
    except ImportError as exc:
        raise ImportError("phonon modes need phonopy: pip install ewald-aiida[phonopy]") from exc
    if phonon.force_constants is not None:
        return phonon
    procs = [source] + nodes.descendants(source) if source is not None else []
    for proc in procs:
        for t in nodes._outgoing(proc):
            if "ForceConstantsData" in t.node.node_type:
                phonon.force_constants = t.node.get_phonopy_instance().force_constants
                return phonon
    forces = getattr(data, "forces", None)
    if forces is not None:
        phonon.forces = forces
        phonon.produce_force_constants()
        return phonon
    raise LookupError(f"node {data.pk} has no force constants or forces")


def _phonon_bands(source):
    if source is None:
        return None
    from aiida import orm

    for proc in [source] + nodes.descendants(source):
        for t in nodes._outgoing(proc):
            if isinstance(t.node, orm.BandsData) and nodes.is_phonon_bands(t.node):
                return t.node
    return None


def _bands_path(bands):
    """``(band_path, labels)`` for phonopy from the k-points and labels of a ``BandsData``:
    paths of end points (connected within a path); two labels on neighbouring k-points mark
    a jump between paths."""
    import numpy as np

    k = np.asarray(bands.get_kpoints(), float)
    marks = sorted(dict(bands.labels or []).items())
    spans = [(i0, i1, l0, l1) for (i0, l0), (i1, l1) in zip(marks, marks[1:]) if i1 > i0 + 1]
    if not spans:
        return None, None
    paths, labels = [], []
    for j, (i0, i1, l0, l1) in enumerate(spans):
        if j == 0 or spans[j - 1][1] != i0:
            paths.append([k[i0].tolist()])
            labels.append(l0)
        paths[-1].append(k[i1].tolist())
        labels.append(l1)
    return paths, labels
