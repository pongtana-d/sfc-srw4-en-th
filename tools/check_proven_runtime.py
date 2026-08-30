#!/usr/bin/env python3
"""Replay the proven native battle route in Mesen and verify golden frames."""
from __future__ import annotations

import argparse
import csv
from collections import Counter
import hashlib
import os
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MESEN = Path("/Applications/Mesen.app/Contents/MacOS/Mesen")
LUA = ROOT / "tools" / "lua" / "wram-snapshots.lua"
DEFAULT_ROM = ROOT / "build" / "srw4-th-test.sfc"
DEFAULT_STATE = ROOT / "build" / "repro" / "en-th-own-native11.mss"
FRAMES = (700, 900, 1100, 1300, 1600, 2400)
WRAM_SIZE = 0x20000
ORDINARY_STATE = (0xFFA0, 0xFFC0)
BATTLE_STATE = (0xFFC0, 0xFFE0)
RENDERER_SCRATCH = (0xFFE0, 0x10000)
DMA_MAX_BYTES_PER_FRAME = 0x8000
DMA_CONTRACTS = {
    (0, 0x04): (544,),
    (1, 0x22): (512,),
    (2, 0x18): None,
}
GOLDEN = {
    700: "efec4d32cbda60dd1d9049880c4b627addcc5339b8212dc0cf0ab1d8e5a6f0c1",
    # This quote-to-animation boundary can expose the last text frame or the
    # first cleared frame depending on the test runner's input-poll parity.
    900: {
        "78bf80ea2c5e2b5710306428e49b6f46e2e6292751c3d9c439233420324a5596",
        "d94b0b1f333b9533a4f58ed5c7c01fd9dd480d0d6ad40b34e28f863a9e24cd1c",
    },
    # This boundary can expose either adjacent safe frame under testRunner.
    1100: {
        "4b299382df4a6a145202243db32c651050ba743c162bf8ffdd00f56a1683b302",
        "d6e561a4a9443eaee703b82a8751caf5ae7679e150cc1718b155e06410d725b2",
    },
    1300: "49892ffffa770bda835c576d452feb7462eecef37d4ae32e1465d1622d01abf5",
    # This explosion animation can expose either adjacent safe phase.
    1600: {
        "0f5caa045d3d261ecd099b5af8c7b69709c634843620b945246e6d7a94126843",
        "addc4c929398f804add8f72bcb21405d67d411ec7d01413dd4607df14a34bae3",
    },
    2400: "b75bbfbf32fba824157f60db8c706800f46d2c4c561ec620975bb76720787bd1",
}


