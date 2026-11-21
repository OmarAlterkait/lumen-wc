"""lumen_wc's input files: lumen's one pipeline (``lumen.inputs``) on this package's shipped GDMLs.

    with inputs.gdml_file(path) as gdml: ...          # a .gdml as it is; a .gdml.xz decompressed, its sha256 checked
    inputs.require({"gdml": (path, sha256, where)})   # refuses a missing file or another sha256, naming its source

The GDMLs this package ships are stored xz-compressed beside ``gdml/SOURCES.json`` (each file's source and the sha256
of the decompressed file).
"""

from __future__ import annotations

import functools
from pathlib import Path

from lumen import inputs
from lumen.inputs import InputError, require, sha256

GDML_DIR = Path(__file__).parent / "gdml"
shipped = functools.partial(inputs.shipped, GDML_DIR)
gdml_file = functools.partial(inputs.gdml_file, gdml_dir=GDML_DIR)

__all__ = ["GDML_DIR", "InputError", "gdml_file", "require", "sha256", "shipped"]
