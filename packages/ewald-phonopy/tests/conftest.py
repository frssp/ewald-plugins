import pytest
from ase.build import bulk

from ewald import DataCollection


@pytest.fixture
def cu_fcc():
    return DataCollection.from_ase(bulk("Cu", "fcc", a=3.615, cubic=True).repeat((4, 4, 4)))
