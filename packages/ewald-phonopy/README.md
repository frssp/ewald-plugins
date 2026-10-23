# ewald-phonopy

EWALD plugin `phonopy`: phonon bands that phonopy computes from force constants. Since
2026-10-23 EWALD itself reads phonopy band.yaml / mesh.yaml / qpoints.yaml and VASP OUTCARs of
IBRION = 5-8 runs and has the `PhononMode` animation; this plugin adds what needs the phonopy
package.

```bash
pip install 'git+https://github.com/frssp/ewald-plugins#subdirectory=packages/ewald-phonopy'
```

| Reader | Files |
|---|---|
| `phonopy-fc` | `phonopy.yaml` / `phonopy_params.yaml` / `phonopy_disp.yaml` with `FORCE_SETS` or `FORCE_CONSTANTS`: phonopy computes the bands with eigenvectors along the seekpath path |

```python
from ewald import import_file
from ewald.modifiers import PhononMode

pipe = import_file("phonopy_disp.yaml", frames=24)   # FORCE_SETS next to it; 24 frames = one period
pipe.modifiers.append(PhononMode(qpoint=50, band=3, amplitude=0.3))
```

A `phonopy.Phonopy` with force constants (for example aiida-phonopy's
`get_phonopy_instance()`) becomes a pipeline with `from_phonopy(phonon, frames=24, band_path=None,
labels=None)`, the seekpath path or your own segments; `reader_from_phonopy` gives the reader and
`modes_from_phonopy` the `PhononModes`. `EXAMPLES / "Cu3Au_band.yaml"` is an example band
structure with eigenvectors. The 0.2 names (`ewald_phonopy.PhononMode`, `ewald_phonopy.phonon`,
`PhonopyYamlReader`, ...) still import; they are EWALD's own now.

Version 0.3 needs an EWALD from 2026-10-23 or later; with an older EWALD use 0.2.2. Manual:
EWALD's docs/user/phonons.md.

Tests: `pip install -e . && pytest tests` (with EWALD installed).
