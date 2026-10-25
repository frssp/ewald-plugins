"""EWALD plugin: search and open structures of OPTIMADE databases (no account or key needed).

```python
from ewald import load
from ewald_optimade import search

pipe = load("optimade:mp/mp-149")          # Materials Project, Si
pipe = load("optimade:cod/1000041")        # Crystallography Open Database
pipe = load("optimade:oqmd?Li-P-S")        # every Li-P-S structure found (one frame each)
search("LiFePO4", db="mp")                 # hits: uri, formula, nsites
search('elements HAS ALL "Si","O" AND nsites<=6', db="cod")
```

Databases go by short names (:data:`providers.BUILTIN`: mp, cod, tcod, oqmd, alexandria, nomad,
mc3d, mc2d, jarvis, odbx); more under Preferences › OPTIMADE. Every frame carries
``attributes["OPTIMADE"]`` (database, id, formula, address). The OPTIMADE side bar searches and
opens; the AI gets a read-only ``optimade_search`` tool.
"""
__version__ = "0.1.0"

from .providers import BUILTIN, Provider  # noqa: E402
from .providers import providers as databases  # noqa: E402
from .query import to_filter  # noqa: E402
from .search import Hit, search  # noqa: E402
from .uri import OptimadeURI, parse  # noqa: E402

__all__ = ["BUILTIN", "Hit", "OptimadeURI", "Provider", "databases", "parse", "search", "to_filter"]
