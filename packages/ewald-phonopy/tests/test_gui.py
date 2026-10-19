"""The GUI with the plugin: band plot picks a mode, phonon files open playing one (needs PySide6;
the main-window test needs an X display with OpenGL, e.g. xvfb-run)."""
import os
from pathlib import Path

import pytest

QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from ewald import import_file  # noqa: E402
from ewald import modifiers as mods  # noqa: E402

DATA = Path(__file__).parent / "data"


@pytest.fixture(scope="module")
def app():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app
    import gc

    for w in QtWidgets.QApplication.topLevelWidgets():
        w.close()
        w.deleteLater()
    app.processEvents()
    gc.collect()


def test_phonon_band_plot_click_picks_mode(app):
    from matplotlib.backend_bases import MouseEvent

    from ewald.gui.plots import PlotsPanel

    pipe = import_file(DATA / "band.yaml", frames=4)
    pipe.modifiers.append(mods.PhononMode(qpoint=4, band=5))
    panel = PlotsPanel()
    panel.resize(600, 400)
    panel.set_data(pipe.compute(0))
    ax = panel.figure.axes[0]
    assert panel.table.currentText() == "Phonon Bands" and ax.get_ylabel() == "Frequency (THz)"
    assert [t.get_text() for t in ax.get_xticklabels()] == ["$\\Gamma$", "X", "M", "$\\Gamma$", "R"]
    modes = pipe.source_frame(0).attributes["Phonon Modes"]
    assert list(panel._marker.get_ydata()) == [modes.frequencies[4, 5]]
    panel.set_data(pipe.compute(1))
    assert panel.figure.axes[0] is ax  # next frame of the animation: no redraw
    picked = []
    panel.phononModePicked.connect(lambda q, b: picked.append((q, b)))
    panel.canvas.draw()
    x, y = ax.transData.transform((modes.distances[12], modes.frequencies[12, 9]))
    panel._clicked(MouseEvent("button_press_event", panel.canvas, x, y, button=1))
    assert picked == [(12, 9)]


@pytest.mark.skipif(not os.environ.get("DISPLAY"), reason="main window needs an X display with OpenGL (xvfb-run)")
def test_main_window_plays_phonon_mode(app):
    from ewald.gui.app import MainWindow

    w = MainWindow()
    pipe = w.open_file(DATA / "OUTCAR.phonon")
    assert [type(m).__name__ for m in pipe.modifiers] == ["PhononMode"]  # added on open
    assert w.data.attributes["Phonon.Band"] == 3 and "Phonon Mode" in w.data.vectors
    w.play_phonon_mode(0, 9)
    assert pipe.modifiers[0].band == 9 and w.data.attributes["Phonon.Band"] == 9
    assert w.timeline.play.isChecked()
    w.timeline.play.setChecked(False)
    menu = {a.text(): a for a in w.viewport_menu().actions()}
    assert "Phonon band structure" in menu and "Play" in menu
    w.close()
