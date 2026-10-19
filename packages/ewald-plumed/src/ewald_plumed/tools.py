"""Claude tools for PLUMED (Ask panel, ``ewald ask``, the MCP server): run a plumed.dat over the
loaded trajectory, and read COLVAR / HILLS files."""
from __future__ import annotations

import os

import numpy as np

from ewald.llm.tools import ToolResult, downsample
from ewald.plugins import claude_tool

from . import plumed as pl
from .modifiers import Plumed


@claude_tool(
    "compute_plumed_cvs",
    "Collective variables computed by PLUMED (needs the PLUMED library) over the trajectory from a plumed.dat "
    "(text or path): e.g. 'd: DISTANCE ATOMS=1,2' (atoms numbered from 1, by Particle Identifier when present), "
    "TORSION, COORDINATION, RMSD, METAD with temperature. Appends a Plumed modifier (unless keep=false), so "
    "every frame gets attributes Plumed.<name> (PLUMED units: nm, rad, kJ/mol) and per-atom labels become "
    "properties 'Plumed <label>'. Returns statistics per value and a downsampled table over frames.",
    {"type": "object", "required": ["input"], "properties": {
        "input": {"type": "string", "description": "PLUMED input text, or the path of a plumed.dat"},
        "start": {"type": "integer"}, "stop": {"type": "integer"}, "step": {"type": "integer"},
        "time_per_frame": {"type": "number", "description": "ps between stored frames (default 1)"},
        "temperature": {"type": "number", "description": "K, for METAD and other biases"},
        "keep": {"type": "boolean", "description": "keep the modifier in the pipeline (default true)"}}})
def compute_plumed_cvs(toolset, input, start=0, stop=None, step=1, time_per_frame=1.0, temperature=0.0, keep=True):
    pipe = toolset._need_pipeline()
    problems = pl.untrusted_input_problems(input)
    if problems:
        raise PermissionError("not run: " + "; ".join(problems))
    mod = Plumed(input, start=start, stop=stop, step=step, time_per_frame=time_per_frame, temperature=temperature)
    pipe.modifiers.append(mod)
    try:
        data = pipe.compute(toolset.frame)
    except Exception:
        pipe.modifiers.remove(mod)
        raise
    if not keep:
        pipe.modifiers.remove(mod)
    table = {k: np.asarray(v, float) for k, v in data.tables["plumed"].items()}
    stats = {k: {"min": float(np.nanmin(v)), "max": float(np.nanmax(v)), "mean": float(np.nanmean(v)),
                 "first": float(v[0]), "last": float(v[-1])} for k, v in table.items() if k != "Frame"}
    per_atom = {name: {"min": float(np.min(data[name])), "max": float(np.max(data[name])),
                       "mean": float(np.mean(data[name])), "frame": toolset.frame}
                for name in data.particles if name.startswith("Plumed ")}
    cols = ["Frame"] + [k for k in table if k != "Frame"][:12]
    return {"values": stats, "per_atom": per_atom, "table": downsample({k: table[k] for k in cols}),
            "pipeline": toolset._pipeline_list()}


@claude_tool(
    "read_plumed_output",
    "Read a PLUMED output file. COLVAR (any '#! FIELDS' file): columns, statistics and a downsampled table. "
    "HILLS: the metadynamics free energy surface F = -sum of hills (as plumed sum_hills), with its minimum, "
    "range and a plot image.",
    {"type": "object", "required": ["path"], "properties": {
        "path": {"type": "string"},
        "bins": {"type": "integer", "description": "FES grid bins per CV (default 100)"}}})
def read_plumed_output(toolset, path, bins=100):
    path = os.path.expanduser(path)
    table = pl.read_colvar(path)
    if not any(k.startswith("sigma_") for k in table):
        stats = {k: {"min": float(np.nanmin(v)), "max": float(np.nanmax(v)), "mean": float(np.nanmean(v))}
                 for k, v in table.items()}
        return {"kind": "colvar", "rows": len(next(iter(table.values()), [])), "columns": stats,
                "table": downsample(dict(table)) if table else {}}
    fes = pl.fes_from_hills(path, bins=bins)
    f = np.asarray(fes["fes"])
    at = np.unravel_index(int(np.argmin(f)), f.shape)
    out = {"kind": "hills", "hills": len(table["height"]), "cvs": fes["cvs"],
           "minimum": {cv: float(ax[i]) for cv, ax, i in zip(fes["cvs"], fes["grid"], at)},
           "fes_max_kJ_mol": float(f.max()),
           "ranges": {cv: [float(ax[0]), float(ax[-1])] for cv, ax in zip(fes["cvs"], fes["grid"])}}
    if len(fes["cvs"]) == 1:
        out["table"] = downsample(fes["table"])
    if len(fes["cvs"]) > 2:
        return out
    import matplotlib

    matplotlib.use("Agg", force=False)
    from matplotlib.figure import Figure

    fig = Figure(figsize=(5, 3.6))
    pl.plot_fes(fes, fig.add_subplot(111))
    fig.tight_layout()
    png = os.path.join(toolset.workdir, f"fes_{len(toolset.figures):03d}.png")
    fig.savefig(png, dpi=120)
    toolset.figures.append(png)
    out["plot"] = png
    with open(png, "rb") as fh:
        return ToolResult(out, images=[fh.read()])
