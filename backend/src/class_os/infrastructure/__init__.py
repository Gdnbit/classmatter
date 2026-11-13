"""External adapters; not imported by domain rules."""
import os

from .windows_platform import configure_windows_platform

# Spawned workers import adapters without executing an application entry point.
# Apply only the explicit process option before adapters import SQLAlchemy.
configure_windows_platform(os.environ)
