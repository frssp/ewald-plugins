"""Residues of a DataCollection read by :class:`ProteinReader`: atom ranges and backbone atoms."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Backbone:
    """Amino-acid residues that have N, CA, C and O, in file order. ``start``/``stop`` are the atom
    ranges, ``n``/``ca``/``c``/``o`` atom indices, ``chain`` the chain names and ``segment`` a number
    that changes at every chain end or chain break (C(i)-N(i+1) longer than 2.5 A)."""

    start: np.ndarray
    stop: np.ndarray
    n: np.ndarray
    ca: np.ndarray
    c: np.ndarray
    o: np.ndarray
    chain: np.ndarray
    segment: np.ndarray

    def __len__(self) -> int:
        return len(self.ca)


def backbone(data) -> Backbone:
    p = data.particles
    if "Residue Index" not in p or "Atom Name" not in p:
        raise ValueError("no residues: open the file with the protein reader (PDB/mmCIF)")
    chain, resi, name = p["Chain"], p["Residue Index"], p["Atom Name"]
    poly = p.get("Polymer", np.ones(len(resi), np.int8))
    new = np.ones(len(resi), bool)
    new[1:] = (chain[1:] != chain[:-1]) | (resi[1:] != resi[:-1])
    starts = np.flatnonzero(new)
    stops = np.append(starts[1:], len(resi))
    rows = []
    for a, b in zip(starts, stops):
        if not poly[a]:
            continue
        names = list(name[a:b])
        try:
            rows.append((a, b, *(a + names.index(k) for k in ("N", "CA", "C", "O")), chain[a]))
        except ValueError:      # missing backbone atom
            continue
    if not rows:
        raise ValueError("no amino-acid residues with a complete backbone")
    a, b, n, ca, c, o, ch = map(np.asarray, zip(*rows))
    pos = data.particles["Position"]
    gap = np.linalg.norm(pos[n[1:]] - pos[c[:-1]], axis=1) > 2.5
    brk = np.concatenate([[False], gap | (ch[1:] != ch[:-1])])
    return Backbone(a, b, n, ca, c, o, ch, np.cumsum(brk))
