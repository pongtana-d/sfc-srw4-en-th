#!/usr/bin/env python3
"""A pixel editor for the font data this project already tuned.

  tools/font_editor.py            -> http://127.0.0.1:8731

It edits `data/font/thai.json` (133 bases, 13 marks) and
`data/font/renewal-overrides.json`, and it previews through the real
`AtlasBuilder`, so what the browser shows is what the atlas will build. No
composition rule is reimplemented here.

Metrics that describe the bitmap -- a base's `left`/`ink`/`top`, a mark's
`sprite`/`height`/`width`/`y` -- are derived from the pixels on every commit,
so the two can never drift apart. Only the two judgement calls stay editable:
a base's `advance` and a mark's `dx` nudge.
"""

from __future__ import annotations

import argparse
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
from srw4.rom import Rom, RomError  # noqa: E402
from srw4.text import THAI_MARKS, token_for  # noqa: E402
from srw4.tokens import EncodingError, TokenMap  # noqa: E402

CLEAN_ROM = ROOT / "rom" / "Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc"
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
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=indent) + "\n")


class Draft:
    """The working copy: what the browser edits before anyone saves."""

    def __init__(self) -> None:
        self.thai, self.thai_indent = _read(THAI)
        self.overrides, self.overrides_indent = _read(OVERRIDES)
        self.icons, self.icons_indent = _read(ICONS)
        self.manifest = TokenMap.load(MANIFEST)
        self.dirty = False
        try:
            rom = Rom.load_clean(CLEAN_ROM).to_bytes()
            self.rom_note = None
        except (OSError, RomError) as exc:
            rom = b""
            self.rom_note = str(exc)
        self.builder = AtlasBuilder(FONT_DIR, rom)

    def _sync(self) -> None:
        self.builder.bases = self.thai["bases"]
        self.builder.marks = self.thai["marks"]
        self.builder.raised_rows = self.thai["raised_rows"]
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

    def put_base(self, char: str, rows: list[int], advance: int | None) -> None:
        rows = [int(r) & 0xFF for r in rows][:CELL_ROWS]
        rows += [0] * (CELL_ROWS - len(rows))
        left, ink = ink_columns(rows)
        top = next((i for i, r in enumerate(rows) if r), 0)
        if advance is None:
            advance = min(max(ink + 1, MIN_ADVANCE), MAX_ADVANCE)
        entry = dict(self.thai["bases"].get(char, {}))
        entry.update({"rows": rows, "left": left, "ink": ink, "top": top,
                      "advance": int(advance)})
        self.thai["bases"][char] = entry
        self.dirty = True

    def put_mark(self, char: str, rows: list[int], dx: int) -> None:
        """A mark is stored left-aligned, with its own top row and height."""
        rows = [int(r) & 0xFF for r in rows][:CELL_ROWS]
        rows += [0] * (CELL_ROWS - len(rows))
        lit = [i for i, r in enumerate(rows) if r]
        entry = dict(self.thai["marks"].get(char, {}))
        if not lit:
            entry.update({"sprite": [], "height": 0, "width": 0, "y": 0, "dx": int(dx)})
        else:
            left, width = ink_columns(rows)
            top, bottom = lit[0], lit[-1]
            sprite = [(rows[i] << left) & 0xFF for i in range(top, bottom + 1)]
            entry.update({"sprite": sprite, "height": len(sprite), "width": width,
                          "y": top, "dx": int(dx)})
        self.thai["marks"][char] = entry
        self.dirty = True

    def put_icon(self, name: str, rows: list[int], advance: int | None,
                 cell_span: int | None) -> None:
        """Icons are fixed artwork: the bitmap is the whole of it, no composition.

        The migration recorded a sha256 to prove each bitmap still matched the
        manifest it came from. Redrawing one makes that claim false, so the
        hash is restamped and the entry says plainly that it was redrawn.
        """
        rows = [int(r) & 0xFF for r in rows][:CELL_ROWS]
        rows += [0] * (CELL_ROWS - len(rows))
        entry = dict(self.icons["glyphs"].get(name, {}))
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
        self.dirty = True

    def put_override(self, token: str, rows: list[int] | None,
                     advance: int | None, reason: str, sample: str) -> None:
        if rows is None:
            self.overrides["overrides"].pop(token, None)
        else:
            if not reason.strip() or not sample.strip():
                raise EncodingError("an override needs a reason and a regression sample")
            entry = {"rows": [int(r) & 0xFF for r in rows], "reason": reason,
                     "sample": sample}
            if advance is not None:
                entry["advance"] = int(advance)
            self.overrides["overrides"][token] = entry
        self.dirty = True

    def save(self) -> list[str]:
        _write(THAI, self.thai, self.thai_indent)
        _write(OVERRIDES, self.overrides, self.overrides_indent)
        _write(ICONS, self.icons, self.icons_indent)
        self.dirty = False
        return [str(p.relative_to(ROOT)) for p in (THAI, OVERRIDES, ICONS)]

    def revert(self) -> None:
        self.thai, self.thai_indent = _read(THAI)
        self.overrides, self.overrides_indent = _read(OVERRIDES)
        self.icons, self.icons_indent = _read(ICONS)
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


def _tokenise(text: str, icons: dict) -> list[str]:
    """Clusters, plus `<Name>` for an icon so a badge can be previewed inline."""
    tokens: list[str] = []
    rest = text
    while rest:
        if rest[0] == "<" and ">" in rest:
            name, tail = rest[1:].split(">", 1)
            if name in icons:
                tokens.append(f"icon:{name}")
                rest = tail
                continue
        head, rest = rest[0], rest[1:]
        while rest and rest[0] in THAI_MARKS:
            head, rest = head + rest[0], rest[1:]
        tokens.append(token_for(head))
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
                "marks": d.thai["marks"],
                "raised_rows": d.thai["raised_rows"],
                "hand_drawn": d.thai.get("_hand_drawn", []),
                "overrides": d.overrides["overrides"],
                "icons": d.icons["glyphs"],
                "clusters": cluster_index(d.manifest),
                "direct": list(d.manifest.direct),
                "worst": d.thai.get("_verification", {}).get("worst", []),
                "windows": windows,
                "rom_note": d.rom_note,
                "dirty": d.dirty,
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
                d.put_base(body["char"], body["rows"], body.get("advance"))
                return self._json({"entry": d.thai["bases"][body["char"]], "dirty": True})
            if self.path == "/api/mark":
                d.put_mark(body["char"], body["rows"], body.get("dx", 0))
                return self._json({"entry": d.thai["marks"][body["char"]], "dirty": True})
            if self.path == "/api/icon":
                d.put_icon(body["name"], body["rows"], body.get("advance"),
                           body.get("cell_span"))
                return self._json({"entry": d.icons["glyphs"][body["name"]], "dirty": True})
            if self.path == "/api/override":
                d.put_override(body["token"], body.get("rows"), body.get("advance"),
                               body.get("reason", ""), body.get("sample", ""))
                return self._json({"overrides": d.overrides["overrides"], "dirty": True})
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
