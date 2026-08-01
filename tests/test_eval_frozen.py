"""Pin frozen-eval headline numbers spoken on camera / Pages / RESULTS."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_frozen_eval_headline_numbers():
    proc = subprocess.run(
        [sys.executable, str(ROOT / "eval" / "run_eval.py"), "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr
    payload = json.loads(proc.stdout)
    c = payload["results"]["C classifier"]
    # Exact binder fractions; spoken/Pages/RESULTS publish accuracy as 0.97 truncated.
    assert c["accuracy"] == pytest.approx(39 / 40)
    assert float(f"{c['accuracy']:.2f}") == 0.97
    assert c["hard_precision"] == 1.0
    assert c["decoy_false_positive_rate"] == 0.0
