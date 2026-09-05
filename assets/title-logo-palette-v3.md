# Palette-constrained imagegen experiment

Generated with the built-in imagegen tool. Reference images:
`title-logo-concept-v1.png` and `title-logo-palette-reference.png`.

Raw output: `title-logo-palette-v3.png`, 2216×709, 135338 distinct RGB colors.
35.53% of pixels exactly match one of the supplied palette entries, including
black background. The model did not obey the exact grid or palette constraint.

`title-logo-palette-v3-native.png` is a separate conversion preview: nearest
neighbor resize to 200×64 and nearest RGB palette assignment, no dithering,
no face extraction, no new extrusion. Index zero is transparent. Its palette
is copied from `data/assets/title-logo.json`. This experiment does not replace
the production asset or ROM.

## Exact generation prompt

Create ONLY an isolated game-ready Thai SNES title logo. Image 1 is the lettering and gold bevel/blue extrusion style reference. Image 2 is the EXACT allowed palette, not an element to include. Text verbatim: "ซูเปอร์โรบอตวอร์ส 4". Preserve the reference lettering and all Thai marks. No menu, no Earth, no screenshot, no swatches, no labels.
CRITICAL: Design on a native 200 x 64 PIXEL GRID. Each pixel is a single solid color. Output may be exactly 200x64 or a NEAREST-NEIGHBOR integer enlargement of that exact grid (e.g. 1600x512, each native pixel an 8x8 solid square). Use wide 25:8 aspect ratio. No subpixel detail. No antialiasing. No dithering. No soft shading. No smooth curves below grid resolution.
Allowed RGB colors ONLY: #000000 background/transparency key; #FFFFFF #FFFFAC #FFFF00 #FFDE00 #FFBD00 #FF9C00 #FF7B00 #FF5A00 #DE3900 #BD0000 #391000 for face/bevel; #00009C #00007B #00005A #000039 for dark blue depth.
Solid pure black background. The entire gold face, Thai marks and depth must fit inside 200x64, with at least 2 native pixels margin. Bold forward-slanted Thai letters, polished continuous white/pale-yellow 1-pixel bevel, carefully stepped gold-orange bands like reference, deep-blue solid extrusion 8-10 native pixels down and 3-4 right. Strong clean readable letter silhouettes and intentional pixel contours; no stray pixels. One line only, numeral 4 on right. Render at the specified palette from the beginning, not a full-color illustration.
