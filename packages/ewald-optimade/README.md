# ewald-optimade (moved into EWALD)

OPTIMADE support is built into EWALD since 2026-10-28: `load("optimade:mp/mp-149")`,
`from ewald.optimade import search`, the OPTIMADE side bar, the read-only AI tool
`optimade_search`, Preferences › OPTIMADE and `ewald optimade search|databases`. See EWALD's
manual, File formats › Structure databases (OPTIMADE).

Version 0.2 of this package registers nothing and only re-exports `ewald.optimade`, so scripts
with `from ewald_optimade import search` keep working. You can uninstall it:

```bash
pip uninstall ewald-optimade
```

An EWALD from before 2026-10-28 needs ewald-optimade 0.1.0 (commit `bf090ab` of this repository).
