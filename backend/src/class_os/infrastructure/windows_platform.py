"""Explicit process-local workaround for unavailable optional Windows WMI metadata.

CPython retains real OS/architecture fallbacks when this query raises OSError.
Never install a global site hook, change a service, or invent platform values.
"""
import platform
import sys
from collections.abc import Mapping


def _optional_wmi_unavailable(*_args):
    raise OSError("Optional WMI metadata query unavailable")


def configure_windows_platform(environ: Mapping[str, str]) -> bool:
    """Opt in before importing adapters that query platform.machine()."""
    value = environ.get("CLASSMATTER_WINDOWS_METADATA_FALLBACK")
    if value is None or value == "0":
        return False
    if value != "1":
        raise ValueError("Windows metadata fallback must be 0 or 1")
    if sys.platform != "win32":
        return False
    if not callable(getattr(platform, "_wmi_query", None)):
        raise RuntimeError("This Python runtime has no supported optional WMI query")
    # Upstream recommends this early process-local override (CPython #112278).
    # OSError selects platform.py's existing sys.getwindowsversion/arch paths;
    # native database extensions and application deadlines remain unchanged.
    platform._wmi_query = _optional_wmi_unavailable
    return True
