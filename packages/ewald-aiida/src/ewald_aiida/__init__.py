"""EWALD plugin: open AiiDA results by PK or UUID, on this machine or another.

```python
from ewald import load
pipe = load("aiida:1234")                       # default profile, node PK 1234
pipe = load("aiida:myprofile/1234")             # another profile
pipe = load("aiida:3f9c2e1a")                   # UUID or its beginning
pipe = load("aiida:1234/relax/output_structure")  # follow output links
pipe = load("aiida:1234", what="structures")    # pick a view of a workflow
pipe = load("aiida://alice@cluster/1234")    # the default profile of alice on cluster
wf = open_archive("wf.aiida")                  # an AiiDA archive, read-only, no database server
```

A node maps to frames as follows: ``StructureData`` is one frame, ``TrajectoryData`` one frame per
step, ``BandsData`` an electronic band structure, aiida-phonopy results phonon modes (through
ewald-phonopy), and a process (CalcJob, WorkChain, WorkGraph) is resolved to the first of
trajectory, phonons, bands, structures, input that it has (:data:`VIEWS`). Every frame carries
``attributes["AiiDA"]`` with the node's PK, UUID, type, label and process.

:mod:`ewald_aiida.export` reads the database (in this process, or on the remote host through
SSH, sent as ``python -c``); it only reads, and needs no daemon or RabbitMQ. An archive
(:mod:`ewald_aiida.archives`) is a profile of its own, ``aiida:archive-<digest>/NODE``. Each step
of a described workflow carries ``inputs``, ``files`` and a ``shape`` (:mod:`ewald_aiida.shape`:
what it computed, from its inputs) for analyses that find steps by what they did. :func:`tree` and
:func:`find` browse the provenance graph.
"""
from .archives import retrieved_file
from .browse import find, tree
from .export import VIEWS
from .source import open_archive
from .uri import AiidaURI, parse

__all__ = ["AiidaURI", "VIEWS", "find", "open_archive", "parse", "retrieved_file", "tree"]
__version__ = "0.2.0"
