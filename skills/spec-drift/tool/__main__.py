"""Entry point for running the directory directly: both
`python3 <skill-dir>/tool ...` and the package form
`python3 -m <package> ...` end up here. So that modules inside the package can
all use absolute (not relative) imports while both invocation forms still resolve them,
`__init__.py` has already inserted this directory into sys.path — here we just do the
ordinary `from cli import main`.
"""
import sys

from cli import main

sys.exit(main())
