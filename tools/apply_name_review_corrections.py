#!/usr/bin/env python3
"""Apply the confirmed corrections in translations/name-review.md.

The Markdown issue table is the human-reviewed authority.  This tool updates
only records that can be joined to their Japanese source; it never performs a
blind Thai-only replacement.  Run without ``--write`` for an audit.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TRANS = ROOT / "data" / "translations"
REVIEW = TRANS / "name-review.md"
DIALOGUE_CONTEXT_ONLY = {"ロザミー"}
CONTEXT_ALIASES = {
    "ダイモス": (("ไดโมส", "ไดมอส"),),
    "グランゾン": (("กรานซอน", "แกรนซอน"),),
    "ゲシュペンスト": (
        ("เกชเพนสท์", "เกอชเปนสต์"),
        ("เกชเพนสต์", "เกอชเปนสต์"),
        ("เกอชเพนสต์", "เกอชเปนสต์"),
    ),
    "グラン=ガラン": (
        ("กราน การัน", "แกรน การัน"),
        ("แกรนการัน", "แกรน การัน"),
        ("แกรนแกแลน", "แกรน การัน"),
    ),
    "ゲア=ガリング": (("เกอา การิง", "เกีย การิง"), ("เกียร์การิง", "เกีย การิง")),
    "ゴラオン": (("โกลาออน", "โกราออน"),),
    "プルツー": (("พลีทู", "พลี ทู"), ("พลูทู", "พลี ทู")),
    "フル=フラット": (("ฟูล ฟลาต", "ฟูล แฟลต"), ("ฟุล ฟลาต", "ฟูล แฟลต")),
    "ファミリア": (("แฟมิเลีย", "แฟมิเลียร์"),),
    "ハイファミリア": (("ไฮแฟมิเลีย", "ไฮแฟมิเลียร์"),),
    "バイオリレーション": (
        ("ไบโอรีเลชั่น", "ไบโอ รีเลชัน"),
        ("ไบโอรีเลชัน", "ไบโอ รีเลชัน"),
    ),
    "ヤーマン": (("ยาแมน", "ยามัน"),),
    "ホワイトベース": (("ไวต์เบส", "ไวท์เบส"),),
    "グレミー": (("เกรมี", "เกลมี"),),
    "アクシズ": (("แอกซิส", "แอ็กซิส"),),
    "カルバリーテンプル": (
        ("แคลวารีเทมเพิล", "แคลเวอรี เทมเพิล"),
        ("แคลวารี เทมเพิล", "แคลเวอรี เทมเพิล"),
    ),
    "サイコミュ": (("ไซโคมิว", "ไซคอมมิว"),),
    "オーラマシン": (("ออร่ามาชีน", "ออร่าแมชชีน"),),
    "ヒューマノイドタイプ": (("แบบฮิวแมนนอยด์", "แบบมนุษย์"),),
    "ヘビーメタル": (("เฮฟวี่เมทัล", "เฮฟวีเมทัล"),),
    "ヤクト=ドーガ": (("ยัคท์ โดกา", "ยาคท์ โดกา"), ("ยัคท์โดกา", "ยาคท์ โดกา")),
    "コープランダー": (("โคปแลนเดอร์", "คอปลันเดอร์"),),
    "スウィートウォーター": (("สวีทวอเทอร์", "สวีตวอเตอร์"),),
    "デラーズ": (("เดลาส", "เดลาซ"),),
    "ミアン=クウ=ハウ=アッシャー": (("เมียน คู เฮา แอชเชอร์", "เมียน คู ฮาว แอชเชอร์"),),
    "ムートロン": (("มูตรอน", "มูโทรน"),),
    "ヴォルクルス": (("โวลคูรุส", "โวลครุส"),),
    "ア=バオア=クー": (("อาบาวาคู", "อะ บาโออา คู"),),
    "オルバン": (("ออร์บัน", "ออลบัน"), ("ออร์บาน", "ออลบัน")),
    "シルキー=マウ": (("ซิลกี เมา", "ซิลกี เมาว์"),),
    "ジャブロー": (("จาบูโร", "จาโบร"),),
    "スードリ": (("ซุดริ", "ซูโดริ"),),
    "スーパーロボット": (("ซูเปอร์โรบ็อต", "ซูเปอร์โรบอต"),),
    "ゼブリーズ=フルシュワ": (("เซบริส ฟรุชวา", "เซบริส ฟอร์ชวา"),),
    "ヌーベルディザード": (("นูเวลดี-เซิร์ด", "โนเวล ดี-เซิร์ด"),),
    "リィリィ=ハッシー": (("ลิลี ฮัสซี", "ลิลี แฮสซี"),),
    "ペンタゴナ": (("เพนตากอนา", "เพนตาโกนา"),),
    "ペンタゴナワールド": (("เพนตาโกนาเวิลด์", "โลกเพนตาโกนา"),),
    "クワサン=オリビー": (
        ("ควาซาน โอลิวี", "ควาซาน โอลิบี"),
    ),
    "あしゅら": (("อาชูระ", "อาชูรา"),),
    "オーラバリア": (("ออร่าแบร์ริเออร์", "ออร่าแบริเออร์"),),
    "ガルバー": (("การ์เบอร์", "กัลวา"),),
    "ケルナグール": (("เคลนากูล", "เครุนากูรุ"), ("เคอร์นากูล", "เครุนากูรุ")),
    "ゼラーナ": (("เซราน่า", "เซเลอร์นา"), ("เซรา\nน่า", "เซเลอร์\nนา")),
    "ダイアナン": (("ไดอานา", "ไดอานัน"),),
    "ダイターン": (("ไดทาน", "ไดทาร์น"),),
    "ビショット=ハッタ": (("บิช็อต ฮัตตะ", "บิช็อต เฮต"),),
    "リヒテル": (("ลิคเทล", "ริชเทอร์"),),
    "レイカ": (("เรย์กะ", "เรกะ"),),
    "香月": (("คาซึกิ", "โคซึกิ"),),
    "グランヴェール": (("กรานแวล", "แกรนเวล"), ("กรานเวล", "แกรนเวล")),
    "ケーラ": (("เคย์ระ", "เคย์รา"),),
    "ジャコバ=アオン": (("จาโคบาอาออน", "จาโคบา อาออน"),),
    "ザビーネ": (("ซาบี้เน", "ซาบิเน"),),
    "テンプルナイツ": (
        ("เทมเพิลไนตส์", "เทมเพิล ไนต์ส"),
        ("เทมเปิลไนต์", "เทมเพิล ไนต์ส"),
    ),
    "クロスボーン=バンガード": (
        ("ครอสโบนแวนการ์ด", "ครอสโบน แวนการ์ด"),
        ("ครอสโบนแวน\nการ์ด", "ครอสโบน แวน\nการ์ด"),
    ),
    "ダイモビック": (("ไดโมบิก", "ไดโมบิค"),),
    "アイザロン": (("ไอซา\nลอน", "ไอซา\nรอน"), ("ไอซาลอน", "ไอซารอน")),
    "ガイゾック": (("ไกโซ\nค", "ไกโซกุ\n"), ("ไกซ็อก", "ไกโซกุ")),
    "ガーベラ=テトラ": (
        ("การ์เบร่า เททร้า", "เยอบีรา เททรา"),
        ("การ์เบร่า เทต\nร้า", "เยอบีรา\nเททรา"),
    ),
    "ギャブレー": (("เกียบเล", "แกบเลย์"),),
    "セティ": (("เซที", "เซติ"),),
    "ロフ": (("รอฟ", "ลอฟ"),),
    "テイニクェット=ゼゼーナン": (("เทย์นิเควต เซเซอร์นัน", "เทนิเค็ต เซเซอร์นัน"),),
    "ナイメーヘン": (("นิจเมเคิน", "ไนเมเคิน"),),
    "ネェル=アーガマ": (("แนลอาร์กามา", "นาเฮล อาร์กามา"),),
    "ジオン": (("จี\nออน", "ซี\nออน"), ("จี ออน", "ซีออน")),
    "ミラリー": (("มิลารี", "มิลลารี"),),
    "ア=バオア=クー": (("อาบาโออาคู", "อะ บาโออา คู"),),
    "オーラバトラー": (
        ("ออร์ราแบทเลอร์", "ออร่าแบทเลอร์"),
        ("ออร์ร่าแบทเลอร์", "ออร่าแบทเลอร์"),
    ),
    "アグレッシブタイプ": (
        ("โหมดก้าวร้าว", "แบบก้าวร้าว"),
        ("แอกเกรสซีฟไทป์", "แบบก้าวร้าว"),
        ("แบบแอกเกรสซีฟ", "แบบก้าวร้าว"),
    ),
    "ジェネレーター": (("เจเนอเรเตอร์", "เครื่องกำเนิดพลัง"),),
    "エゥーゴ": (("เอยูโก", "AEUG"),),
    "マグマ": (("แม็กม่า", "แมกมา"),),
    "オオサカシティ": (("นครโอซาก้า", "เมืองโอซากะ"), ("โอซาก้า", "โอซากะ")),
    "ナゴヤシティ": (("นครนาโกย่า", "เมืองนาโกยะ"), ("นาโกย่า", "นาโกยะ")),
    "ラル": (("รัล", "ราล"),),
    "京四郎": (("เคียวชิโร่", "เคียวชิโร"),),
    "ハッシャ": (("ฮาชชา", "แฮตเชีย"),),
    "ルー": (("ลู", "รู"),),
    "洸": (("โค", "อากิระ"),),
    "ジェリル": (("เจอริล", "เจริล"),),
    "トッド": (("ท็อดด์", "ท็อด"),),
    "リィリィ": (("ริลี", "ลิลี"),),
    "カツ": (("คัตสึ", "คัตซ์"),),
    "フル": (("ฟุล", "ฟูล"),),
    "ミネバ": (("มิเนบา", "มิเนวา"),),
    "ギワザ": (("กิวาซ่า", "กิวาซา"),),
    "キャラ": (("คาร่า", "คารา"),),
    "バニングス": (("บานนิงส์", "บันนิงส์"),),
    "ショウ=ザマ": (("โชว์ ซามะ", "โช ซามะ"),),
    "ザビ": (("ซาบิ", "ซาบี้"),),
}
THAI_NAME_SUFFIX = (
    r"(?:คุง|ซัง|จัง|ก็|คือ|เอง|นะ|น่ะ|ล่ะ|สิ|เหรอ|หรือ|เป็น|ไป|มา|ดู|พูด|ทำ|บอก|อยู่|จะ|คง|ต้อง|ไม่|กับ|ที่|ของ|และ|แล้ว|เถอะ|ว่า|คน|ยัง|แต่|เพราะ|มี)"
)


def clean(value: str) -> str:
    return value.strip().strip("`").replace("`", "")


def canonical_jp(value: str) -> str:
    return value.replace("－", "ー").replace("＝", "=").replace("・", "=")


def contains_jp_token(text: str, key: str) -> bool:
    text = re.sub(r"\s+", "", text)
    key = re.sub(r"\s+", "", key)
    left = r"(?<![ァ-ヶー])" if key and re.match(r"[ァ-ヶー]", key[0]) else ""
    right = r"(?![ァ-ヶー])" if key and re.match(r"[ァ-ヶー]", key[-1]) else ""
    return re.search(left + re.escape(key) + right, text) is not None


def replace_context_alias(text: str, old: str, new: str) -> str:
    if len(old) >= 4:
        if new.startswith(old):
            suffix = new[len(old) :]
            if suffix:
                return re.sub(re.escape(old) + f"(?!{re.escape(suffix)})", new, text)
        return text.replace(old, new)
    for prefix in ("คุณ", "ไอ้", "นาย", "ท่าน", "กับ", "ให้", "ของ", "ตาม", "ช่วย", "รัก", "หา", "แม่", "ถ้า", "เพราะ"):
        text = text.replace(prefix + old, prefix + new)
    return re.sub(
        r"(?<![ก-๙])"
        + re.escape(old)
        + f"(?=(?:{THAI_NAME_SUFFIX})|[^\u0e01-\u0e59]|$)",
        new,
        text,
    )


def reviewed_map() -> tuple[dict[str, str], dict[str, set[str]]]:
    section = REVIEW.read_text(encoding="utf-8").split(
        "## ชื่อที่ยืนยันแล้วว่าปัจจุบันมีปัญหา", 1
    )[1]
    desired: dict[str, str] = {}
    old_forms: dict[str, set[str]] = {}
    for line in section.splitlines():
        if not line.startswith("|") or line.startswith("|---"):
            continue
        cells = [clean(cell) for cell in line.strip("|").split("|")]
        if len(cells) != 4 or cells[0] == "ญี่ปุ่น":
            continue
        jp, old, new, _reason = cells
        jp_parts = [clean(x) for x in jp.split("／")]
        old_parts = [clean(x) for x in old.split(" / ")]
        new_parts = [clean(x) for x in new.split(" / ")]
        if len(jp_parts) != len(old_parts) or len(jp_parts) != len(new_parts):
            continue
        for source, previous, replacement in zip(jp_parts, old_parts, new_parts):
            key = canonical_jp(source)
            # Some review rows prescribe deletion/contextual binding instead
            # of a literal replacement.  They are intentionally manual.
            if any(word in replacement for word in ("ลบคีย์", "แยกตามชื่อเต็ม", "ไม่ควรสร้าง")):
                continue
            desired[key] = replacement
            old_forms.setdefault(key, set()).add(previous)

    # Rows whose prose deliberately groups several concrete ROM keys.
    manual = {
        "イーグルファイターＮ": "อีเกิลไฟเตอร์ N",
        "イーグルファイターＡ": "อีเกิลไฟเตอร์ A",
        "イーグルファイターＨ": "อีเกิลไฟเตอร์ H",
        "ランドクーガーＮ": "แลนด์คูการ์ N",
        "ランドクーガーＡ": "แลนด์คูการ์ A",
        "ランドクーガーＨ": "แลนด์คูการ์ H",
        "ランドライガーＮ": "แลนด์ไลเลอร์ N",
        "ランドライガーＡ": "แลนด์ไลเลอร์ A",
        "ランドライガーＨ": "แลนด์ไลเลอร์ H",
        "ビッグモスＮ": "บิ๊กมอธ N",
        "ビッグモスＡ": "บิ๊กมอธ A",
        "ビッグモスＨ": "บิ๊กมอธ H",
        "サイコガンダムｍｋⅡ": "ไซโคกันดั้ม Mk-II",
        "キュベレイｍｋⅡ": "คิวเบเลย์ Mk-II",
        "ガンダムｍｋⅡ": "กันดั้ม Mk-II",
        "機械獣ガラダＫ７": "อสูรกล การาดา K7",
        "機械獣トロスＤ７": "อสูรกล โทรอส D7",
        "機械獣ジェノバＭ９": "อสูรกล เจโนวา M9",
        "機械獣スパルタンＫ５": "อสูรกล สปาร์ตัน K5",
        "機械獣ダブラスM2": "อสูรกล ดูบลาส M2",
        "ガラダK7": "การาดา K7",
        "ジェノバM9": "เจโนวา M9",
        "スパルタンK5": "สปาร์ตัน K5",
        "トロスD7": "โทรอส D7",
        "ゲッタードラゴン": "เก็ตเตอร์ ดรากอน",
        "ゲッターライガー": "เก็ตเตอร์ ไลเกอร์",
        "ゲッターポセイドン": "เก็ตเตอร์ โพไซดอน",
        "コンバトラーV": "คอมแบตเลอร์ V",
        "コンバトラーチーム": "ทีมคอมแบตเลอร์",
        "バトルジェット": "แบทเทิล เจ็ต",
        "バトルクラッシャー": "แบทเทิล ครัชเชอร์",
        "バトルタンク": "แบทเทิล แทงก์",
        "バトルマリン": "แบทเทิล มารีน",
        "バトロウクラフト": "แบทเทิล คราฟต์",
        "ハイパーレプラカーン": "ไฮเปอร์ เลปราคาร์น",
        "ハイパーライネック": "ไฮเปอร์ ไรเน็ก",
        "ハイパーガラバ": "ไฮเปอร์ กัลลาบา",
    }
    for source, replacement in manual.items():
        key = canonical_jp(source)
        desired[key] = replacement
        old_forms.setdefault(key, set())
    for prefix in ("真・ゲッター", "真ゲッター"):
        for number in "123":
            key = canonical_jp(prefix + number)
            desired[key] = f"ชิน เก็ตเตอร์ {number}"
            old_forms.setdefault(key, set()).add(f"ชินเก็ตเตอร์ {number}")
    for source in ("ネオジオン", "ネオ・ジオン"):
        key = canonical_jp(source)
        desired[key] = "นีโอซีออน"
        old_forms.setdefault(key, set()).add("นีโอจีออน")
    return desired, old_forms


def update_record_tree(node: object, mapping: dict[str, str], changes: list[str], path: str) -> None:
    if isinstance(node, list):
        for index, value in enumerate(node):
            update_record_tree(value, mapping, changes, f"{path}[{index}]")
    elif isinstance(node, dict):
        source = node.get("source")
        if isinstance(source, str) and isinstance(node.get("translation"), str):
            replacement = mapping.get(canonical_jp(source))
            if replacement is not None and node["translation"] != replacement:
                changes.append(f"{path}: {source}: {node['translation']} -> {replacement}")
                node["translation"] = replacement
                node["method"] = "reviewed_name_report"
        for key, value in node.items():
            update_record_tree(value, mapping, changes, f"{path}.{key}")


def update_glossary(node: object, mapping: dict[str, str], changes: list[str], path: str) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if key.startswith("_"):
                continue
            replacement = mapping.get(canonical_jp(key))
            if replacement is not None and isinstance(value, str) and value != replacement:
                changes.append(f"{path}.{key}: {value} -> {replacement}")
                node[key] = replacement
            else:
                update_glossary(value, mapping, changes, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            update_glossary(value, mapping, changes, f"{path}[{index}]")


def update_dialogue(mapping: dict[str, str], old_forms: dict[str, set[str]], changes: list[str]) -> dict:
    source_rows = json.loads((TRANS / "script.source.json").read_text(encoding="utf-8"))["messages"]
    sources = {row["id"]: canonical_jp(row["source"]) for row in source_rows}
    document = json.loads((TRANS / "script.th.json").read_text(encoding="utf-8"))
    for message_id, thai in document["messages"].items():
        source = sources[message_id]
        # Speaker labels have their own exact-source synchronizer.  Restrict
        # glossary substitutions to the utterance so a short alias mentioned
        # in the body cannot rewrite a different speaker name.
        label_match = re.match(r"^((?:<[^>]+>)*[^:\n]*:)(.*)$", thai, re.DOTALL)
        label = label_match.group(1) if label_match else ""
        revised = label_match.group(2) if label_match else thai
        original_body = revised
        for japanese in sorted(mapping, key=len, reverse=True):
            if japanese in DIALOGUE_CONTEXT_ONLY:
                continue
            if not contains_jp_token(source, japanese):
                continue
            candidates = old_forms.get(japanese, set())
            for previous in sorted(candidates, key=len, reverse=True):
                if previous and previous in revised:
                    replacement = mapping[japanese]
                    if replacement.startswith(previous):
                        suffix = replacement[len(previous) :]
                        if suffix:
                            revised = re.sub(
                                re.escape(replacement) + f"(?:{re.escape(suffix)})+",
                                replacement,
                                revised,
                            )
                            revised = re.sub(
                                re.escape(previous) + f"(?!{re.escape(suffix)})",
                                replacement,
                                revised,
                            )
                    else:
                        revised = revised.replace(previous, replacement)
        # Context-sensitive homographs documented in name-review.md.
        if "フォウ" in source:
            revised = revised.replace("ฟาว", "โฟร์")
        if "バーン" in source:
            bern_or_baan = "บาน" if "バーン=ガニア" in source else "เบิร์น"
            revised = revised.replace("บาร์น", bern_or_baan)
            if bern_or_baan == "เบิร์น":
                revised = replace_context_alias(revised, "บาน", bern_or_baan)
        for japanese, aliases in CONTEXT_ALIASES.items():
            if not contains_jp_token(source, japanese):
                continue
            for old, replacement in aliases:
                revised = replace_context_alias(revised, old, replacement)
        if revised != original_body:
            revised = re.sub(r"(?<=[A-Za-z0-9])(?=[ก-๙])", " ", revised)
            revised = re.sub(r"(?<=[ก-๙])(?=[A-Za-z])", " ", revised)
            complete = label + revised
            changes.append(f"script.th.json:{message_id}: {thai} -> {complete}")
            document["messages"][message_id] = complete
    return document


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    mapping, old_forms = reviewed_map()
    changed_documents: dict[Path, object] = {}
    changes: list[str] = []

    for path in sorted(TRANS.glob("*.th.json")):
        if path.name == "script.th.json":
            continue
        document = json.loads(path.read_text(encoding="utf-8"))
        before = len(changes)
        update_record_tree(document, mapping, changes, path.name)
        if path.name == "glossary.th.json":
            update_glossary(document, mapping, changes, path.name)
        if len(changes) != before:
            changed_documents[path] = document

    dialogue = update_dialogue(mapping, old_forms, changes)
    original_dialogue = json.loads((TRANS / "script.th.json").read_text(encoding="utf-8"))
    if dialogue != original_dialogue:
        changed_documents[TRANS / "script.th.json"] = dialogue

    print(f"reviewed Japanese names: {len(mapping)}")
    print(f"corrections: {len(changes)} in {len(changed_documents)} files")
    if args.verbose:
        print("\n".join(changes))
    if args.write:
        for path, document in changed_documents.items():
            path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 1 if changes and not args.write else 0


if __name__ == "__main__":
    raise SystemExit(main())
