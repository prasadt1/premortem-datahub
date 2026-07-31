"""Repair round-trip must stay at 100% on eligible frozen queries (kill criterion)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_repair_roundtrip_passes():
    proc = subprocess.run(
        [sys.executable, str(ROOT / "eval" / "run_repair_roundtrip.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr
    assert "22/22" in proc.stdout
    assert "PASS" in proc.stdout
