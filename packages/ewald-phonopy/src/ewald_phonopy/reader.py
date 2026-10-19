"""Phonon mode files as a looping trajectory.

- ``phonopy``: band.yaml / mesh.yaml / qpoints.yaml with eigenvectors;
- ``vasp-phonon``: VASP OUTCARs of IBRION=5-8 runs (Gamma modes);
- ``phonopy-fc``: phonopy's input (``phonopy.yaml``, ``phonopy_params.yaml``, ``phonopy_disp.yaml``)
  with forces or force constants; phonopy computes the band structure with eigenvectors.

Every frame is the primitive cell with the modes in ``data.attributes["Phonon Modes"]`` (a
:class:`ewald_phonopy.phonon.PhononModes`) and the frequencies in the table "Phonon Bands"; the
:class:`ewald_phonopy.PhononMode` modifier displaces the atoms along one mode, one period
over the ``frames`` frames.
"""
from __future__ import annotations

import os

import numpy as np

from ewald.data import Cell
from ewald.io.base import FrameReader

from .phonon import PhononModes, is_outcar_phonon, is_phonopy_yaml, read_modes


class PhononReader(FrameReader):
    """Phonon modes of ``path``; ``frames`` frames make one vibration period."""

    def __init__(self, path, frames: int = 24, structure=None):
        self.path = str(path)
        self.frames = int(frames)
        if self.frames < 1:
            raise ValueError("frames must be at least 1")
        self.modes: PhononModes = read_modes(self.path, structure=structure)
        self._table = self.modes.table()  # shared by every frame, so the Plots tab draws it once

    def __len__(self) -> int:
        return self.frames

    def read(self, index: int):
        from ewald.data import DataCollection

        m = self.modes
        data = DataCollection(m.positions.copy(), m.types, m.cell.copy())
        data.particles["Mass"] = m.masses
        data.attributes["Phonon Modes"] = m
        data.attributes["Timestep"] = int(index)
        data.tables["Phonon Bands"] = dict(self._table)
        return data


class PhonopyYamlReader(PhononReader):
    """phonopy band.yaml/mesh.yaml/qpoints.yaml with eigenvectors: phonon modes (PhononMode animates one); frames= per period, structure= for qpoints.yaml"""

    patterns = ("band.yaml", "mesh.yaml", "qpoints.yaml", "*.yaml")
    sniff = staticmethod(is_phonopy_yaml)
    priority = 9
    aliases = ("phonopy-yaml", "band.yaml", "phonon")


class VaspPhononReader(PhononReader):
    """VASP OUTCAR of an IBRION=5-8 run: Gamma phonon modes (PhononMode animates one)"""

    patterns = ("OUTCAR*",)
    sniff = staticmethod(is_outcar_phonon)
    priority = 15          # before ewald's OUTCAR reader (16), which reads the ionic steps
    aliases = ("outcar-phonon",)


_NAMES = ("phonopy.yaml", "phonopy_params.yaml", "phonopy_disp.yaml", "phonopy.yml")


def _has_forces(path: str) -> bool:
    folder = os.path.dirname(os.path.abspath(path))
    if any(os.path.exists(os.path.join(folder, f)) for f in ("FORCE_SETS", "FORCE_CONSTANTS", "force_constants.hdf5")):
        return True
    with open(path, encoding="utf-8", errors="replace") as fh:
        text = fh.read(4_000_000)
    return "\nforce_constants:" in text or "\n  forces:" in text or "\nforces:" in text or "\n    forces:" in text


def sniff(path) -> bool:
    """A phonopy input yaml (``phonopy:`` header with a ``supercell_matrix``) with forces or
    force constants available; band.yaml and mesh.yaml are left to ewald's own reader."""
    path = str(path)
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            head = fh.read(20000)
    except OSError:
        return False
    if "phonopy:" not in head or "supercell_matrix:" not in head or "\nphonon:" in head:
        return False
    try:
        return _has_forces(path)
    except OSError:
        return False


def _ticks(distances, connections, labels) -> list[tuple[float, str]]:
    """High-symmetry ticks of phonopy band segments. phonopy's ``labels`` has one label per
    segment start plus, at every break in the path (``connections[i]`` False) and at the end,
    the label of the segment's end; at a break the end and the next start share an x and
    become one "end|start" tick."""
    n = len(distances)
    connections = list(connections) if connections is not None else [True] * (n - 1) + [False]
    it = iter(labels)
    ticks = [(float(np.asarray(distances[0])[0]), next(it, ""))]
    for i in range(n):
        x = float(np.asarray(distances[i])[-1])
        if i < n - 1 and connections[i]:
            ticks.append((x, next(it, "")))
            continue
        end = next(it, "")
        if i < n - 1:
            start = next(it, "")
            end = end if end == start else f"{end}|{start}"
        ticks.append((x, end))
    return ticks


