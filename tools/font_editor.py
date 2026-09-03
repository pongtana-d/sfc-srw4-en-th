#!/usr/bin/env python3
"""A pixel editor for the font data this project already tuned.

  tools/font_editor.py            -> http://127.0.0.1:8731

It edits `data/font/thai.json` (bases, exact contextual stacks and base variants) and
`data/font/renewal-overrides.json`, and it previews through the real
`AtlasBuilder`, so what the browser shows is what the atlas will build. No
composition rule is reimplemented here.

Contextual upper/lower stacks are full 8x16 overlays. Their saved pixels are
already in the final position; production never recalculates x/y placement.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.atlas import CELL_ROWS, CELL_WIDTH, MAX_ADVANCE, MIN_ADVANCE, AtlasBuilder  # noqa: E402
from srw4.text import segment, token_for  # noqa: E402
from srw4.tokens import EncodingError, TokenMap  # noqa: E402

EN_ROM = ROOT / "rom" / "Dai-4-ji Super Robot Taisen (English).sfc"
FONT_DIR = ROOT / "data" / "font"
THAI = FONT_DIR / "thai.json"
OVERRIDES = FONT_DIR / "renewal-overrides.json"
ICONS = FONT_DIR / "renewal-icons.json"
MANIFEST = FONT_DIR / "renewal-clusters.json"
WINDOWS = ROOT / "data" / "config" / "text-windows.json"
PAGE = Path(__file__).resolve().parent / "font_editor.html"


def ink_columns(rows: list[int]) -> tuple[int, int]:
    """(left, width) of the lit columns; (0, 0) when nothing is drawn."""
    used = [row for row in rows if row]
    if not used:
        return 0, 0
    left = min(7 - value.bit_length() + 1 for value in used)
    right = max(max(b for b in range(8) if value >> (7 - b) & 1) for value in used)
    return left, right - left + 1


def _read(path: Path) -> tuple[dict, int]:
    """Load a font file, and remember how it was indented so a save is a no-op."""
    text = path.read_text()
    second = text.split("\n", 1)[1] if "\n" in text else " "
    return json.loads(text), len(second) - len(second.lstrip(" ")) or 1


def _write(path: Path, doc: dict, indent: int) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(doc, ensure_ascii=False, indent=indent) + "\n")
    temp.replace(path)


class Draft:
    """The working copy: what the browser edits before anyone saves."""

    def __init__(self) -> None:
        self.thai, self.thai_indent = _read(THAI)
        self.overrides, self.overrides_indent = _read(OVERRIDES)
        self.icons, self.icons_indent = _read(ICONS)
        self.manifest = TokenMap.load(MANIFEST)
        self.history: dict[str, list[object]] = {}
        self.dirty = False
        self._remember_saved_state()
        try:
            rom = EN_ROM.read_bytes()
            self.rom_note = None
        except OSError as exc:
            rom = b""
            self.rom_note = str(exc)
        self.builder = AtlasBuilder(FONT_DIR, rom)

    def _remember_saved_state(self) -> None:
        self.saved_thai = copy.deepcopy(self.thai)
        self.saved_overrides = copy.deepcopy(self.overrides)
        self.saved_icons = copy.deepcopy(self.icons)

    def _refresh_dirty(self) -> None:
        self.dirty = (
            self.thai != self.saved_thai
            or self.overrides != self.saved_overrides
            or self.icons != self.saved_icons
        )

    def _record(self, key: str, before: object, after: object) -> int:
        history = self.history.setdefault(key, [copy.deepcopy(before)])
        if history[-1] != before:
            history.append(copy.deepcopy(before))
        if history[-1] != after:
            history.append(copy.deepcopy(after))
        self._refresh_dirty()
        return len(history) - 1

    def _previous(self, key: str, current: object) -> tuple[object, int, bool]:
        history = self.history.get(key)
        if not history:
            return current, 0, False
        if history[-1] != current:
            history.append(copy.deepcopy(current))
        if len(history) <= 1:
            return current, 0, False
        history.pop()
        return copy.deepcopy(history[-1]), len(history) - 1, True

    def _sync(self) -> None:
        self.builder.bases = self.thai["bases"]
        self.builder.contextual = self.thai["contextual"]
        self.builder.overrides = self.overrides["overrides"]
        self.builder.icons = self.icons["glyphs"]

    def compose(self, tokens: list[str]) -> list[dict]:
        self._sync()
        out = []
        for token in tokens:
            try:
                glyph = self.builder.build(token)
            except (EncodingError, KeyError) as exc:
                out.append({"token": token, "error": str(exc)})
                continue
            out.append(
                {
                    "token": token,
                    "rows": list(glyph.rows),
                    "source": glyph.source,
                    **glyph.metrics(),
                }
            )
        return out

    # --- commits ------------------------------------------------------------

    def put_base(self, char: str, rows: list[int], advance: int | None) -> int:
        rows = [int(r) & 0xFF for r in rows][:CELL_ROWS]
        rows += [0] * (CELL_ROWS - len(rows))
        left, ink = ink_columns(rows)
        top = next((i for i, r in enumerate(rows) if r), 0)
        if advance is None:
            advance = min(max(ink + 1, MIN_ADVANCE), MAX_ADVANCE)
        before = copy.deepcopy(self.thai["bases"].get(char, {}))
        entry = dict(before)
        entry.update({"rows": rows, "left": left, "ink": ink, "top": top,
                      "advance": int(advance)})
        self.thai["bases"][char] = entry
        return self._record(f"base:{char}", before, entry)

    def put_contextual(self, area: str, family: str | None, key: str,
                       rows: list[int]) -> int:
        rows = [int(row) for row in rows]
        if len(rows) != CELL_ROWS or any(not 0 <= row <= 0xFF for row in rows):
            raise EncodingError(f"contextual bitmap must contain {CELL_ROWS} byte rows")
        contextual = self.thai["contextual"]
        if area in {"upper", "lower"}:
            if family not in {"normal", "left"}:
                raise EncodingError(f"unknown contextual family: {family!r}")
            table = contextual[f"{area}_stacks"][family]
            if key not in table:
                raise EncodingError(f"unknown {area} stack: {key!r}")
            before = copy.deepcopy(table[key])
            table[key] = rows
            history_key = f"{area}:{family}:{key}"
        elif area == "base":
            entry = contextual["lower_base_variants"].get(key)
            if entry is None:
                raise EncodingError(f"unknown lower base variant: {key!r}")
            before = copy.deepcopy(entry["rows"])
            entry["rows"] = rows
            history_key = f"variant::{key}"
        else:
            raise EncodingError(f"unknown contextual area: {area!r}")
        return self._record(history_key, before, rows)

    def put_icon(self, name: str, rows: list[int], advance: int | None,
                 cell_span: int | None) -> int:
        """Icons are fixed artwork: the bitmap is the whole of it, no composition.

        The migration recorded a sha256 to prove each bitmap still matched the
        manifest it came from. Redrawing one makes that claim false, so the
        hash is restamped and the entry says plainly that it was redrawn.
        """
        rows = [int(r) & 0xFF for r in rows][:CELL_ROWS]
        rows += [0] * (CELL_ROWS - len(rows))
        before = copy.deepcopy(self.icons["glyphs"].get(name, {}))
        entry = dict(before)
        entry["rows"] = rows
        if advance is not None:
            entry["advance"] = int(advance)
        if cell_span is not None:
            entry["cell_span"] = int(cell_span)
        digest = hashlib.sha256(bytes(rows)).hexdigest()
        if entry.get("sha256") != digest:
            entry["sha256"] = digest
            entry["redrawn"] = True
        self.icons["glyphs"][name] = entry
        return self._record(f"icon:{name}", before, entry)

    def put_override(self, token: str, rows: list[int] | None,
                     advance: int | None, reason: str, sample: str) -> int:
        before = copy.deepcopy(self.overrides["overrides"].get(token))
        if rows is None:
            self.overrides["overrides"].pop(token, None)
            after = None
        else:
            if not reason.strip() or not sample.strip():
                raise EncodingError("an override needs a reason and a regression sample")
            entry = {"rows": [int(r) & 0xFF for r in rows], "reason": reason,
                     "sample": sample}
            if advance is not None:
                entry["advance"] = int(advance)
            self.overrides["overrides"][token] = entry
            after = entry
        return self._record(f"override:{token}", before, after)

    def undo(self, kind: str, key: str, area: str | None,
             family: str | None) -> dict:
        if kind == "base":
            history_key = f"base:{key}"
            current = self.thai["bases"][key]
            previous, depth, changed = self._previous(history_key, current)
            if changed:
                self.thai["bases"][key] = previous
        elif kind == "icon":
            history_key = f"icon:{key}"
            current = self.icons["glyphs"][key]
            previous, depth, changed = self._previous(history_key, current)
            if changed:
                self.icons["glyphs"][key] = previous
        elif kind == "stack" and area in {"upper", "lower"} and family in {"normal", "left"}:
            history_key = f"{area}:{family}:{key}"
            table = self.thai["contextual"][f"{area}_stacks"][family]
            current = table[key]
            previous, depth, changed = self._previous(history_key, current)
            if changed:
                table[key] = previous
        elif kind == "variant" and area == "base":
            history_key = f"variant::{key}"
            entry = self.thai["contextual"]["lower_base_variants"][key]
            previous, depth, changed = self._previous(history_key, entry["rows"])
            if changed:
                entry["rows"] = previous
        else:
            raise EncodingError(f"cannot undo {kind}:{area}:{family}:{key}")
        self._refresh_dirty()
        return {"changed": changed, "undo_depth": depth, "dirty": self.dirty}

    def save(self) -> list[str]:
        _write(THAI, self.thai, self.thai_indent)
        _write(OVERRIDES, self.overrides, self.overrides_indent)
        _write(ICONS, self.icons, self.icons_indent)
        self._remember_saved_state()
        self.dirty = False
        return [str(p.relative_to(ROOT)) for p in (THAI, OVERRIDES, ICONS)]

    def revert(self) -> None:
        self.thai, self.thai_indent = _read(THAI)
        self.overrides, self.overrides_indent = _read(OVERRIDES)
        self.icons, self.icons_indent = _read(ICONS)
        self._remember_saved_state()
        self.history.clear()
        self.dirty = False


def cluster_index(manifest: TokenMap) -> dict[str, list[str]]:
    """Every manifest cluster, grouped under the base it is built from."""
    grouped: dict[str, list[str]] = {}
    for token in manifest.tokens:
        kind, value = token.split(":", 1)
        if kind == "cluster":
            grouped.setdefault(value[0], []).append(token)
        elif kind == "char":
            grouped.setdefault(value, []).append(token)
    return grouped


def contextual_index(draft: Draft) -> dict[str, list[str]]:
    """Manifest clusters grouped by the exact contextual artwork they consume."""
    grouped: dict[str, list[str]] = {}
    contextual = draft.thai["contextual"]
    for token in draft.manifest.tokens:
        kind, cluster = token.split(":", 1)
        if kind != "cluster" or len(cluster) < 2:
            continue
        try:
            lower = [mark for mark in cluster[1:] if draft.builder._mark_class(mark) == "below"]
            upper = "".join(
                mark for mark in cluster[1:] if draft.builder._mark_class(mark) == "above"
            )
        except EncodingError:
            continue
        base = cluster[0]
        if upper:
            family = "left" if base in contextual["upper_left_bases"] else "normal"
            grouped.setdefault(f"upper:{family}:{upper}", []).append(token)
        if lower:
            family = "left" if base in contextual["lower_left_bases"] else "normal"
            grouped.setdefault(f"lower:{family}:{lower[0]}", []).append(token)
            if base in contextual["lower_base_variants"]:
                grouped.setdefault(f"base::{base}", []).append(token)
    return grouped


def _tokenise(text: str, icons: dict) -> list[str]:
    """Clusters, plus `<Name>` for an icon so a badge can be previewed inline."""
    tokens: list[str] = []
    rest = text
    plain = ""

    def flush() -> None:
        nonlocal plain
        tokens.extend(token_for(cluster) for cluster in segment(plain))
        plain = ""

    while rest:
        if rest[0] == "<" and ">" in rest:
            name, tail = rest[1:].split(">", 1)
            if name in icons:
                flush()
                tokens.append(f"icon:{name}")
                rest = tail
                continue
        plain += rest[0]
        rest = rest[1:]
    flush()
    return tokens


class Handler(BaseHTTPRequestHandler):
    draft: Draft

    def log_message(self, *args) -> None:      # quiet; the browser is the UI
        pass

    def _send(self, code: int, body: bytes, kind: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload: dict, code: int = 200) -> None:
        self._send(code, json.dumps(payload, ensure_ascii=False).encode(),
                   "application/json; charset=utf-8")

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/api/state":
            d = self.draft
            windows = json.loads(WINDOWS.read_text())["windows"] if WINDOWS.exists() else {}
            self._json({
                "cell": d.thai["cell"],
                "bases": d.thai["bases"],
                "contextual": d.thai["contextual"],
                "hand_drawn": d.thai.get("_hand_drawn", []),
                "overrides": d.overrides["overrides"],
                "icons": d.icons["glyphs"],
                "clusters": cluster_index(d.manifest),
                "contextual_clusters": contextual_index(d),
                "direct": list(d.manifest.direct),
                "worst": d.thai.get("_verification", {}).get("worst", []),
                "windows": windows,
                "rom_note": d.rom_note,
                "dirty": d.dirty,
                "undo_depths": {
                    key: max(0, len(history) - 1)
                    for key, history in d.history.items()
                },
                "advance_range": [MIN_ADVANCE, MAX_ADVANCE],
            })
        else:
            self._json({"error": "no such path"}, 404)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError as exc:
            return self._json({"error": f"bad json: {exc}"}, 400)
        d = self.draft
        try:
            if self.path == "/api/compose":
                tokens = body.get("tokens")
                if tokens is None:
                    tokens = _tokenise(body.get("text", ""), d.icons["glyphs"])
                return self._json({"glyphs": d.compose(tokens)})
            if self.path == "/api/base":
                depth = d.put_base(body["char"], body["rows"], body.get("advance"))
                return self._json({"entry": d.thai["bases"][body["char"]],
                                   "undo_depth": depth, "dirty": d.dirty})
            if self.path == "/api/contextual":
                depth = d.put_contextual(
                    body["area"], body.get("family"), body["key"], body["rows"]
                )
                return self._json({"contextual": d.thai["contextual"],
                                   "undo_depth": depth, "dirty": d.dirty})
            if self.path == "/api/icon":
                depth = d.put_icon(body["name"], body["rows"], body.get("advance"),
                                   body.get("cell_span"))
                return self._json({"entry": d.icons["glyphs"][body["name"]],
                                   "undo_depth": depth, "dirty": d.dirty})
            if self.path == "/api/override":
                depth = d.put_override(
                    body["token"], body.get("rows"), body.get("advance"),
                    body.get("reason", ""), body.get("sample", "")
                )
                return self._json({"overrides": d.overrides["overrides"],
                                   "undo_depth": depth, "dirty": d.dirty})
            if self.path == "/api/undo":
                return self._json(d.undo(body["kind"], body["key"], body.get("area"),
                                         body.get("family")))
            if self.path == "/api/save":
                return self._json({"written": d.save(), "dirty": False})
            if self.path == "/api/revert":
                d.revert()
                return self._json({"dirty": False})
            if self.path == "/api/rebuild":
                done = subprocess.run(
                    [sys.executable, str(Path(__file__).with_name("build_atlas.py"))],
                    capture_output=True, text=True, cwd=ROOT,
                )
                return self._json({"ok": done.returncode == 0,
                                   "out": done.stdout + done.stderr})
        except (EncodingError, KeyError, ValueError) as exc:
            return self._json({"error": str(exc)}, 400)
        self._json({"error": "no such path"}, 404)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8731)
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args()

    ThreadingHTTPServer.allow_reuse_address = False   # never silently steal a port
    Handler.draft = Draft()
    if Handler.draft.rom_note:
        print(f"note: no clean ROM, stock-font glyphs will not preview\n  {Handler.draft.rom_note}")
    url = f"http://127.0.0.1:{args.port}"
    print(f"font editor on {url}   (ctrl-c to stop)")
    if not args.no_open:
        webbrowser.open(url)
    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    except OSError as exc:
        print(f"cannot listen on port {args.port}: {exc}\n"
              f"another editor is probably already running -- open {url}, "
              f"or pass --port")
        return 1
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
