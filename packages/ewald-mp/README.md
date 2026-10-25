# ewald-mp

The [Materials Project](https://next-gen.materialsproject.org) in EWALD through
[mp-api](https://github.com/materialsproject/api), with your own API key. Besides structures it
gives what MP's OPTIMADE endpoint does not: band structures, densities of states, charge
densities and relaxation trajectories. For structures alone, without a key, the
[ewald-optimade](../ewald-optimade) plugin is enough (`load("optimade:mp/mp-149")`).

```bash
pip install "ewald-mp @ git+https://github.com/frssp/ewald-plugins@<commit>#subdirectory=packages/ewald-mp"
```

or Plugins side bar › Catalog › Materials Project › Install. Then set the key under
Preferences › Materials Project (get it at https://next-gen.materialsproject.org/api). EWALD
keeps it in the system keychain, never in a settings file. Without one there, mp-api's own
places work too (`MP_API_KEY`, `~/.pmgrc.yaml`).

```python
from ewald import load
from ewald_mp import search

pipe = load("mp:mp-149")               # the final structure (conventional=True: conventional cell)
pipe = load("mp:mp-149/bands")         # + band structure, table "Bands"
pipe = load("mp:mp-149/dos")           # + density of states, table "DOS" (projected per site and orbital)
pipe = load("mp:mp-149/electronic")    # both
pipe = load("mp:mp-149/chgcar")        # + the charge density grid ("Charge Density" e/Å³, "Magnetization")
pipe = load("mp:mp-149/relax")         # the relaxation, one frame per ionic step (Force, Energy)
pipe = load("mp:mp-149/initial")       # the structures its calculations started from

search("Li-P-S", is_stable=True)       # uri, formula, space group, energy above hull, band gap
search("ABO3", energy_above_hull=(0, 0.02), band_gap=(1, 4))
```

A search takes a formula (`LiFePO4`, also `ABO3` or `Si*`), a chemical system (`Li-P-S`),
elements a material must contain (`Li P S`) or ids (`mp-149, mp-13`), plus any argument of
mp-api's `materials.summary.search`. Hits come most stable first.

`/relax` picks the material's structure optimization task, r2SCAN first, then GGA+U, then GGA;
`run_type="GGA"` prefers one, `task="mp-…"` names the task.

## Side bar and AI

The Materials Project button on the activity bar opens a side bar: search, choose what to open
(structure, bands, DOS, charge density, relaxation), then double-click, or **Insert cell** for
`pipe = load("mp:...")` in the notebook.

The AI gets one read-only tool, `mp_search`. It never sees the key; to open a material it
writes a notebook cell, as for every other change.

From a shell: `python -m ewald_mp search Li-P-S --stable [--json]`.

## Tests

`pytest packages/ewald-mp/tests` uses a stand-in for `MPRester` that answers with real pymatgen
objects, so it needs mp-api installed but no key or internet.
