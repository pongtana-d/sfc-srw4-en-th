#!/usr/bin/env python3
"""Build the translator-facing dialogue reference from production translation data.

The generated file is a view, not a second source of truth.  Catalog files keep
their ROM metadata; this view exposes only reviewed Japanese -> Thai terms.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TRANS = ROOT / "data" / "translations"
OUTPUT = TRANS / "references" / "dialogue.th.json"
DASHES = str.maketrans({"－": "ー"})


def _read(name: str) -> object:
    return json.loads((TRANS / name).read_text(encoding="utf-8"))


def _clean(source: object, translation: object) -> tuple[str, str] | None:
    source_text = str(source or "").strip().translate(DASHES)
    thai = str(translation or "").strip()
    if not source_text or not thai or source_text.startswith("<"):
        return None
    return source_text, thai


def _catalog(name: str, records_key: str | None = None) -> dict[str, str]:
    raw = _read(name)
    rows = raw if records_key is None else raw[records_key]  # type: ignore[index]
    result: dict[str, str] = {}
    for row in rows:  # type: ignore[union-attr]
        pair = _clean(row.get("source"), row.get("translation"))
        if pair is None:
            continue
        source, thai = pair
        previous = result.get(source)
        if previous is not None and previous != thai:
            raise ValueError(f"{name}: conflicting translations for {source!r}: {previous!r}, {thai!r}")
        result[source] = thai
    return dict(sorted(result.items()))


def _glossary() -> dict[str, dict[str, str]]:
    raw = _read("glossary.th.json")
    result: dict[str, dict[str, str]] = {}
    for group, entries in raw.items():  # type: ignore[union-attr]
        if group.startswith("_"):
            continue
        cleaned: dict[str, str] = {}
        for source, translation in entries.items():
            pair = _clean(source, translation)
            if pair is not None:
                cleaned[pair[0]] = pair[1]
        result[group] = dict(sorted(cleaned.items()))
    return result


def _iter_categories(categories: dict[str, object]) -> Iterable[tuple[str, str, str]]:
    for category, entries in categories.items():
        if category == "glossary":
            for group, terms in entries.items():  # type: ignore[union-attr]
                for source, thai in terms.items():
                    yield f"glossary.{group}", source, thai
        else:
            for source, thai in entries.items():  # type: ignore[union-attr]
                yield category, source, thai


def build() -> dict[str, object]:
    categories: dict[str, object] = {
        "pilots": _catalog("pilots.th.json"),
        "pilot_labels": _catalog("pilot-short-names.th.json"),
        "units": _catalog("units.th.json"),
        "weapons": _catalog("weapons.th.json"),
        "series": _catalog("series-names.th.json", "records"),
        "terrain": _catalog("terrain-names.th.json", "records"),
        "glossary": _glossary(),
    }

    # Later categories are more specific for dialogue review.  In particular,
    # glossary entries intentionally override catalog spellings for the same key.
    lookup: dict[str, dict[str, object]] = {}
    for origin, source, thai in _iter_categories(categories):
        entry = lookup.setdefault(source, {"translation": thai, "origins": []})
        if entry["translation"] == thai:
            origins = entry["origins"]
            if origin not in origins:  # type: ignore[operator]
                origins.append(origin)  # type: ignore[union-attr]
        elif origin.startswith("glossary.") and not any(
            str(previous).startswith("glossary.") for previous in entry["origins"]  # type: ignore[union-attr]
        ):
            # A canonical dialogue form may intentionally be longer than a
            # catalog field can display. Preserve the measured display form
            # without treating the reviewed glossary override as a conflict.
            entry["overridden_display"] = {
                "translation": entry["translation"],
                "origins": list(entry["origins"]),  # type: ignore[arg-type]
            }
            entry["translation"] = thai
            entry["origins"] = [origin]
        else:
            alternatives = entry.setdefault("alternatives", [])
            alternative = {
                "translation": entry["translation"],
                "origins": list(entry["origins"]),  # type: ignore[arg-type]
            }
            if alternative not in alternatives:  # type: ignore[operator]
                alternatives.append(alternative)  # type: ignore[union-attr]
            entry["translation"] = thai
            entry["origins"] = [origin]

    conflict_count = sum("alternatives" in entry for entry in lookup.values())
    override_count = sum("overridden_display" in entry for entry in lookup.values())

    return {
        "_meta": {
            "generated": True,
            "command": "python3 tools/build_dialogue_reference.py",
            "purpose": "แหล่งอ้างอิงรวมสำหรับแปลและตรวจบทสนทนา ห้ามแก้ไฟล์นี้โดยตรง",
            "sources": [
                "glossary.th.json",
                "pilots.th.json",
                "pilot-short-names.th.json",
                "units.th.json",
                "weapons.th.json",
                "series-names.th.json",
                "terrain-names.th.json",
            ],
            "precedence": "glossary overrides catalog entries with the same normalized source",
            "conflicts": conflict_count,
            "intentional_display_overrides": override_count,
            "conflict_policy": "lookup shows the selected value and preserves every displaced value in alternatives",
        },
        "categories": categories,
        "lookup": dict(sorted(lookup.items())),
    }


def main() -> int:
    document = build()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {OUTPUT.relative_to(ROOT)}")
    print(f"terms: {len(document['lookup'])}, conflicts: {document['_meta']['conflicts']}")  # type: ignore[index]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
