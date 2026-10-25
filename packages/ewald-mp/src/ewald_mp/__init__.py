"""EWALD plugin: the Materials Project through mp-api, with your API key.

```python
from ewald import load
from ewald_mp import search

pipe = load("mp:mp-149")              # Si, the final structure
pipe = load("mp:mp-149/bands")        # with its band structure (table "Bands")
pipe = load("mp:mp-149/dos")          # density of states (table "DOS", projected per site)
pipe = load("mp:mp-149/chgcar")       # charge density grid, for isosurfaces and slices
pipe = load("mp:mp-149/relax")        # the relaxation, one frame per ionic step
search("Li-P-S", is_stable=True)      # hits: uri, formula, energy above hull, band gap
```

Set the key once under Preferences › Materials Project (kept in the system keychain). Structures
alone need no key through the OPTIMADE plugin (``load("optimade:mp/mp-149")``).
"""
__version__ = "0.1.0"

from .reader import VIEWS, parse  # noqa: E402
from .search import Hit, criteria, search  # noqa: E402

__all__ = ["Hit", "VIEWS", "criteria", "parse", "search"]
