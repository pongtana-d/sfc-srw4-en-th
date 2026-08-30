#!/bin/sh
set -eu

SOURCE=${1:?source PNG required}
SHADOW_SOURCE=${2:?shadow-source PNG required}
OUTPUT=${3:?output PNG required}

# Preserve the source image exactly except for dark-blue extrusion pixels inside
# the title-logo bounds.  The generated repair is resized only to compensate
# for the editor's one-pixel canvas normalization.
ffmpeg -hide_banner -loglevel error -y \
  -i "$SOURCE" \
  -i "$SHADOW_SOURCE" \
  -filter_complex "[0:v]format=gbrp[base];[1:v]scale=1314:1197:flags=neighbor,format=gbrp,split[shadow][mask_source];[mask_source]geq=r='if(between(X,125,1225)*between(Y,275,620)*lt(r(X,Y),85)*lt(g(X,Y),90)*gt(b(X,Y),45)*gt(b(X,Y),1.35*r(X,Y))*gt(b(X,Y),1.20*g(X,Y)),255,0)':g='if(between(X,125,1225)*between(Y,275,620)*lt(r(X,Y),85)*lt(g(X,Y),90)*gt(b(X,Y),45)*gt(b(X,Y),1.35*r(X,Y))*gt(b(X,Y),1.20*g(X,Y)),255,0)':b='if(between(X,125,1225)*between(Y,275,620)*lt(r(X,Y),85)*lt(g(X,Y),90)*gt(b(X,Y),45)*gt(b(X,Y),1.35*r(X,Y))*gt(b(X,Y),1.20*g(X,Y)),255,0)',format=gray[mask];[base][shadow][mask]maskedmerge,format=rgb24[out]" \
  -map '[out]' -frames:v 1 "$OUTPUT"
