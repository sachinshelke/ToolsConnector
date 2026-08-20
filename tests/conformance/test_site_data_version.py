"""Release gate for site/data.json's version provenance.

The committed site/data.json was removed (it is regenerated fresh at deploy),
so it can no longer go stale. This gate closes the remaining hole: the version
``scripts/build_site.py`` stamps into ``meta.version`` is ``_read_package_version()``
(read from pyproject), and it must equal the package's own ``__version__``. If a
future change makes those diverge, the release fails HERE instead of shipping a
catalog whose ``meta.version`` disagrees with the tag.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import toolsconnector

_ROOT = Path(__file__).resolve().parents[2]


def _load_build_site():
    path = _ROOT / "scripts" / "build_site.py"
    spec = importlib.util.spec_from_file_location("_build_site_for_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_site_stamps_the_package_version() -> None:
    build_site = _load_build_site()
    stamped = build_site._read_package_version()
    assert stamped == toolsconnector.__version__, (
        f"build_site would stamp meta.version={stamped!r}, but the package "
        f"__version__ is {toolsconnector.__version__!r}. site/data.json's "
        "meta.version must equal the released version — align them before tagging."
    )
