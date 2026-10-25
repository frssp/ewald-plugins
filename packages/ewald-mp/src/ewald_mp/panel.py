"""The Materials Project side bar: type a formula, ``Li-P-S``, ``Li P S`` or ``mp-149``, pick what to
open (structure, bands, DOS, charge density, relaxation) and open it. A double click (or Open)
opens it as File › Open from › Location does; Insert cell adds ``pipe = load("mp:...")`` to the
notebook without running it. Searches run off the GUI thread."""
from __future__ import annotations

#: a database cylinder, drawn with currentColor for the UI theme
ICON = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">'
        '<ellipse cx="12" cy="5.5" rx="7" ry="2.5"/><path d="M5 5.5v13c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5v-13"/>'
        '<path d="M5 12c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5"/></svg>')

#: what the view box offers: label -> the suffix of the mp: path
VIEWS = {"Structure": "", "Band structure": "/bands", "Density of states": "/dos",
         "Bands + DOS": "/electronic", "Charge density": "/chgcar", "Relaxation": "/relax"}


def materials_project(context):
    """Materials Project: search materials and open structures, bands, DOS, charge densities."""
    return MPPanel(context)


materials_project.title = "Materials Project"
materials_project.icon = ICON
materials_project.tooltip = "Materials Project: search materials (needs your API key)"


