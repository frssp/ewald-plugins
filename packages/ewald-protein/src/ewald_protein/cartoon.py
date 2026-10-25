"""Cartoon (ribbon) of protein chains as one triangle mesh, so every EWALD renderer (OpenGL, the
ray tracer, SVG/PDF, the legacy viewport) draws it the same way.

The backbone is a Catmull-Rom spline through the CA atoms; the width direction follows the C=O
vectors (in the sheet plane for strands, along the axis for helices). Each spline sample gets a
superellipse cross-section: round tube for coil, flat ribbon for helices, flat box with an arrow
head for strands. Faces carry the colour (lit in every renderer), vertices the smooth normals.
"""
from __future__ import annotations

import numpy as np

from ewald.mesh import SurfaceMesh
from ewald.scene import VisualElement

from .backbone import backbone
from .ss import COIL, HELIX, STRAND, assign

SS_COLORS = {COIL: (0.78, 0.78, 0.76), HELIX: (0.86, 0.30, 0.36), STRAND: (0.98, 0.78, 0.25)}
CHAIN_COLORS = [(0.30, 0.55, 0.85), (0.90, 0.50, 0.25), (0.35, 0.70, 0.45), (0.75, 0.40, 0.70),
                (0.85, 0.75, 0.30), (0.40, 0.75, 0.80), (0.85, 0.40, 0.45), (0.55, 0.55, 0.55)]


class CartoonVis(VisualElement):
    """Cartoon of every protein chain. ``color_by``: 'ss' (helix/strand/coil), 'chain' or
    'rainbow' (N to C terminus with ``colormap``). Sizes in Angstrom; ``quality`` is the number of
    spline samples per residue (also the cross-section detail)."""

    name = "Cartoon"

    def __init__(self, color_by: str = "ss", colormap: str = "turbo", coil_radius: float = 0.3,
                 helix_width: float = 1.5, helix_thickness: float = 0.3, strand_width: float = 1.5,
                 strand_thickness: float = 0.4, arrow_width: float = 2.3, quality: int = 8):
        self.color_by = color_by
        self.colormap = colormap
        self.coil_radius = coil_radius
        self.helix_width = helix_width
        self.helix_thickness = helix_thickness
        self.strand_width = strand_width
        self.strand_thickness = strand_thickness
        self.arrow_width = arrow_width
        self.quality = quality

    def applies(self, data) -> bool:
        return "Residue Index" in data.particles and "Atom Name" in data.particles

    def build(self, data, ctx):
        bb = backbone(data)
        pos = data.particles["Position"]
        if "Secondary Structure" in data.particles:
            ss = data.particles["Secondary Structure"][bb.ca].astype(int)
        else:
            ss = assign(pos[bb.n], pos[bb.ca], pos[bb.c], pos[bb.o], bb.segment).astype(int)
        colors = self._residue_colors(bb, ss)
        parts = []
        for seg in np.unique(bb.segment):
            idx = np.flatnonzero(bb.segment == seg)
            if len(idx) >= 2:
                parts.append(_segment_mesh(pos[bb.ca[idx]], pos[bb.o[idx]] - pos[bb.c[idx]], ss[idx],
                                           colors[idx], self))
        if not parts:
            return None
        v, f, n, c = [], [], [], []
        off = 0
        for pv, pf, pn, pc in parts:
            v.append(pv), f.append(pf + off), n.append(pn), c.append(pc)
            off += len(pv)
        return ("cartoon", SurfaceMesh(np.concatenate(v), np.concatenate(f), {"Color": np.concatenate(c)},
                                       vertex_properties={"Normal": np.concatenate(n)}))

    def _residue_colors(self, bb, ss):
        if self.color_by == "chain":
            names = list(dict.fromkeys(bb.chain))
            return np.array([CHAIN_COLORS[names.index(ch) % len(CHAIN_COLORS)] for ch in bb.chain])
        if self.color_by == "rainbow":
            from ewald.colormaps import get_colormap

            cmap = get_colormap(self.colormap)
            t = np.zeros(len(bb))
            for ch in np.unique(bb.chain):
                k = np.flatnonzero(bb.chain == ch)
                t[k] = np.linspace(0, 1, len(k))
            return np.asarray(cmap(t))[:, :3]
        return np.array([SS_COLORS[s] for s in ss])


