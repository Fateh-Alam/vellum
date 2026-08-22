"""Anki entry point for Vellum.

Anki imports this module when the add-on is enabled.  Keeping the entry point
small makes failures easier to isolate and leaves the core package importable in
normal Python test environments where ``aqt`` is unavailable.
"""

from pathlib import Path

from .bootstrap import bootstrap


APP = bootstrap(package_name=__name__, addon_root=Path(__file__).parent)
