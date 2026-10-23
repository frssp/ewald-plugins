"""Example UI theme plugin: "Phosphor", a green-on-black CRT terminal look for the desktop app.

It sets every kind of key a ``@ui_theme`` may return, so it doubles as a test of the theme API:

- colors: all design tokens (phosphor green accents, amber data, near-black panels and 3D view);
- fonts: JetBrains Mono for the whole UI and the editors (bundled with ewald, so it looks the
  same on Windows, macOS and Linux);
- shape: square corners (``radius`` 0), roomy spacing (``density`` "comfortable") and bold
  icons (``icon_stroke`` 2.2);
- extra style sheet rules (``qss``): dashed panel-header rules, a glowing bar on the current
  cell and green text selection.

Install it from the Plugins side bar (search "Phosphor") or copy this file into ewald's plugin
folder (``ewald plugins`` prints where it is), then pick it under Preferences > General > UI
theme, or from Python::

    from ewald import settings

    s = settings.load()
    s["general.ui_theme"] = "Phosphor"
    s.save()

See docs/plugins/styles.md#ui-themes in ewald.
"""
from ewald.plugin_api import ui_theme


@ui_theme(name="Phosphor", base="graphite")
def phosphor():
    """Green-on-black CRT terminal: monospace text, square corners, bold icons, amber data."""
    return {
        "bg": "#050A06", "panel": "#08110A", "raised": "#0D1A10", "border": "#1E4A2A",
        "text": "#B6F5C2", "secondary": "#86DB98", "muted": "#5FA770",
        "accent": "#33FF66", "on_accent": "#021006", "accent_soft": "#103A1C",
        "data": "#FFB000", "data_soft": "#3A2A05",
        "selection": "#E6FF4D", "pick": "#FF4FD8", "error": "#FF5555", "ok": "#33FF66",
        "viewport": "#020503",
        "hover": "#123019", "pressed": "#184021", "accent_hover": "#7DFF9C", "accent_pressed": "#22C24C",
        # beyond colors
        "font": "JetBrains Mono", "mono_font": "JetBrains Mono", "font_size": 12,
        "radius": 0, "density": "comfortable", "icon_stroke": 2.2,
        # applied after ewald's own rules; $token is a color of this theme
        "qss": (
            "QWidget#panelHeader { border-bottom: 1px dashed $accent; }\n"
            "QFrame#cell[current=\"true\"] { border-left: 3px solid $accent; }\n"
            "QPlainTextEdit, QTextEdit, QLineEdit { selection-background-color: $accent;"
            " selection-color: $on_accent; }\n"
        ),
    }


__ewald__ = {"plugin_api": 1}   # plugin manifest: written for ewald.plugin_api version 1
