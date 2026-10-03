"""Guard the Python 3.8 runtime compatibility contract.

Pydantic resolves model field annotations while classes are being created.
Unlike postponed function annotations, PEP 585 built-in generics and PEP 604
unions therefore fail on Python 3.8. Keep model/config field declarations on
the `typing` spelling until the project raises its minimum Python version.
"""

from __future__ import annotations

import re
from pathlib import Path


_ROOT = Path(__file__).parents[1] / "src" / "clashctl"
_PY38_INCOMPATIBLE_ANNOTATION = re.compile(r"\b(?:dict|list|set|tuple|type)\[|\s\|\s")
_PYDANTIC_MODEL_FILES = (
    _ROOT / "config" / "schema.py",
    _ROOT / "models" / "config.py",
    _ROOT / "models" / "connection.py",
    _ROOT / "models" / "proxy.py",
    _ROOT / "models" / "rule.py",
    _ROOT / "models" / "version.py",
)


def test_pydantic_models_avoid_python_38_runtime_annotations() -> None:
    for path in _PYDANTIC_MODEL_FILES:
        assert not _PY38_INCOMPATIBLE_ANNOTATION.search(path.read_text()), path