def MPPanel(context, parent=None):
    from PySide6 import QtCore, QtWidgets

    from . import client
    from .search import search

    try:
        from ewald.gui.workers import detach
    except ImportError:          # older ewald
        def detach(thread):
            return thread

    HIT = QtCore.Qt.UserRole
    COLUMNS = ["Formula", "Id", "Space group", "E hull", "Gap"]

    class _Job(QtCore.QThread):
        done = QtCore.Signal(object, str)

        def __init__(self, fn):
            super().__init__()
            self.fn = fn

        def run(self):
            try:
                self.done.emit(self.fn(), "")
            except Exception as exc:  # noqa: BLE001 (a failed search shows in the side bar, never a crash)
                self.done.emit(None, str(exc))

    class Panel(QtWidgets.QWidget):
        def __init__(self):
            super().__init__(parent)
            self.context = context
            self.jobs = []
            lay = QtWidgets.QVBoxLayout(self)
            lay.setContentsMargins(8, 8, 8, 8)
            lay.setSpacing(6)
            head = QtWidgets.QHBoxLayout()
            self.who = QtWidgets.QLabel(objectName="muted", wordWrap=True)
            head.addWidget(self.who, 1)
            self.key_button = QtWidgets.QToolButton(text="API key…", toolTip="Set your Materials Project API key")
            self.key_button.clicked.connect(lambda: context.open_preferences("Materials Project"))
            head.addWidget(self.key_button)
            lay.addLayout(head)
            row = QtWidgets.QHBoxLayout()
            self.search = QtWidgets.QLineEdit(placeholderText="LiFePO4, Li-P-S, Li P S or mp-149")
            self.search.setClearButtonEnabled(True)
            self.search.returnPressed.connect(self.run_search)
            row.addWidget(self.search, 1)
            go = QtWidgets.QToolButton(text="Search")
            go.clicked.connect(self.run_search)
            row.addWidget(go)
            lay.addLayout(row)
            self.stable = QtWidgets.QCheckBox("Only stable (on the hull)")
            lay.addWidget(self.stable)
            self.tree = QtWidgets.QTreeWidget(objectName="mpResults", columnCount=len(COLUMNS), rootIsDecorated=False)
            self.tree.setHeaderLabels(COLUMNS)
            self.tree.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
            self.tree.itemDoubleClicked.connect(lambda *_: self.open())
            self.tree.itemSelectionChanged.connect(self._selected)
            lay.addWidget(self.tree, 1)
            view_row = QtWidgets.QHBoxLayout()
            view_row.addWidget(QtWidgets.QLabel("Open"))
            self.view = QtWidgets.QComboBox(toolTip="What to open of the selected material")
            for label, suffix in VIEWS.items():
                self.view.addItem(label, suffix)
            view_row.addWidget(self.view, 1)
            lay.addLayout(view_row)
            buttons = QtWidgets.QHBoxLayout()
            self.buttons = {}
            for text, slot, tip in (("Open", self.open, "Open the selected material (double click does the same)"),
                                    ("Insert cell", self.insert_cell, 'A notebook cell pipe = load("mp:..."), not run')):
                b = QtWidgets.QPushButton(text, toolTip=tip)
                b.clicked.connect(lambda _=False, slot=slot: slot())
                b.setEnabled(False)
                buttons.addWidget(b)
                self.buttons[text] = b
            lay.addLayout(buttons)
            self.note = QtWidgets.QLabel(objectName="muted", wordWrap=True)
            self.note.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
            lay.addWidget(self.note)
            self.refresh_account()
            context.on("settings", lambda _s: self.refresh_account())

        def refresh_account(self):
            try:
                has_key = bool(client.api_key())
            except Exception:  # noqa: BLE001 (no keychain: mp-api's own config may still hold a key)
                has_key = False
            self.who.setText("API key set" if has_key else
                             f"No API key yet: get one at {client.KEY_URL}")

        # -------------------------------------------------------------- search
        def run_search(self):
            text = self.search.text().strip()
            filters = {"is_stable": True} if self.stable.isChecked() else {}
            self._say("Searching…")
            self.tree.clear()
            for b in self.buttons.values():
                b.setEnabled(False)
            job = detach(_Job(lambda: search(text, **filters)))
            job.done.connect(self._show)
            job.finished.connect(lambda: self.jobs.remove(job) if job in self.jobs else None)
            self.jobs.append(job)
            job.start()

        def wait(self, ms: int = 10000):
            """Block until every search has answered (tests, screenshots)."""
            while self.jobs:
                self.jobs[0].wait(ms)
                QtWidgets.QApplication.processEvents()

        def _show(self, results, error):
            if error:
                self._say(error, error=True)
                return
            for h in results:
                item = QtWidgets.QTreeWidgetItem([
                    h.formula, h.material_id, h.spacegroup,
                    "" if h.energy_above_hull is None else f"{h.energy_above_hull:.3f}",
                    "" if h.band_gap is None else f"{h.band_gap:.2f}"])
                item.setData(0, HIT, h)
                item.setToolTip(0, h.uri)
                self.tree.addTopLevelItem(item)
            for col in range(len(COLUMNS)):
                self.tree.resizeColumnToContents(col)
            self._say(f"{len(results)} found, most stable first · E hull in eV/atom, gap in eV" if results
                      else "Nothing found")

        def _selected(self):
            n = len(self.selected())
            self.buttons["Open"].setEnabled(n == 1)
            self.buttons["Insert cell"].setEnabled(n >= 1)

        def selected(self):
            return [it.data(0, HIT) for it in self.tree.selectedItems() if it.data(0, HIT) is not None]

        def path(self, hit) -> str:
            return hit.uri + (self.view.currentData() or "")

        # -------------------------------------------------------------- actions
        def open(self):
            hits = self.selected()
            if len(hits) == 1:
                self.context.open(self.path(hits[0]))

        def insert_cell(self):
            hits = self.selected()
            if not hits:
                return
            if len(hits) == 1:
                code = f'pipe = load("{self.path(hits[0])}")  # {hits[0].formula}'
            else:
                names = [h.material_id.replace("-", "_") for h in hits]
                code = "\n".join(f'{n} = load("{self.path(h)}")  # {h.formula}' for n, h in zip(names, hits))
                code += f"\npipe = {names[0]}"
            self.context.insert_cell(code)

        def _say(self, text, error=False):
            self.note.setText(text)
            self.note.setObjectName("cellError" if error else "muted")
            self.note.style().polish(self.note)

    return Panel()
