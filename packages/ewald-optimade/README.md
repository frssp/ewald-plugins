# ewald-optimade

Search and open crystal structures of [OPTIMADE](https://www.optimade.org) databases in EWALD:
Materials Project, the Crystallography Open Database, OQMD, Alexandria, NOMAD, Materials Cloud,
JARVIS and any other OPTIMADE server. No account or API key is needed.

```bash
pip install "ewald-optimade @ git+https://github.com/frssp/ewald-plugins@<commit>#subdirectory=packages/ewald-optimade"
```

or Plugins side bar › Catalog › OPTIMADE structures › Install.

```python
from ewald import load
from ewald_optimade import search

pipe = load("optimade:mp/mp-149")       # Materials Project, Si
pipe = load("optimade:cod/1000041")     # Crystallography Open Database
pipe = load("optimade:oqmd?Li-P-S")     # every Li-P-S structure it finds, one frame each (limit=50)

search("LiFePO4", db="mp")              # hits with .uri, .formula, .nsites
search("Li P S", db="alexandria")       # structures that contain Li, P and S
search('elements HAS ALL "Si","O" AND nsites<=6', db="cod")   # an OPTIMADE filter as it is
```

## Addresses

| Address | Opens |
|---|---|
| `optimade:DB/ID` | one structure, by the database's own id (it may hold slashes) |
| `optimade:DB?QUERY` | every structure the query finds, one frame each (`limit=50`) |
| `optimade:ID` | `ID` in the default database (Preferences › OPTIMADE) |

`load("optimade:DB", filter='...')` sends an OPTIMADE filter as it is.

A query is a formula (`LiFePO4`, `Ca(OH)2`), a chemical system with exactly those elements
(`Li-P-S`), elements a structure must contain (`Li P S` or `Li,P,S`), or an OPTIMADE filter
(anything with `=`, `<`, `>` or a keyword such as `HAS`, `AND`).

## Databases

| Name | Database |
|---|---|
| `mp` | Materials Project |
| `cod`, `tcod` | Crystallography Open Database, Theoretical COD |
| `oqmd` | Open Quantum Materials Database |
| `alexandria`, `alexandria-pbesol` | Alexandria (PBE, PBEsol) |
| `nomad` | NOMAD |
| `mc3d`, `mc2d` | Materials Cloud three- and two-dimensional crystals |
| `jarvis` | JARVIS-DFT |
| `odbx` | open database of xtals |

Add others under Preferences › OPTIMADE › Extra databases, one `name = base URL` per line (the
URL without `/v1`), e.g. `mylab = https://optimade.mylab.org`. `python -m ewald_optimade
databases` lists them all.

## What a frame holds

Positions, elements and the cell. A direction that is not periodic (a molecule, a slab) gets a
box around the atoms with 10 Å of vacuum and is non-periodic. A partly occupied site shows its
majority element and gets the particle property `Occupancy`; site names that are not plain
elements (`Fe1`, mixed sites) are kept as `Species`. `attributes["OPTIMADE"]` holds the
database, id, address and the formulas the server gives.

## Side bar and AI

The OPTIMADE button on the activity bar opens a side bar: pick a database, type a query, then
double-click a hit to open it, **Insert cell** to add `pipe = load("optimade:...")` to the
notebook, or **Open all** for every hit as frames.

The AI gets one read-only tool, `optimade_search`. It searches only the databases above and
those you added; to open a structure it writes a notebook cell, as for every other change.

From a shell: `python -m ewald_optimade search Li-P-S --db mp [--json]`.

## Tests

`pytest packages/ewald-optimade/tests` runs against a small OPTIMADE server on 127.0.0.1, so
it needs no internet.
