"""Every production text surface must have an explicit evidence state."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_surface_inventory_is_complete_and_auditable():
    run = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "audit_surface_inventory.py")],
        capture_output=True, text=True,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    report = json.loads(
        (ROOT / "build" / "reports" / "surface-inventory.json").read_text()
    )
    assert report["surfaces"] == 36
    assert report["unknown"] == []
    assert report["release_ready"] is False


def test_every_master_catalog_entry_has_an_owner():
    run = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "scan_catalog_residue.py")],
        capture_output=True, text=True,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    report = json.loads(
        (ROOT / "build" / "reports" / "catalog-residue.json").read_text()
    )
    assert report["entries"] == report["classified"] == 19
    assert report["unknown"] == []
