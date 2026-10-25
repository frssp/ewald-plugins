"""Secondary structure from backbone hydrogen bonds (Kabsch & Sander 1983, DSSP), simplified:
alpha helices (4-turns) and beta strands (bridges with a bridged neighbour); no 3-10/pi helices,
bulges or turns."""
from __future__ import annotations

import numpy as np

from ewald.pipeline import Modifier

from .backbone import backbone

COIL, HELIX, STRAND = 0, 1, 2
NAMES = {COIL: "coil", HELIX: "helix", STRAND: "strand"}


def hbond_matrix(N, CA, C, O, segment) -> np.ndarray:
    """``hb[i, j]``: the C=O of residue i accepts a hydrogen bond from the N-H of residue j
    (DSSP electrostatic energy below -0.5 kcal/mol)."""
    m = len(CA)
    H = N.copy()
    same = segment[1:] == segment[:-1]
    d = C[:-1] - O[:-1]
    d /= np.linalg.norm(d, axis=1, keepdims=True)
    H[1:][same] = N[1:][same] + d[same]          # H along the previous C=O, 1.0 A from N
    has_h = np.concatenate([[False], same])
    close = np.linalg.norm(CA[:, None] - CA[None], axis=2) < 9.0
    r = lambda a, b: np.linalg.norm(a[:, None] - b[None], axis=2) + 1e-9  # noqa: E731
    e = 0.084 * 332.0 * (1 / r(O, N) + 1 / r(C, H) - 1 / r(O, H) - 1 / r(C, N))
    hb = (e < -0.5) & close & has_h[None, :]
    idx = np.arange(m)
    hb &= np.abs(idx[:, None] - idx[None]) > 1
    return hb


def assign(N, CA, C, O, segment) -> np.ndarray:
    """One of COIL, HELIX, STRAND per residue."""
    m = len(CA)
    hb = hbond_matrix(N, CA, C, O, segment)
    ss = np.zeros(m, np.int8)
    seg_ok = lambda i, k: 0 <= i and i + k < m and segment[i] == segment[i + k]  # noqa: E731
    turn4 = np.array([seg_ok(i, 4) and hb[i, i + 4] for i in range(m)])
    for i in range(1, m):
        if turn4[i - 1] and turn4[i]:
            ss[i:i + 4] = HELIX
    bridge = np.zeros(m, bool)
    H = lambda i, j: 0 <= i < m and 0 <= j < m and hb[i, j]  # noqa: E731
    for i in range(1, m - 1):
        for j in np.flatnonzero(np.abs(np.arange(m) - i) > 2):
            if not (0 < j < m - 1):
                continue
            par = (H(i - 1, j) and H(j, i + 1)) or (H(j - 1, i) and H(i, j + 1))
            anti = (H(i, j) and H(j, i)) or (H(i - 1, j + 1) and H(j - 1, i + 1))
            if par or anti:
                bridge[i] = True
                break
    ladder = bridge & (np.roll(bridge, 1) | np.roll(bridge, -1))
    ss[ladder & (ss != HELIX)] = STRAND
    return ss


class SecondaryStructure(Modifier):
    """Assign helix / strand / coil from backbone hydrogen bonds (simplified DSSP) and store it as
    the per-atom property 'Secondary Structure' (0 coil, 1 helix, 2 strand); every atom of a residue
    gets its residue's value. ``use_file`` takes the HELIX/SHEET records of the file instead when
    there are any."""

    def __init__(self, use_file: bool = False):
        self.use_file = use_file

    def modify(self, data, ctx):
        bb = backbone(data)
        pos = data.particles["Position"]
        rec = data.attributes.get("Protein", {})
        if self.use_file and (rec.get("helices") or rec.get("strands")):
            ss = _from_records(data, bb, rec)
        else:
            ss = assign(pos[bb.n], pos[bb.ca], pos[bb.c], pos[bb.o], bb.segment)
        per_atom = np.zeros(data.count, np.int8)
        for a, b, s in zip(bb.start, bb.stop, ss):
            per_atom[a:b] = s
        data.particles["Secondary Structure"] = per_atom
        for k, name in NAMES.items():
            data.attributes[f"SecondaryStructure.{name}_residues"] = int((ss == k).sum())


def _from_records(data, bb, rec) -> np.ndarray:
    resi = data.particles["Residue Index"][bb.ca]
    ss = np.zeros(len(bb), np.int8)
    for value, key in ((HELIX, "helices"), (STRAND, "strands")):
        for ch, lo, hi in rec.get(key, []):
            ss[(bb.chain == ch) & (resi >= lo) & (resi <= hi)] = value
    return ss
