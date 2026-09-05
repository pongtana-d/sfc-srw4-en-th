#!/usr/bin/env python3
"""Direct pixel editor for the game-ready Thai title-logo asset."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.en_title import build_en_title_logo, EN_TITLE_LOGO_PC  # noqa: E402
from srw4.en_baseline import EN_SHA256  # noqa: E402
from srw4.rom import Rom, sha256  # noqa: E402


ASSET = ROOT / "data" / "assets" / "title-logo.json"
PAGE = Path(__file__).with_name("title_logo_editor.html")
CLEAN_ROM = ROOT / "rom" / "Dai-4-ji Super Robot Taisen (English combo).sfc"
WIDTH = 200
HEIGHT = 64
PALETTE = (
    "0000", "7FFF", "57FF", "03FF", "037F", "02FF", "027F", "01FF",
    "017F", "00FB", "0017", "0047", "4C00", "3C00", "2C00", "1C00",
)

# Measured per palette index from the stable EN title screenshot in Mesen.
# Display only: saved indices and ROM BGR555 entries remain authoritative.
TITLE_DISPLAY_RGB = (
    "#000000", "#C6C6C6", "#C6C684", "#C6C600", "#C6AD00", "#C69400",
    "#C67B00", "#C66300", "#C64200", "#AD2900", "#940000", "#290800",
    "#00007B", "#000063", "#000042", "#000029",
)


def rgb_from_bgr555(raw: str) -> str:
    value = int(raw, 16)
    red = (value & 31) * 255 // 31
    green = ((value >> 5) & 31) * 255 // 31
    blue = ((value >> 10) & 31) * 255 // 31
    return f"#{red:02X}{green:02X}{blue:02X}"


def validate_rows(rows: object) -> list[str]:
    if not isinstance(rows, list) or len(rows) != HEIGHT:
        raise ValueError(f"logo needs exactly {HEIGHT} rows")
    normalized = []
    for index, row in enumerate(rows):
        if not isinstance(row, str) or len(row) != WIDTH:
            raise ValueError(f"row {index} needs exactly {WIDTH} pixels")
        row = row.upper()
        if any(pixel not in "0123456789ABCDEF" for pixel in row):
            raise ValueError(f"row {index} contains a color outside palette 0..15")
        normalized.append(row)
    return normalized


class LogoDocument:
    def __init__(self, path: Path = ASSET) -> None:
        self.path = path
        self.document: dict[str, object] = {}
        self.reload()

    def reload(self) -> None:
        document = json.loads(self.path.read_text(encoding="utf-8"))
        rows = validate_rows(document.get("rows"))
        box = document.get("screen_box")
        if box != {"x": 24, "y": 48, "width": WIDTH, "height": HEIGHT}:
            raise ValueError("title-logo screen_box no longer matches the stock OBJ surface")
        if document.get("palette_bgr555") != list(PALETTE):
            raise ValueError("title-logo palette no longer matches stock OBJ palette 7")
        document["rows"] = rows
        self.document = document

    def state(self) -> dict[str, object]:
        rows = self.document["rows"]
        assert isinstance(rows, list)
        try:
            display_path = str(self.path.relative_to(ROOT))
        except ValueError:
            display_path = str(self.path)
        return {
            "text": self.document.get("text"),
            "rows": rows,
            "width": WIDTH,
            "height": HEIGHT,
            "screen_box": self.document["screen_box"],
            "palette_bgr555": list(PALETTE),
            "palette_rgb": [rgb_from_bgr555(value) for value in PALETTE],
            "palette_display_rgb": list(TITLE_DISPLAY_RGB),
            "sha256": hashlib.sha256("".join(rows).encode()).hexdigest(),
            "path": display_path,
        }

    def save(self, rows: object) -> dict[str, object]:
        normalized = validate_rows(rows)
        document = dict(self.document)
        document["rows"] = normalized
        document["manual_edit"] = True
        document["editor"] = "tools/title_logo_editor.py"
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=self.path.parent,
            prefix=self.path.name + ".", suffix=".tmp", delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(document, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            temporary.replace(self.path)
        finally:
            temporary.unlink(missing_ok=True)
        self.reload()
        return self.state()

    def verify(self) -> dict[str, object]:
        self.reload()
        base = CLEAN_ROM.read_bytes()
        if sha256(base) != EN_SHA256:
            raise ValueError("English base ROM does not match the pinned version")
        payload, report = build_en_title_logo(self.path.parent.parent, base)
        current = (ROOT / "build/srw4-en-th.sfc").read_bytes()
        image = Rom(bytearray(current))
        image.write_at(EN_TITLE_LOGO_PC, payload)
        image.fix_checksum()
        output = ROOT / "build/srw4-en-th-title-edited.sfc"
        output.write_bytes(image.to_bytes())
        return {
            "ok": True,
            "logo": report,
            "output": str(output),
            "sha256": sha256(output.read_bytes()),
            "pixel_roundtrip": "exact",
        }


class Handler(BaseHTTPRequestHandler):
    logo: LogoDocument

    def log_message(self, *_args) -> None:
        pass

    def send_body(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, payload: dict[str, object], code: int = 200) -> None:
        self.send_body(
            code, json.dumps(payload, ensure_ascii=False).encode(),
            "application/json; charset=utf-8",
        )

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            self.send_body(200, PAGE.read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/api/state":
            self.send_json(self.logo.state())
        elif self.path == "/title-background.png":
            self.send_body(200, (ROOT / "assets/title-background-en.png").read_bytes(), "image/png")
        else:
            self.send_json({"error": "no such path"}, 404)

    def do_POST(self) -> None:
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
            if self.path == "/api/save":
                return self.send_json({"state": self.logo.save(body.get("rows"))})
            if self.path == "/api/revert":
                self.logo.reload()
                return self.send_json({"state": self.logo.state()})
            if self.path == "/api/verify":
                return self.send_json(self.logo.verify())
            self.send_json({"error": "no such path"}, 404)
        except (json.JSONDecodeError, OSError, ValueError) as exc:
            self.send_json({"error": str(exc)}, 400)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8732)
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args()
    Handler.logo = LogoDocument()
    ThreadingHTTPServer.allow_reuse_address = False
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"title-logo editor: {url}")
    print(f"source of truth: {ASSET.relative_to(ROOT)}")
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
