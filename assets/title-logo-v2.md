# Title logo refinement

The built-in image generation tool produced `title-logo-concept-v2.png`
from `title-logo-in-game-en-final.png` (edit target) and
`title-logo-concept-v1.png` (style reference).

Prompt: Polish only the Thai title logo, preserving the text
“ซูเปอร์โรบอตวอร์ส 4”. Match the original concept's clean gold bevels,
continuous highlights, coherent contours and dark blue extrusion. Preserve
the background and menu. Use SNES pixel art without blur or new elements.

The generated full-screen image is a concept, not emulator evidence.
Only its logo face is imported by `python3 tools/import_title_logo_v2.py`.
The importer masks the background before resizing, quantizes to the stock
palette and rebuilds the existing 10-pixel extrusion. Production builds
continue to read the editable `data/assets/title-logo.json` directly.

Native preview: `build/repro/title-logo-v2-native.png`.
Build: `python3 tools/build_en_th_full_dialogue.py`.
