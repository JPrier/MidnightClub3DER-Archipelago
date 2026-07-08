"""Pytest bootstrap — make mc3api and the client package importable from tests."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for p in (ROOT, ROOT / "client"):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)
