# ewald-aiida

Open AiiDA results in EWALD by PK or UUID. The plugin reads the profile you already use with
`verdi`; it never stores, submits or changes nodes, and needs no daemon or RabbitMQ.

```bash
pip install "ewald-aiida @ git+https://github.com/frssp/ewald-plugins#subdirectory=packages/ewald-aiida"
pip install "ewald-aiida[phonopy] @ ..."    # + phonon modes of aiida-phonopy results (ewald-phonopy)
```

```python
from ewald import load

pipe = load("aiida:1234")                          # default profile, node PK 1234
pipe = load("aiida:myprofile/1234")                # another profile
pipe = load("aiida:3f9c2e1a")                      # a UUID or its beginning: the same node on any machine
pipe = load("aiida:1234/iteration_01/output_structure")   # follow links (called steps, outputs)
pipe = load("aiida:1234", what="structures")       # trajectory | phonons | bands | structures | input
```

The same strings work on the command line (`ewald gui aiida:1234`, `ewald render aiida:1234`),
in the GUI's notebook cells, and in saved sessions and `.ewd` notebooks, which store only the
string. Prefer the UUID form for notebooks you share, since PKs differ between databases.

## What a node becomes

| Node | Frames |
|---|---|
| `StructureData` | one frame (kinds such as `Fe1`/`Fe2` kept in the `Kind` property) |
| `TrajectoryData` | one frame per step; forces and velocities as `Force`/`Velocity`, per-step arrays (energy, ...) as attributes, `Timestep`/`Time` |
| electronic `BandsData` | the structure, with `Electronic Structure`, the `Bands` table, Fermi energy and band gap (as from vasprun.xml) |
| aiida-phonopy `PhonopyData`/`ForceConstantsData` | phonon modes through the `phonopy` reader of ewald-phonopy, along the path of the workflow's `phonon_bands` output (else seekpath) |
| a process: CalcJob, WorkChain, WorkGraph | the first of: its trajectory (else its called calculations' trajectories, joined in call order), phonons, bands, structures, input structure |

Every frame has `attributes["AiiDA"]` (`pk`, `uuid`, `node_type`, `label`, `process_label`,
`exit_status`, `view`, `output_pk`, `calc_pk`), and the numbers of the process's `Dict` outputs
(`energy`, `fermi_energy`, ...) as attributes.

## Browsing

```bash
python -m ewald_aiida tree 1234              # called processes and outputs, with PKs
python -m ewald_aiida find --process 'Pw%'   # recent processes; --ok, --json, --profile
```

```text
PwRelaxWorkChain <2> [finished, exit 0]  -> load("aiida:2") opens trajectory
├─ output_structure: StructureData <9> Si2
├─ iteration_01: PwCalculation <3> [finished, exit 0]
│  ├─ output_trajectory: TrajectoryData <4> 3 steps
...
```

`ewald_aiida.tree(pk)` and `ewald_aiida.find(...)` return the same from Python.

## Security

The plugin only reads. For a shared PostgreSQL database, give the profile a read-only database
role. An `aiida:` string in a notebook you received reads from your own profiles only.

## Tests

`pytest packages/ewald-aiida/tests` builds a throwaway in-memory SQLite profile with a relaxation
WorkChain (two restarts), an electronic band structure and an aiida-phonopy result (Cu, EMT
forces), and checks that loading changes nothing in the database.
