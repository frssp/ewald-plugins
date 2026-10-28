"""The Materials Project connection: the API key and the client the reader and search talk to.

Without mp-api that is :class:`ewald_mp.rest.Rester` (the REST API and MP's open data through
urllib, nothing else to install); with mp-api installed (``ewald-mp[full]``) and "Use mp-api when
it is installed" on, an ``mp_api`` ``MPRester``, which also reads relaxation trajectories and the
newest band structures and DOS from MP's Delta tables. Both answer the same calls.

The key is a secret field of the settings page (Preferences › Materials Project), so EWALD keeps
it in the operating system's keychain (``plugin:mp:api_key``), never in a settings file or the
environment. Without one there, mp-api's own places are used (``MP_API_KEY``, ``~/.pmgrc.yaml``),
so a key you already set up for pymatgen works too.

With mp-api: it talks through requests and boto3, which trust only certifi's list of authorities, so
behind a proxy that re-signs HTTPS (company and university networks) every call fails with
CERTIFICATE_VERIFY_FAILED although the browser and EWALD's own downloads work. Before mp-api is
first imported the plugin therefore makes Python's ``ssl`` use the operating system's store
(``truststore.inject_into_ssl()``, the store Windows, macOS and Linux keep up to date);
"Use the system certificate store" on the settings page turns that off.
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
        SettingsField("use_mp_api", "Use mp-api when it is installed", kind="bool", default=True, advanced=True,
                      help="mp-api (pip install mp-api) adds relaxation trajectories and the newest band "
                           "structures and DOS; without it EWALD talks to the Materials Project directly."),
        SettingsField("system_certificates", "Use the system certificate store", kind="bool", default=True,
                      advanced=True,
                      help="Trust the certificates your operating system trusts (needed behind proxies that "
                           "re-sign HTTPS). Takes effect at the next start of EWALD when turned off."),
    )


class MPKeyError(RuntimeError):
    """No API key, or the Materials Project refused it."""


CERT_HINT = ("the connection's certificate was not trusted (a proxy that re-signs HTTPS?); turn on "
             "Preferences › Materials Project › Use the system certificate store and restart EWALD, or "
             "ask your IT for the proxy's root certificate")


def _cert_error(text: str) -> bool:
    return "CERTIFICATE_VERIFY_FAILED" in text or "SSLCertVerificationError" in text


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


_trust_injected = False


def trust_system_store() -> bool:
    """Make ``ssl`` (and so requests, urllib3 and boto3) use the OS certificate store, once per
    process; it must run before boto3 is imported. False when it is off or truststore is missing."""
    global _trust_injected
    if _trust_injected:
        return True
    if settings().get("system_certificates", True) is False:
        return False
    try:
        import truststore
    except ImportError:
        return False
    truststore.inject_into_ssl()
    _trust_injected = True
    return True


def has_mp_api() -> bool:
    import importlib.util

    try:
        return importlib.util.find_spec("mp_api") is not None
    except (ImportError, ValueError):
        return False


def backend() -> str:
    """``"mp-api"`` when mp-api is installed and not turned off, else ``"rest"``."""
    return "mp-api" if settings().get("use_mp_api", True) is not False and has_mp_api() else "rest"


def rester():
    """A new client with the stored key (tests replace this function): an ``MPRester`` or a
    :class:`ewald_mp.rest.Rester`, see :func:`backend`."""
    if backend() == "rest":
        from .rest import Rester, env_key

        return Rester(api_key() or env_key())
    return mp_api_rester()


def mp_api_rester():
    """A new ``mp_api`` ``MPRester`` with the stored key."""
    trust_system_store()
    try:
        from mp_api.client import MPRester
    except ImportError as exc:
        raise ImportError("the Materials Project plugin needs mp-api: pip install mp-api") from exc
    try:
        return MPRester(api_key(), mute_progress_bars=True)
    except Exception as exc:  # noqa: BLE001 (mp-api raises its own MPRestError for a missing key)
        if _cert_error(str(exc)):
            raise ConnectionError(f"Materials Project: {CERT_HINT}") from exc
        if "api_key" in str(exc).lower() or "api key" in str(exc).lower():
            raise MPKeyError(f"no Materials Project API key: set it under Preferences › Materials Project "
                             f"(get one at {KEY_URL})") from None
        raise


def call(fn):
    """``fn(mpr)`` with an open ``MPRester``; a refused key says where to set it."""
    from .rest import NeedsMPApi

    mpr = rester()
    try:
        if hasattr(mpr, "__enter__"):
            with mpr:
                return fn(mpr)
        return fn(mpr)
    except (MPKeyError, NeedsMPApi, ConnectionError, ValueError):
        raise
    except Exception as exc:  # noqa: BLE001
        text = str(exc)
        if _cert_error(text):
            raise ConnectionError(f"Materials Project: {CERT_HINT}") from exc
        if any(s in text for s in ("401", "403", "Unauthorized", "invalid API key", "API key")):
            raise MPKeyError(f"the Materials Project refused the API key ({text.splitlines()[0][:200]}); "
                             "check it under Preferences › Materials Project") from None
        raise
