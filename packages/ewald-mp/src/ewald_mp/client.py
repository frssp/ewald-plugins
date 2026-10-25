"""The Materials Project connection: the API key and an ``mp_api`` ``MPRester``.

The key is a secret field of the settings page (Preferences › Materials Project), so EWALD keeps
it in the operating system's keychain (``plugin:mp:api_key``), never in a settings file or the
environment. Without one there, mp-api's own places are used (``MP_API_KEY``, ``~/.pmgrc.yaml``),
so a key you already set up for pymatgen works too.
"""
from __future__ import annotations

from ewald.plugin_api import SettingsField

KEY_URL = "https://next-gen.materialsproject.org/api"


class MPSettings:
    """Your Materials Project API key."""

    title = "Materials Project"
    fields = (
        SettingsField("api_key", "API key", kind="secret",
                      help=f"From {KEY_URL} (log in, then API key). Stored in the system keychain."),
        SettingsField("page_size", "Results per search", kind="int", default=25),
    )


class MPKeyError(RuntimeError):
    """No API key, or the Materials Project refused it."""


def settings() -> dict:
    try:
        from ewald.plugin_api import plugin_settings

        return plugin_settings("mp")
    except KeyError:      # the settings page is switched off or not registered
        return {}


def api_key() -> str | None:
    key = settings().get("api_key")
    return key if isinstance(key, str) and key.strip() else None


def page_size() -> int:
    return max(1, min(int(settings().get("page_size") or 25), 500))


def rester():
    """A new ``MPRester`` with the stored key (tests replace this function)."""
    try:
        from mp_api.client import MPRester
    except ImportError as exc:
        raise ImportError("the Materials Project plugin needs mp-api: pip install mp-api") from exc
    try:
        return MPRester(api_key(), mute_progress_bars=True)
    except Exception as exc:  # noqa: BLE001 (mp-api raises its own MPRestError for a missing key)
        if "api_key" in str(exc).lower() or "api key" in str(exc).lower():
            raise MPKeyError(f"no Materials Project API key: set it under Preferences › Materials Project "
                             f"(get one at {KEY_URL})") from None
        raise


def call(fn):
    """``fn(mpr)`` with an open ``MPRester``; a refused key says where to set it."""
    mpr = rester()
    try:
        if hasattr(mpr, "__enter__"):
            with mpr:
                return fn(mpr)
        return fn(mpr)
    except Exception as exc:  # noqa: BLE001
        text = str(exc)
        if any(s in text for s in ("401", "403", "Unauthorized", "invalid API key", "API key")):
            raise MPKeyError(f"the Materials Project refused the API key ({text.splitlines()[0][:200]}); "
                             "check it under Preferences › Materials Project") from None
        raise
