"""EWALD plugin: open AiiDA results by PK or UUID.

```python
from ewald import load
pipe = load("aiida:1234")                       # default profile, node PK 1234
pipe = load("aiida:myprofile/1234")             # another profile
pipe = load("aiida:3f9c2e1a")                   # UUID or its beginning
pipe = load("aiida:1234/relax/output_structure")  # follow output links
pipe = load("aiida:1234", what="structures")    # pick a view of a workflow
```

A node maps to frames as follows: ``StructureData`` is one frame, ``TrajectoryData`` one frame per
step, ``BandsData`` an electronic band structure, aiida-phonopy results phonon modes (through
the phonopy reader of EWALD / ewald-phonopy), and a process (CalcJob, WorkChain, WorkGraph) is
resolved to the first of trajectory, phonons, bands, structures, input that it has
(:data:`VIEWS`). Every frame carries ``attributes["AiiDA"]`` with the node's PK, UUID, type,
label and process.

The plugin only reads: it never stores, submits or changes nodes, and needs no daemon or
RabbitMQ. :func:`tree` and :func:`find` browse the provenance graph.
"""
from .browse import find, tree
from .nodes import VIEWS, resolve
from .uri import AiidaURI, parse

__all__ = ["AiidaURI", "VIEWS", "find", "parse", "resolve", "tree"]
__version__ = "0.1.0"
