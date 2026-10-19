# ewald-plumed

EWALD plugin `plumed`: PLUMED collective variables over a trajectory, COLVAR files, metadynamics
free energy surfaces and two Claude tools (`compute_plumed_cvs`, `read_plumed_output`). It was
part of EWALD's core until 2026-10-19; scripts written then keep working once it is installed
(`from ewald.modifiers import Plumed`, `import ewald.plumed`).

```bash
pip install 'git+https://github.com/frssp/ewald-plugins#subdirectory=packages/ewald-plumed'
conda install -c conda-forge plumed py-plumed     # only for Plumed / compute_plumed_cvs
```

```python
from ewald import import_file
from ewald.modifiers import FreeEnergySurface, Plumed

pipe = import_file("dump.lammpstrj")
pipe.modifiers.append(Plumed("d: DISTANCE ATOMS=1,2\nphi: TORSION ATOMS=5,7,9,15", time_per_frame=0.1))
pipe.modifiers.append(FreeEnergySurface("HILLS", bins=(60, 60)))
```

`LoadColvar`, `FreeEnergySurface`, `ewald_plumed.plumed.fes_from_hills` and
`read_plumed_output` need no PLUMED library. With a source build, install the binding with
`pip install plumed` (or this package's `[engine]` extra) and set
`PLUMED_KERNEL=<prefix>/lib/libplumedKernel.so`. Manual: EWALD's docs/user/plumed.md.

Tests: `pip install -e . && pytest tests`; the ones that run PLUMED skip without it, and compare
with `plumed driver` and the `sum_hills` files in `tests/data/` (regenerate with
`tests/data/make_plumed_reference.py`, never by hand).
