"""EWALD plugin (proof of concept): proteins.

```python
from ewald import load, view
from ewald_protein import SecondaryStructure

pipe = load("1ubq.cif")                       # residues, chains, atom names via gemmi
pipe.add(SecondaryStructure())                # helix / strand / coil per residue
view(pipe, visuals=["Cartoon"], show_atoms=False)
```
"""
__version__ = "0.0.1"

from .cartoon import CartoonVis  # noqa: E402
from .reader import ProteinReader  # noqa: E402
from .ss import SecondaryStructure  # noqa: E402

__all__ = ["CartoonVis", "ProteinReader", "SecondaryStructure"]
