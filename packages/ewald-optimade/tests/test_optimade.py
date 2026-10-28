"""ewald-optimade 0.2 only re-exports ewald.optimade (its tests moved to EWALD's tests/test_optimade.py)."""
import importlib.metadata

import pytest

pytest.importorskip("ewald.optimade")


def test_names_are_the_core_ones():
    import ewald.optimade
    import ewald_optimade
    from ewald_optimade import providers, search

    assert search is ewald.optimade.search and providers is ewald.optimade.providers
    assert ewald_optimade.to_filter("Li-P-S") == 'elements HAS ALL "Li","P","S" AND nelements=3'


def test_registers_nothing():
    dist = importlib.metadata.distribution("ewald-optimade")
    assert not [ep for ep in dist.entry_points if ep.group.startswith("ewald.")]
