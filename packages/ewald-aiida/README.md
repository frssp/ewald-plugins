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
pipe = load("aiida://alice@cluster/1234")       # AiiDA on another machine, over SSH
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
| aiida-phonopy `PhonopyData`/`ForceConstantsData` | phonon modes through ewald-phonopy (`reader_from_phonopy`), along the path of the workflow's `phonon_bands` output (else seekpath) |
| a process: CalcJob, WorkChain, WorkGraph | the first of: its trajectory (else its called calculations' trajectories, joined in call order), phonons, bands, structures, input structure |

Every frame has `attributes["AiiDA"]` (`pk`, `uuid`, `node_type`, `label`, `process_label`,
`exit_status`, `view`, `output_pk`, `calc_pk`), and the numbers of the process's `Dict` outputs
(`energy`, `fermi_energy`, ...) as attributes.

## AiiDA on another machine

`aiida://[user@]host[:port]/[profile/]NODE[/link...]` reads a profile on a remote host, for
example the profile of the `alice` account on a cluster. `host` can be a `~/.ssh/config`
alias, and keys, ssh-agent, jump hosts and known_hosts work as for EWALD's other remote files.
Nothing is installed on the host: EWALD sends the read-only exporter
([export.py](src/ewald_aiida/export.py), standard library, numpy, aiida-core) as `python -c`,
using the Python that `verdi` runs with there (found through a login shell, so conda and
`module load` setups apply). Pass `python="/path/to/env/bin/python"` or set
`EWALD_AIIDA_PYTHON` when that guess is wrong. Results come back as one compressed npz;
nodes named by full UUID are cached locally once their process has finished.

To read another account's profile you need that account's SSH login (simplest), or read
access to its `~/.aiida` configuration, its file repository and its database (a read-only
PostgreSQL role) from your own account.

## In the GUI: the AiiDA side bar

The **AiiDA** button on EWALD's activity bar opens a side bar with the profile's whole
workflows (processes nobody called), newest first; type a PK to jump to one or words to search
process labels, labels and descriptions. Expanding a workflow lists the processes it called,
nested, with their structures, trajectories and bands; a restart workchain's `iteration_NN`
calculations are one step with a run count. A double click opens a step or output, and on a
workflow opens it as one notebook with a `load` cell per step and `pipe` on its main result.
Edit › Plugin settings › AiiDA sets where the profile is: a host (empty: this machine), a
profile (empty: the default) and the Python that runs `verdi` on the host. EWALD's AI tools
`list_workflows` and `describe_workflow` read the same. The side bar is EWALD's workflow side
bar (`ewald.workflow`); this plugin is its source (`ewald_aiida.source.AiidaWorkflows`, which
runs `export.py describe` / `find --page` where the profile is). It needs an EWALD with
workflow sources.

## Browsing

```bash
python -m ewald_aiida tree 1234              # called processes and outputs, with PKs
python -m ewald_aiida find --process 'Pw%'   # recent processes; --ok, --json, --profile
python -m ewald_aiida find --host alice@cluster --process 'Phonopy%'
python -m ewald_aiida tree aiida://alice@cluster/1234
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
forces), and checks that loading changes nothing in the database. The remote path is tested by
running the exact `python -c` command the SSH host would get against that profile.
