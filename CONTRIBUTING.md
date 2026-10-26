# Contributing to the EWALD plugins

This repository holds two things: the plugin index (`plugins/*.toml`, built into `index.json`)
and the first-party plugins in `packages/`. Everything general (setting up EWALD, the
Windows/macOS/Linux rules, how design decisions are recorded, security reports, the code of
conduct) is in EWALD's own
[CONTRIBUTING.md](https://github.com/frssp/ewald/blob/main/CONTRIBUTING.md) and applies here too.

## Listing a plugin

Follow [Adding a plugin](README.md#adding-a-plugin): one `plugins/<id>.toml` with a pinned
`source` (a tag or commit, never a branch; a single file also needs its `sha256`), then

```bash
python scripts/build_index.py
python scripts/validate.py <id>     # in a throwaway virtualenv with ewald installed
```

and open a pull request with the entry and the rebuilt `index.json`. Installing a listed plugin
runs its code with the user's rights, so say what the plugin does and link its source.

## Changing a first-party plugin

```bash
pip install -e packages/ewald-<name>
pytest packages/ewald-<name>/tests
pytest tests                        # the index scripts
```

A release bumps `version` in `pyproject.toml`, `ewald-plugin.toml` and the index entry together
and points `source` at the new commit or tag. Pull requests here are merged with a merge commit,
not squashed, because the index pins commits.
