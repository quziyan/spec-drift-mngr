"""Modules inside this package always use absolute (not relative) imports, so that this
directory can be executed directly with `python3 <directory>` (that form puts the
directory itself on sys.path[0] and then runs __main__.py, so the modules can only refer
to one another by absolute import — `from . import x` no longer works).

Running it as a package instead (`python3 -m <package> ...`) goes through the package
import path and does not add this directory to sys.path by itself — hence the explicit
insertion here, so both invocation forms can share one set of absolute imports.
"""
import sys
from pathlib import Path

_PKG_DIR = str(Path(__file__).resolve().parent)
if _PKG_DIR not in sys.path:
    sys.path.insert(0, _PKG_DIR)
