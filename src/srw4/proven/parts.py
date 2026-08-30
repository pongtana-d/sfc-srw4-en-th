"""Short localized labels for the enhancement-parts inventory."""

from __future__ import annotations

from pathlib import Path

from .catalogs import Write
from .text.japanese import CatalogDecoder, read_catalog_string
from .text.stock import encode_stock


# These names use the stock Latin page.  Every replacement is no wider than
# its Japanese field, so the fixed, non-catalog table stays in place.
NAMES = (
    (0x12875D, "高性能レーダー", "RADAR"),
    (0x128768, "ミノフスキークラフト", "MINOVSKY"),
    (0x128773, "ブースター", "BOOST"),
    (0x128779, "メガブースター", "MEGA"),
    (0x128781, "アポジモーター", "APOGEE"),
    (0x128789, "ファティマ", "FATI"),
    (0x12878F, "ＡＬＩＣＥ", "ALICE"),
    (0x128795, "サイコフレーム", "PSY"),
    (0x12879D, "バイオセンサー", "BIO"),
    (0x1287A5, "マグネットコーティング", "MAG COAT"),
    (0x1287B1, "Ｉフィールド発生機", "I-FIELD"),
    (0x1287BE, "チョバムアーマー", "CHOBHAM"),
    (0x1287C7, "ハイブリッドアーマー", "HYBRID"),
    (0x1287D2, "バリアジェネレーター", "BARRIER"),
    (0x1287DD, "対ビームコーティング", "BEAM COAT"),
    (0x1287E9, "リペアキット", "REPAIR"),
    (0x1287F0, "プロペラントタンク", "PROP TANK"),
    (0x1287FA, "プロペラントタンクＳ", "PROP TANKS"),
    (0x128805, "金塊", "GD"),
    (0x12880A, "なし", "NO"),
)


def build_part_name_data(root: Path, clean: bytes) -> tuple[list[Write], dict[str, object]]:
    decoder = CatalogDecoder(root / "font/jp-kanji.json")
    writes: list[Write] = []
    report: list[dict[str, object]] = []
    for pc, source_text, replacement in NAMES:
        pointer = pc & 0xFFFF
        source = read_catalog_string(clean, pc & 0xFF0000, pointer)
        if decoder.decode(source) != source_text:
            raise ValueError(f"part name source mismatch at {pc:#08x}")
        encoded = encode_stock(replacement)
        if len(encoded) > len(source) - 1 or len(replacement) > len(source_text):
            raise ValueError(f"part name does not fit: {replacement}")
        payload = encoded + b"\x00" * (len(source) - len(encoded) - 1) + b"\xFF"
        writes.append(Write(pc, payload, f"part-name:{replacement}", False))
        report.append({"pc": f"0x{pc:06X}", "source": source_text, "text": replacement,
                       "width_px": len(replacement) * 8, "max_width_px": len(source_text) * 8})
    return writes, {"names": report, "source_routes": {}}