def modes_from_phonopy(phonon, npoints: int = 51, source: str = "", band_path=None,
                       labels=None) -> PhononModes:
    """Band structure with eigenvectors of a ``phonopy.Phonopy`` that has force constants, along
    the seekpath path of its primitive cell, or along ``band_path``: segments of q-points in
    reduced coordinates of the primitive reciprocal cell, e.g. ``[[[0, 0, 0], [0.5, 0, 0.5]],
    [[0.5, 0.5, 0.5], [0, 0, 0]]]`` (a break between segments), with ``labels`` for the ends."""
    if phonon.force_constants is None:
        raise ValueError("the Phonopy object has no force constants (produce_force_constants first)")
    if band_path is None:
        phonon.auto_band_structure(npoints=npoints, with_eigenvectors=True)
    else:
        from phonopy.phonon.band_structure import get_band_qpoints_and_path_connections

        qpoints, connections = get_band_qpoints_and_path_connections(band_path, npoints=npoints)
        phonon.run_band_structure(qpoints, path_connections=connections, labels=labels,
                                  with_eigenvectors=True)
    bs = phonon.get_band_structure_dict()
    prim = phonon.primitive
    natoms = len(prim)
    qpoints = np.concatenate([np.asarray(q, float) for q in bs["qpoints"]])
    distances = np.concatenate([np.asarray(d, float) for d in bs["distances"]])
    frequencies = np.concatenate([np.asarray(f, float) for f in bs["frequencies"]])
    vecs = np.concatenate([np.asarray(e) for e in bs["eigenvectors"]])          # (nq, 3N, nbands)
    eigenvectors = vecs.transpose(0, 2, 1).reshape(len(qpoints), -1, natoms, 3)
    ticks = _ticks(bs["distances"], getattr(phonon.band_structure, "path_connections", None),
                   list(getattr(phonon.band_structure, "labels", None) or []))
    return PhononModes(cell=Cell(np.array(prim.cell, float)), positions=np.array(prim.positions, float),
                       types=np.array(prim.symbols), masses=np.array(prim.masses, float), qpoints=qpoints,
                       frequencies=frequencies, eigenvectors=eigenvectors, distances=distances, ticks=ticks,
                       source=source or "phonopy force constants")


class PhonopyForceConstantsReader(PhononReader):
    """phonopy input with forces or force constants: band structure with eigenvectors (phonopy)."""

    patterns = _NAMES
    sniff = staticmethod(sniff)
    priority = 8           # phonopy input files; band/mesh/qpoints.yaml go to PhonopyYamlReader
    description = "phonopy.yaml with FORCE_SETS/force constants: band structure computed by phonopy"

    def __init__(self, path, frames: int = 24, npoints: int = 51):
        import phonopy

        self.path = str(path)
        self.frames = int(frames)
        if self.frames < 1:
            raise ValueError("frames must be at least 1")
        folder = os.path.dirname(os.path.abspath(self.path))
        kwargs = {}
        for name, key in (("FORCE_SETS", "force_sets_filename"), ("FORCE_CONSTANTS", "force_constants_filename")):
            if os.path.exists(os.path.join(folder, name)):
                kwargs[key] = os.path.join(folder, name)
        phonon = phonopy.load(self.path, log_level=0, **kwargs)
        if phonon.force_constants is None:
            raise ValueError(f"{self.path}: phonopy found no forces or force constants "
                             f"(put FORCE_SETS or FORCE_CONSTANTS next to it)")
        self.modes = modes_from_phonopy(phonon, npoints=npoints,
                                        source=f"phonopy {os.path.basename(self.path)}")
        self._table = self.modes.table()


def reader_from_phonopy(phonon, frames: int = 24, npoints: int = 51, band_path=None, labels=None,
                        source: str = "") -> PhononReader:
    """A :class:`PhononReader` over a ``phonopy.Phonopy`` with force constants (e.g.
    aiida-phonopy's ``get_phonopy_instance()``): its band structure with eigenvectors as a
    looping trajectory of ``frames`` frames. ``band_path``/``labels`` as in
    :func:`modes_from_phonopy`."""
    reader = PhononReader.__new__(PhononReader)
    reader.path = source or "phonopy"
    reader.frames = int(frames)
    if reader.frames < 1:
        raise ValueError("frames must be at least 1")
    reader.modes = modes_from_phonopy(phonon, npoints=npoints, source=source or "phonopy object",
                                      band_path=band_path, labels=labels)
    reader._table = reader.modes.table()
    return reader


def from_phonopy(phonon, frames: int = 24, npoints: int = 51, band_path=None, labels=None,
                 source: str = "", mode: bool = True):
    """A ``Pipeline`` over a ``phonopy.Phonopy`` with force constants, as ``import_file`` gives
    for a phonon file: ``frames`` frames make one period, and with ``mode`` a
    :class:`~ewald_phonopy.PhononMode` with its default mode is already added."""
    from ewald import Pipeline, StaticSource

    from .modifier import PhononMode

    reader = reader_from_phonopy(phonon, frames, npoints, band_path, labels, source)
    pipe = Pipeline(StaticSource([reader.read(i) for i in range(len(reader))]))
    if mode:
        pipe.modifiers.append(PhononMode())
    return pipe