def route() -> str:
    presses = ["5:up", "15:up", "25:up", "50:a", "80:a", "110:a"]
    presses.extend(f"{frame}:a" for frame in range(155, 2451, 45))
    return ",".join(presses)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE,
                        help="native battle state (defaults to the canonical E-156 state)")
    parser.add_argument("--rom", type=Path, default=DEFAULT_ROM,
                        help="ROM to replay (defaults to the promoted proven build)")
    args = parser.parse_args()
    state = args.state.resolve()
    rom = args.rom.resolve()
    if not MESEN.is_file():
        raise SystemExit(f"Mesen is missing: {MESEN}")
    if not state.is_file():
        raise SystemExit(f"state is missing: {state}")
    if not rom.is_file():
        raise SystemExit(f"ROM is missing: {rom}")

    with tempfile.TemporaryDirectory(prefix="srw4-runtime-") as temporary:
        prefix = Path(temporary) / "battle"
        dma_path = Path(temporary) / "battle-dma.csv"
        run = subprocess.run(
            [
                str(MESEN), "--testRunner", "--testRunnerTimeout=600", "--noAudio",
                str(rom), str(LUA),
            ],
            env=dict(
                os.environ,
                SRW4_STATE=str(state),
                SRW4_OUT=str(prefix),
                SRW4_PRESS=route(),
                SRW4_SHOTS=",".join(map(str, FRAMES)),
                SRW4_FRAMES="2450",
                SRW4_DMA=str(dma_path),
            ),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if run.returncode:
            raise SystemExit(
                f"Mesen runtime failed with exit code {run.returncode}\n{run.stdout[-4000:]}"
            )
        failures = []
        wram_frames: dict[int, bytes] = {}
        for frame in FRAMES:
            shot = Path(f"{prefix}-{frame:04d}.png")
            if not shot.is_file():
                failures.append(f"frame {frame}: screenshot missing")
                continue
            digest = hashlib.sha256(shot.read_bytes()).hexdigest()
            expected = GOLDEN[frame]
            accepted = expected if isinstance(expected, set) else {expected}
            if digest not in accepted:
                failures.append(
                    f"frame {frame}: expected one of {sorted(accepted)}, got {digest}"
                )
            wram = Path(f"{prefix}-{frame:04d}.wram")
            if not wram.is_file():
                failures.append(f"frame {frame}: WRAM dump missing")
            else:
                payload = wram.read_bytes()
                if len(payload) != WRAM_SIZE:
                    failures.append(
                        f"frame {frame}: WRAM dump is {len(payload)} bytes, expected {WRAM_SIZE}"
                    )
                else:
                    wram_frames[frame] = payload

        if len(wram_frames) == len(FRAMES):
            def variants(bounds: tuple[int, int]) -> set[bytes]:
                start, end = bounds
                return {payload[start:end] for payload in wram_frames.values()}

            ordinary = variants(ORDINARY_STATE)
            battle = variants(BATTLE_STATE)
            scratch = variants(RENDERER_SCRATCH)
            if len(ordinary) != 1:
                failures.append(
                    "ordinary renderer state changed during the isolated battle lifecycle"
                )
            if len(battle) < 3:
                failures.append("battle renderer state did not exercise enough lifecycle phases")
            if len(scratch) < 3:
                failures.append("renderer scratch did not exercise enough battle phases")
            for bounds, label in (
                (BATTLE_STATE, "battle state"),
                (RENDERER_SCRATCH, "renderer scratch"),
            ):
                start, end = bounds
                if wram_frames[1600][start:end] != wram_frames[2400][start:end]:
                    failures.append(f"{label} did not settle before map return")

        if not dma_path.is_file():
            failures.append("DMA trace missing")
        else:
            with dma_path.open(newline="") as handle:
                dma_rows = list(csv.DictReader(handle))
            per_frame: Counter[int] = Counter()
            seen: set[tuple[int, int]] = set()
            for row in dma_rows:
                channel = int(row["channel"])
                bbus = int(row["bbus"], 16)
                length = int(row["length"])
                contract = (channel, bbus)
                seen.add(contract)
                if contract not in DMA_CONTRACTS:
                    failures.append(
                        f"unexpected DMA contract ch{channel} -> ${bbus:02X}"
                    )
                    continue
                lengths = DMA_CONTRACTS[contract]
                if lengths is not None and length not in lengths:
                    failures.append(
                        f"DMA ch{channel} -> ${bbus:02X} length {length}, expected {lengths}"
                    )
                if not 0 < length <= 0xFFFF:
                    failures.append(f"invalid DMA length {length} on channel {channel}")
                hvbjoy = int(row["hvbjoy"], 16)
                inidisp = int(row["inidisp"], 16)
                if not (hvbjoy & 0x80 or inidisp & 0x80):
                    failures.append(
                        f"DMA ch{channel} launched outside VBlank/forced blank at "
                        f"frame {row['frame']} ($4212={hvbjoy:02X}, $2100={inidisp:02X})"
                    )
                per_frame[int(row["frame"])] += length
            missing = set(DMA_CONTRACTS) - seen
            if missing:
                failures.append(f"DMA contracts not exercised: {sorted(missing)}")
            if not per_frame:
                failures.append("DMA trace contains no transfers")
            else:
                peak_frame, peak_bytes = max(per_frame.items(), key=lambda item: item[1])
                if peak_bytes > DMA_MAX_BYTES_PER_FRAME:
                    failures.append(
                        f"DMA peak {peak_bytes} bytes at frame {peak_frame} exceeds "
                        f"route ceiling {DMA_MAX_BYTES_PER_FRAME}"
                    )
        if failures:
            raise SystemExit("runtime gate failed\n  " + "\n  ".join(failures))

    print(
        "runtime gate passed: Thai quotes, WRAM isolation, and safe DMA timing/ceiling"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
