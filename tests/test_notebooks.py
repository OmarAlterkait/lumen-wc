"""The notebooks (notebooks/NN_*.ipynb) run end to end, each in a fresh kernel, in order, sharing one work directory.

    pytest tests/test_notebooks.py --durations=0     # on a machine with a GPU

Skipped without a GPU (JAX's default backend in a fresh interpreter). The notebooks fetch the reference data they read
into ``lumen.compare.references.store()`` (``LUMEN_DATA``, else lumen's cache) on first use. ``LUMEN_NOTEBOOKS`` names
the work directory (default: a temporary one), where each executed notebook is written with its outputs; ``G4REF``
(the g4ref binary) lets notebook 01 run its geometry check against Geant4. The checks are lumen's
(``lumen.testing.notebooks``, ``check_notebooks_clean``, ``run_notebook``).
"""

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from lumen import testing

NOTEBOOKS = testing.notebooks(Path(__file__).resolve().parents[1] / "notebooks")


def _gpu() -> bool:
    out = subprocess.run([sys.executable, "-c", "import jax; print(jax.default_backend())"], capture_output=True,
                         text=True, timeout=300)  # fmt: skip
    return out.stdout.strip().endswith("gpu")


needs_gpu = pytest.mark.skipif(not NOTEBOOKS or not _gpu(), reason="needs a GPU")


@pytest.fixture(scope="module")
def work(tmp_path_factory):
    path = Path(os.environ.get("LUMEN_NOTEBOOKS") or tmp_path_factory.mktemp("notebooks"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_notebooks_are_committed_without_outputs():
    testing.check_notebooks_clean(NOTEBOOKS)


@pytest.mark.parametrize("path", NOTEBOOKS, ids=lambda p: p.stem)
@needs_gpu
def test_notebook_runs(path, work, monkeypatch):
    monkeypatch.setenv("LUMEN_NOTEBOOKS", str(work))
    t0 = time.time()
    testing.run_notebook(path, work)
    print(f"{path.stem}: {time.time() - t0:.0f} s")
