"""EWALD plugin: open AiiDA results by PK or UUID, on this machine or another.

```python
from ewald import load
pipe = load("aiida:1234")                       # default profile, node PK 1234
pipe = load("aiida:myprofile/1234")             # another profile
pipe = load("aiida:3f9c2e1a")                   # UUID or its beginning
pipe = load("aiida:1234/relax/output_structure")  # follow output links
pipe = load("aiida:1234", what="structures")    # pick a view of a workflow
pipe = load("aiida://sim-agent@nurion/1234")    # the default profile of sim-agent on nurion
```

A node maps to frames as follows: ``StructureData`` is one frame, ``TrajectoryData`` one frame per
step, ``BandsData`` an electronic band structure, aiida-phonopy results phonon modes (through
ewald-phonopy), and a process (CalcJob, WorkChain, WorkGraph) is resolved to the first of
trajectory, phonons, bands, structures, input that it has (:data:`VIEWS`). Every frame carries
``attributes["AiiDA"]`` with the node's PK, UUID, type, label and process.

:mod:`ewald_aiida.export` reads the database (in this process, or on the remote host through
SSH, sent as ``python -c``); it only reads, and needs no daemon or RabbitMQ. :func:`tree` and
:func:`find` browse the provenance graph.
"""
from .browse import find, tree
from .export import VIEWS
from .uri import AiidaURI, parse

__all__ = ["AiidaURI", "VIEWS", "find", "parse", "tree"]
__version__ = "0.1.0"