# ----------------------------------------------------------------------------- geometry
def _segment_mesh(ca, carbonyl, ss, colors, opt):
    k, sub = len(ca), max(2, int(opt.quality))
    ctrl = ca.copy()
    for i in range(1, k - 1):                       # take the pleat out of strands
        if ss[i] == STRAND:
            ctrl[i] = 0.25 * ca[i - 1] + 0.5 * ca[i] + 0.25 * ca[i + 1]
    # consistent C=O directions (flip every other one, as consecutive C=O point opposite ways)
    o = carbonyl / np.linalg.norm(carbonyl, axis=1, keepdims=True)
    for i in range(1, k):
        if o[i] @ o[i - 1] < 0:
            o[i] = -o[i]
    P = _catmull_rom(ctrl, sub)
    O = _catmull_rom(o, sub)
    T = np.gradient(P, axis=0)
    T /= np.linalg.norm(T, axis=1, keepdims=True)
    N = O - (O * T).sum(1, keepdims=True) * T
    N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-9)
    B = np.cross(T, N)
    m = len(P)
    res = np.minimum(np.rint(np.arange(m) / sub).astype(int), k - 1)
    s = ss[res]
    w = np.where(s == HELIX, opt.helix_width, np.where(s == STRAND, opt.strand_width, 2 * opt.coil_radius))
    h = np.where(s == HELIX, opt.helix_thickness, np.where(s == STRAND, opt.strand_thickness, 2 * opt.coil_radius))
    e = np.where(s == STRAND, 6.0, 2.0)
    box = np.ones(sub) / sub                         # ease width changes over one residue
    pad = lambda a: np.convolve(np.pad(a, (sub, sub), mode="edge"), box, "same")[sub:-sub]  # noqa: E731
    w, h, e = pad(w), pad(h), pad(e)
    caps = {}                                        # sample index -> (width before, width after)
    for i in range(k):                               # arrow heads on the last residue of each strand
        if ss[i] == STRAND and (i + 1 == k or ss[i + 1] != STRAND):
            a, b = max(0, (i - 1) * sub + sub // 2), min(m - 1, i * sub + sub // 2)
            if b > a:
                caps[a] = w[a]
                w[a:b + 1] = np.linspace(opt.arrow_width, 0.15, b - a + 1)
                h[a:b + 1], e[a:b + 1] = opt.strand_thickness, 6.0
    rings = []                                       # (point, T, N, B, w, h, e, flat normal or None, joined, sample)
    for j in range(m):
        if j == 0:
            rings.append((P[j], T[j], N[j], B[j], 0.0, 0.0, e[j], -T[j], False, j))
            rings.append((P[j], T[j], N[j], B[j], w[j], h[j], e[j], -T[j], True, j))
        if j in caps:                                # the flat back of an arrow head
            rings.append((P[j], T[j], N[j], B[j], caps[j], h[j], e[j], None, j > 0, j))
            rings.append((P[j], T[j], N[j], B[j], caps[j], h[j], e[j], -T[j], False, j))
            rings.append((P[j], T[j], N[j], B[j], w[j], h[j], e[j], -T[j], True, j))
            rings.append((P[j], T[j], N[j], B[j], w[j], h[j], e[j], None, False, j))
            continue
        rings.append((P[j], T[j], N[j], B[j], w[j], h[j], e[j], None, j > 0, j))
        if j == m - 1:
            rings.append((P[j], T[j], N[j], B[j], w[j], h[j], e[j], T[j], False, j))
            rings.append((P[j], T[j], N[j], B[j], 0.0, 0.0, e[j], T[j], True, j))
    ncs = max(8, 2 * sub)
    th = np.linspace(0, 2 * np.pi, ncs, endpoint=False)
    cos, sin = np.cos(th), np.sin(th)
    verts, norms, faces, fcol = [], [], [], []
    for r, (p, t, n, b, wi, hi, ei, flat, joined, j) in enumerate(rings):
        x = 0.5 * wi * np.sign(cos) * np.abs(cos) ** (2 / ei)
        y = 0.5 * hi * np.sign(sin) * np.abs(sin) ** (2 / ei)
        verts.append(p + x[:, None] * n + y[:, None] * b)
        if flat is not None:
            norms.append(np.tile(flat, (ncs, 1)))
        else:                                        # gradient of |x/a|^e + |y/b|^e
            gx = np.sign(cos) * np.abs(cos) ** (2 * (ei - 1) / ei) / max(wi, 1e-6)
            gy = np.sign(sin) * np.abs(sin) ** (2 * (ei - 1) / ei) / max(hi, 1e-6)
            g = gx[:, None] * n + gy[:, None] * b
            norms.append(g / np.maximum(np.linalg.norm(g, axis=1, keepdims=True), 1e-12))
        if joined and r > 0:
            a0, a1 = (r - 1) * ncs, r * ncs
            jj = np.arange(ncs)
            jn = (jj + 1) % ncs
            faces.append(np.column_stack([a0 + jj, a0 + jn, a1 + jn]))
            faces.append(np.column_stack([a0 + jj, a1 + jn, a1 + jj]))
            fcol.append(np.tile(colors[res[j]], (2 * ncs, 1)))
    verts, norms = np.concatenate(verts), np.concatenate(norms)
    return verts, np.concatenate(faces), norms, np.concatenate(fcol)


def _catmull_rom(pts, sub):
    """``sub`` samples per interval through every point (uniform Catmull-Rom), ends included."""
    p = np.concatenate([2 * pts[:1] - pts[1:2], pts, 2 * pts[-1:] - pts[-2:-1]])
    u = np.arange(sub) / sub
    u2, u3 = u * u, u * u * u
    out = []
    for i in range(1, len(p) - 2):
        p0, p1, p2, p3 = p[i - 1], p[i], p[i + 1], p[i + 2]
        out.append(0.5 * ((2 * p1)[None] + np.outer(u, p2 - p0) + np.outer(2 * u2, p0) - np.outer(5 * u2, p1)
                          + np.outer(4 * u2, p2) - np.outer(u2, p3) + np.outer(-u3, p0) + np.outer(3 * u3, p1)
                          - np.outer(3 * u3, p2) + np.outer(u3, p3)))
    out.append(pts[-1:])
    return np.concatenate(out)
