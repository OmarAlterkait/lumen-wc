"""docs/detectors.md's code runs as written (it converts IWCD, whose GDML ships here: no reference data read)."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_the_detectors_page_runs(tmp_path, monkeypatch):
    monkeypatch.setenv("LUMEN_EXAMPLES_OUT", str(tmp_path))
    ns: dict = {}
    for code in re.findall(r"```python\n(.*?)```", (ROOT / "docs/detectors.md").read_text(), re.S):
        exec(compile(code, "docs/detectors.md", "exec"), ns)
    assert len(ns["det"].sensor_table().name) > 0
