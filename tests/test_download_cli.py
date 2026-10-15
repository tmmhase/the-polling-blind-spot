"""Command-line wiring for the raw-data downloaders."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_help_lists_all_three_sources():
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "download_data.py"), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0
    for source in ("fte-historical", "medsl-senate", "wikipedia-2026"):
        assert source in completed.stdout
