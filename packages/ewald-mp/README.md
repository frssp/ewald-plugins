# ewald-mp

The [Materials Project](https://next-gen.materialsproject.org) in EWALD with your own API key.
Besides structures it gives what MP's OPTIMADE endpoint does not: band structures, densities of
states, charge densities and relaxation trajectories. For structures alone, without a key,
EWALD's built-in OPTIMADE support is enough (`load("optimade:mp/mp-149")`).

```bash
pip install "ewald-mp @ git+https://github.com/frssp/ewald-plugins@<commit>#subdirectory=packages/ewald-mp"
```

or Plugins side bar › Catalog › Materials Project › Install. Then set the key under
Preferences › Materials Project (get it at https://next-gen.materialsproject.org/api). EWALD
keeps it in the system keychain, never in a settings file. Without one there, mp-api's own
places work too (`MP_API_KEY`, `~/.pmgrc.yaml`).

## Light by default, mp-api when installed

The plugin installs nothing besides EWALD and `truststore`. It talks to MP's REST API
(`api.materialsproject.org`, the key in the `X-API-Key` header) for searches and structures,
and reads band structures, DOS and charge densities from MP's public open data bucket
(`materialsproject-parsed`, the per-task `.json.gz` files), converting them without pymatgen.

[mp-api](https://github.com/materialsproject/api) pulls in pymatgen, emmet-core, boto3,
deltalake and pyarrow (about 50 packages). Install it only for what needs MP's newer Delta
tables: relaxation trajectories (`/relax`), and band structures or DOS of calculations newer
than the per-task files.

```bash
pip install mp-api            # or: pip install "ewald-mp[full] @ git+..."
```

With mp-api installed the plugin uses it for everything (Preferences › Materials Project ›
Advanced › Use mp-api when it is installed turns that off). Without it, `/relax` and a missing
file say to install it.

Behind a proxy that re-signs HTTPS ("CERTIFICATE_VERIFY_FAILED"), the plugin uses the operating
system's certificate store (`truststore`; for mp-api it is injected before mp-api starts), as
EWALD's own downloads do. Preferences › Materials Project › Advanced › Use the system certificate
store turns that off.

```python
from ewald import load
from ewald_mp import search

pipe = load("mp:mp-149")               # the final structure (conventional=True: conventional cell)
pipe = load("mp:mp-149/bands")         # + band structure, table "Bands"
pipe = load("mp:mp-149/dos")           # + density of states, table "DOS" (projected per site and orbital)
pipe = load("mp:mp-149/electronic")    # both
pipe = load("mp:mp-149/chgcar")        # + the charge density grid ("Charge Density" e/Å³, "Magnetization")
pipe = load("mp:mp-149/relax")         # the relaxation, one frame per ionic step (Force, Energy); mp-api
pipe = load("mp:mp-149/initial")       # the structures its calculations started from

search("Li-P-S", is_stable=True)       # uri, formula, space group, energy above hull, band gap
search("ABO3", energy_above_hull=(0, 0.02), band_gap=(1, 4))
```

A search takes a formula (`LiFePO4`, also `ABO3` or `Si*`), a chemical system (`Li-P-S`),
elements a material must contain (`Li P S`) or ids (`mp-149, mp-13`), plus any argument of
mp-api's `materials.summary.search` (ranges as `(min, max)`). Hits come most stable first.
Without mp-api, `conventional=True` is spglib's conventional standard cell (pymatgen may order
the axes differently).

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

`pytest packages/ewald-mp/tests` needs no key or internet: `test_rest.py` runs the plugin
without mp-api against a local server that answers as the REST API and the open data bucket do;
`test_mp.py` runs it with mp-api, through a stand-in for `MPRester` that answers with real
pymatgen objects (skipped without pymatgen), and `test_rest.py` also checks that their
`as_dict()` reads the same as the objects.
