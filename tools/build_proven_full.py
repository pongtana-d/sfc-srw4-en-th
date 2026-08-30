#!/usr/bin/env python3
"""Build the last proven cumulative Thai ROM from its pinned source revision.

The current rewrite does not yet contain the battle-safe renderer.  This
entrypoint keeps the verified milestone reproducible while that implementation
is migrated: it extracts an immutable in-repository revision to a temporary
directory and runs its cumulative intro/story build.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.battle_contract import BattleContract  # noqa: E402
from srw4.battle_adapters import build_dispatch, build_width  # noqa: E402
from srw4.battle_renderer import build as build_battle_renderer  # noqa: E402
from srw4.battle_stock_fb import build as build_battle_stock_fb  # noqa: E402
from srw4.battle_assets import build as build_battle_assets  # noqa: E402

PROVEN_REVISION = "eddbcada4ff6b05b562b5b93d9a26477468c3142"
EXPECTED_SHA256 = "a82a78d89f100bce8c9df3fec31c045337957797440d7b573f76afaa62ca4995"
DEFAULT_CLEAN = ROOT / "rom" / "Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc"
DEFAULT_OUTPUT = ROOT / "build" / "srw4-th-proven-full.sfc"
DEFAULT_REPORT = ROOT / "build" / "reports" / "proven-full.json"
BATTLE_CONTRACT = ROOT / "data" / "config" / "battle-contract.json"


def place_current_battle(image: bytes, clean_image: bytes) -> tuple[bytes, dict]:
    """Place P8 artifacts from current modules and return placement metadata."""
    contract = BattleContract.load(BATTLE_CONTRACT)
    if contract.source_revision != PROVEN_REVISION:
        raise SystemExit("battle contract and proven build revisions differ")
    contract.verify_clean(clean_image)
    payload = bytearray(image)
    assets, asset_addresses = build_battle_assets(contract)
    for name, artifact in assets.items():
        at = asset_addresses[name]
        payload[at:at + len(artifact)] = artifact
    renderer = build_battle_renderer(contract)
    payload[contract.renderer_pc:contract.renderer_pc + len(renderer)] = renderer
    generated = {
        "stock_fb": lambda spec: build_battle_stock_fb(spec),
        "width": lambda spec: build_width(spec.cpu, spec.dependency_cpu),
        "dispatch": lambda spec: build_dispatch(spec.cpu, spec.dependency_cpu),
    }
    for adapter in contract.adapters:
        actual = generated[adapter.id](adapter)
        if len(actual) != adapter.bytes:
            raise SystemExit(f"current {adapter.id} size differs from its contract")
        payload[adapter.pc:adapter.pc + len(actual)] = actual
    for hook in contract.hooks:
        payload[hook.pc:hook.pc + len(hook.proven)] = hook.proven
    final = bytes(payload)
    contract.verify_proven(final)
    return final, {
        "owner": "current modules",
        "assets": len(assets),
        "renderer_bytes": len(renderer),
        "adapters": [adapter.id for adapter in contract.adapters],
        "hooks": [hook.id for hook in contract.hooks],
    }


def build_proven(clean: Path, output: Path, report: Path) -> str:
    """Build the pinned milestone and return its verified SHA-256."""
    clean = clean.resolve()
    output = output.resolve()
    report = report.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    report.parent.mkdir(parents=True, exist_ok=True)

    archive = subprocess.run(
        ["git", "archive", "--format=tar", PROVEN_REVISION],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
    ).stdout
    with tempfile.TemporaryDirectory(prefix="srw4-proven-") as temporary:
        checkout = Path(temporary)
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as bundle:
            bundle.extractall(checkout, filter="data")
        subprocess.run(
            [
                sys.executable,
                str(checkout / "tools" / "build_intro.py"),
                "--input", str(clean),
                "--output", str(output),
                "--report", str(report),
            ],
            cwd=checkout,
            check=True,
        )

    final_image, battle_placement = place_current_battle(
        output.read_bytes(), clean.read_bytes()
    )
    output.write_bytes(final_image)
    digest = hashlib.sha256(final_image).hexdigest()
    if digest != EXPECTED_SHA256:
        raise SystemExit(
            f"current-owned battle placement changed the proven ROM: "
            f"expected {EXPECTED_SHA256}, got {digest}"
        )
    document = json.loads(report.read_text())
    document["proven_source"] = {
        "revision": PROVEN_REVISION,
        "sha256": digest,
        "battle_contract": str(BATTLE_CONTRACT.relative_to(ROOT)),
        "battle_placement": battle_placement,
        "runtime_gates": [
            "native battle quote rendered in Thai",
            "battle animation completed",
            "battle returned to map without tile corruption",
            "cold boot reached naming screen with Thai presets",
        ],
    }
    report.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n")
    return digest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_CLEAN)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    digest = build_proven(args.input, args.output, args.report)
    print(f"verified proven full ROM: {args.output.resolve()} sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
