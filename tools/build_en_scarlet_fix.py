#!/usr/bin/env python3
"""Build a focused Scarlet Beam IPS for an existing EN or EN->Thai ROM."""
from pathlib import Path
import argparse
import hashlib
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from srw4.en_baseline import EN_SHA256
from srw4.en_scarlet_upgrade import install
from srw4.en_story_build import verify_stock_objectives
from srw4.rom import Rom
from build_en_th_full_dialogue import encode_ips


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,default=ROOT/'build/srw4-en-th.sfc')
    parser.add_argument('--output-dir',type=Path,default=ROOT/'build/scarlet-repair-slot')
    args=parser.parse_args()
    clean=(ROOT/'rom/Dai-4-ji Super Robot Taisen (English combo).sfc').read_bytes()
    if hashlib.sha256(clean).hexdigest()!=EN_SHA256:
        raise ValueError('English baseline hash mismatch')
    base=args.input.read_bytes()
    if len(base)!=len(clean):raise ValueError('Expected unheadered 4 MiB EN ROM')
    rom=Rom(bytearray(base))
    report=install(rom.data)
    verify_stock_objectives(rom.data,clean)
    rom.fix_checksum()
    patched=rom.to_bytes()
    output=args.output_dir
    target=output/'srw4-en-th-scarlet-fix.sfc'
    if target.resolve()==args.input.resolve():raise ValueError('Do not overwrite input ROM')
    output.mkdir(parents=True,exist_ok=True)
    target.write_bytes(patched)
    focused=encode_ips(base,patched)
    (output/'scarlet-fix.ips').write_bytes(focused)
    (output/'srw4-en-th-with-scarlet-fix.ips').write_bytes(encode_ips(clean,patched))
    report.update(input_path=str(args.input.resolve()),input_sha256=hashlib.sha256(base).hexdigest(),
                  output_sha256=hashlib.sha256(patched).hexdigest(),
                  focused_patch_sha256=hashlib.sha256(focused).hexdigest(),
                  combined_patch_base_sha256=EN_SHA256,objectives='stock English verified')
    (output/'patch.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
