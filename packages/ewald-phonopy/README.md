# ewald-phonopy

EWALD plugin `phonopy`: phonon modes from phonopy and VASP, and the `PhononMode` animation. It
was part of EWALD's core until 2026-10-19; scripts written then keep working once it is
installed (`from ewald.modifiers import PhononMode`, `import ewald.phonon`).

```bash
pip install 'git+https://github.com/frssp/ewald-plugins#subdirectory=packages/ewald-phonopy'
```

```python
from ewald import import_file
from ewald.modifiers import PhononMode
from ewald_phonopy import EXAMPLES

pipe = import_file(EXAMPLES / "Cu3Au_band.yaml", frames=24)   # 24 frames = one period
pipe.modifiers.append(PhononMode(qpoint=50, band=3, amplitude=0.3))
```

| Reader | Files |
|---|---|
| `phonopy` | `band.yaml`, `mesh.yaml`, `qpoints.yaml` with eigenvectors |
| `vasp-phonon` | OUTCAR of an IBRION = 5-8 run (Gamma-point modes) |
| `phonopy-fc` | `phonopy.yaml` / `phonopy_params.yaml` / `phonopy_disp.yaml` with `FORCE_SETS` or `FORCE_CONSTANTS`: phonopy computes the bands with eigenvectors along the seekpath path |

The GUI draws the "Phonon Bands" table as a band structure (click a band to play that mode)
and opens phonon files playing a mode. Manual: EWALD's docs/user/phonons.md.

Tests: `pip install -e . && pytest tests` (with ewald installed; `test_gui.py` needs PySide6 and
`xvfb-run` for the main-window test).
