"""EWALD frames from an exporter bundle (:mod:`ewald_aiida.export`)."""
from __future__ import annotations

import numpy as np

from ewald import Cell, DataCollection


def structure(item, arrays, prefix) -> DataCollection:
    data = DataCollection(arrays[prefix + "positions"], item["symbols"],
                          Cell(arrays[prefix + "cell"], pbc=np.array(item["pbc"], bool)))
    if item["kinds"] != item["symbols"]:
        data.particles["Kind"] = np.array(item["kinds"])  # Fe1/Fe2 magnetic kinds
    return data


class Trajectory:
    """One ``TrajectoryData`` item; :meth:`frame` builds step ``i``."""

    def __init__(self, item, arrays, prefix):
        self.item = item
        self.positions = arrays[prefix + "positions"]
        self.cells = arrays.get(prefix + "cells")
        self.steps = arrays[prefix + "steps"]
        self.times = arrays.get(prefix + "times")
        pbc = item["pbc"]
        self.pbc = np.array(pbc, bool) if pbc is not None else np.array([self.cells is not None] * 3)
        self.per_atom = {prop: arrays[prefix + "pa." + name] for name, prop in item["per_atom"].items()}
        self.per_step = {name: arrays[prefix + "ps." + name] for name in item["per_step"]}

    def __len__(self) -> int:
        return len(self.positions)

    def frame(self, i: int) -> DataCollection:
        cell = Cell(self.cells[i], pbc=self.pbc) if self.cells is not None else Cell(pbc=self.pbc)
        data = DataCollection(self.positions[i], self.item["symbols"], cell)
        for prop, a in self.per_atom.items():
            data.particles[prop] = a[i]
        data.attributes["Timestep"] = int(self.steps[i])
        if self.times is not None:
            data.attributes["Time"] = float(self.times[i])
        for name, a in self.per_step.items():
            data.attributes[name] = a[i].item()
        return data


def bands(item, arrays, prefix) -> DataCollection:
    """The structure with ``ElectronicStructure`` (tables, Fermi energy, gap) of a ``BandsData``."""
    from ewald.electronic import ElectronicStructure, pretty_label

    e = arrays[prefix + "bands"]
    e = e[None] if e.ndim == 2 else e                          # (nspin, nk, nb)
    kpts = arrays[prefix + "kpoints"]
    cart = arrays.get(prefix + "kcart")
    cart = kpts if cart is None else cart / (2 * np.pi)       # 1/Angstrom without 2 pi, as phonopy
    step = np.linalg.norm(np.diff(cart, axis=0), axis=1)
    labels = item["labels"]
    breaks = [b for (a, _), (b, _) in zip(labels, labels[1:]) if b == a + 1]  # two labels side by side
    for b in breaks:
        step[b - 1] = 0.0                                      # a jump in the path is not distance
    dist = np.concatenate([[0.0], np.cumsum(step)])
    occ = arrays.get(prefix + "occupations")
    s = item.get("structure")
    data = structure(s, arrays, prefix + "s.") if s else DataCollection([], [])
    es = ElectronicStructure(np.array(s["symbols"] if s else []), efermi=float(item["efermi"] or 0.0),
                             kpoints=kpts, eigenvalues=e,
                             occupations=None if occ is None else occ.reshape(e.shape),
                             distances=dist, ticks=[(float(dist[i]), pretty_label(l)) for i, l in labels],
                             breaks=breaks, source=f"AiiDA BandsData {item['pk']}")
    return es.attach(data)


def phonon_reader(item, frames: int):
    """Phonon modes through ewald-phonopy: the exported phonopy params become a
    ``phonopy.Phonopy`` whose band structure is a looping trajectory."""
    try:
        from ewald_phonopy import reader_from_phonopy
    except ImportError as exc:
        raise ImportError("phonon modes need the ewald-phonopy plugin: pip install "
                          "'git+https://github.com/frssp/ewald-plugins#subdirectory=packages/ewald-phonopy'") from exc
    import os
    import tempfile

    import phonopy

    fd, tmp = tempfile.mkstemp(suffix="-phonopy.yaml")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(item["phonopy_yaml"])
        phonon = phonopy.load(tmp, produce_fc=False, log_level=0)
    finally:
        os.remove(tmp)
    return reader_from_phonopy(phonon, frames=frames, band_path=item["band_path"], labels=item["band_labels"],
                               source=f"AiiDA {item['type']} {item['pk']}")
