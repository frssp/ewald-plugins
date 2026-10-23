"""The Phosphor UI theme loads, keeps every key within the theme API and restyles the window.

Runs against an installed ewald: from this repository (``pytest tests/test_phosphor_theme.py``)
or as the index entry's ``tests`` file in ``scripts/validate.py``, where the plugin is already
installed in the scratch config folder.
"""
import importlib.util
from pathlib import Path

import pytest

plugins = pytest.importorskip("ewald.plugins")

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "phosphor_theme.py"


@pytest.fixture
def phosphor():
    found = plugins.ui_themes().get("Phosphor")
    if found is None:   # run from this repository: register the example file directly
        spec = importlib.util.spec_from_file_location("phosphor_theme", EXAMPLE)
        spec.loader.exec_module(importlib.util.module_from_spec(spec))
        found = plugins.ui_themes()["Phosphor"]
    return found


def test_palette_sets_every_token(phosphor):
    from ewald.ui_tokens import PALETTES

    palette = phosphor.palette()
    assert set(palette) == set(PALETTES["graphite"])
    assert palette["accent"] == "#33FF66" and palette["viewport"] == "#020503"
    # the theme overrides every token of its base, so it is not just a recolored Graphite
    assert all(palette[k] != v for k, v in PALETTES["graphite"].items())


def test_style_goes_beyond_colors(phosphor):
    style = phosphor.style()
    assert style["font"] == style["mono_font"] == "JetBrains Mono"
    assert (style["radius"], style["density"], style["icon_stroke"]) == (0, "comfortable", 2.2)
    assert "$accent" in style["qss"]


def test_window_stylesheet_uses_it(phosphor):
    pytest.importorskip("PySide6")
    from ewald.gui import theme

    try:
        theme.use("Phosphor")
        css = theme.stylesheet(12)
        assert '"JetBrains Mono", "IBM Plex Sans"' in css
        assert "border-bottom: 1px dashed #33FF66" in css   # $accent filled in
        assert "#08110A" in css                             # panel color
    finally:
        theme.use("graphite")
