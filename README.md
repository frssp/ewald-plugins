# EWALD plugin index

The list of plugins that EWALD's Plugins bar offers. Each plugin is one file in `plugins/`, and
`index.json` is generated from those files. EWALD reads `index.json` from this repository. To
read more indexes, such as a lab's own list, add their URLs under Preferences > Python > Plugin
catalogs.

This works the way Open VSX's `publish-extensions`, Homebrew taps and conda-forge feedstocks
do. A plugin's code stays in its own repository. This repository only records where each
release is and checks that it loads.

## First-party plugins

`packages/` holds plugins maintained with EWALD itself, for support tied to one outside code
(most of it used to be part of EWALD's core):

| Package | Plugin id | Adds |
|---|---|---|
| [ewald-phonopy](packages/ewald-phonopy) | `phonopy` | phonopy/VASP phonon readers, `PhononMode` |
| [ewald-plumed](packages/ewald-plumed) | `plumed` | `Plumed`, `LoadColvar`, `FreeEnergySurface`, two Claude tools |
| [ewald-aiida](packages/ewald-aiida) | `aiida` | `load("aiida:1234")`: AiiDA structures, trajectories, bands, workflows and aiida-phonopy results by PK/UUID (read-only) |

A release points the entry's `source` at a commit (or a tag `ewald-<name>-vX.Y.Z`) with
`#subdirectory=packages/ewald-<name>`, and bumps `version` in the entry, `pyproject.toml` and
`ewald-plugin.toml` together. Their tests run against an installed EWALD:
`pip install -e packages/ewald-phonopy && pytest packages/ewald-phonopy/tests`.

## Adding a plugin

1. Give the plugin a manifest so that EWALD knows its id and the versions it supports. A
   package uses `ewald-plugin.toml` plus an `ewald.plugins` entry point; a single file uses
   `__ewald__ = {...}` (see EWALD's docs/plugins/packaging.md). Tag a release.
2. Add `plugins/<id>.toml`:

   ```toml
   id = "cp2k"                       # = the plugin's id in EWALD (`ewald plugins`)
   name = "CP2K formats"
   summary = "Reads CP2K -pos-*.xyz trajectories"
   kinds = ["reader"]                # modifier reader writer visual overlay colormap theme tool
   source = "pip:git+https://github.com/OWNER/ewald-cp2k@v0.2.0"
   version = "0.2.0"
   requires_ewald = ">=0.1"
   author = "OWNER"
   homepage = "https://github.com/OWNER/ewald-cp2k"
   description = "Longer text shown on the plugin's page."   # optional
   tests = "https://raw.githubusercontent.com/OWNER/ewald-cp2k/v0.2.0/tests/test_readers.py"  # optional
   ```

   `source` must be pinned, so the index never changes under a user. Use one of
   - `pip:git+https://github.com/OWNER/REPO@TAG` (or a commit) for a package,
   - `pip:NAME==VERSION` for a PyPI release,
   - `https://raw.githubusercontent.com/OWNER/REPO/TAG/path/plugin.py` for a single file. EWALD
     copies it into the plugin folder.

   Branch names such as `main` are rejected.
3. Run `python scripts/build_index.py` and `python scripts/validate.py <id>` in a throwaway
   virtualenv with ewald installed, then open a pull request with the entry and `index.json`.

To update a plugin, change `source` and `version` in its entry. To remove one, delete the file
and rebuild `index.json`.

## Checks

`scripts/build_index.py` checks every entry's fields and the source pin, then writes
`index.json`. `--check` only reports when the file is stale. `scripts/validate.py` installs each
entry into a scratch EWALD config folder and checks the following:

- the plugin loads (`plugins.installed()` state "loaded");
- its `requires-ewald` matches;
- it registers something of every kind it lists;
- its `tests`, when given, pass.

Private sources need `GITHUB_TOKEN`, or `--from-git OWNER/REPO=PATH` with a local clone. The
GitHub workflow runs both checks and is started by hand. It needs the `EWALD_TOKEN` secret,
with read access to frssp/ewald.

## index.json

```json
{"format": 1, "plugins": [{"id": "...", "name": "...", "summary": "...", "kinds": ["reader"],
  "source": "pip:git+https://github.com/...@v0.2.0", "version": "0.2.0",
  "requires_ewald": ">=0.1", "author": "...", "homepage": "...", "description": "...", "tests": "..."}]}
```

These are the `Entry` fields of `ewald.plugin_catalog`, plus `id` and `requires_ewald`. EWALD
uses `id` to match an entry with an installed plugin, and `version` to offer updates. Entries
are trusted only as far as this repository's review goes: installing one runs its code with
your user's rights, as with VS Code extensions.
