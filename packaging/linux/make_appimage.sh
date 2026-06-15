#!/usr/bin/env bash
# packaging/linux/make_appimage.sh — package the frozen dist/Orrin into an AppImage (I6).
#
# We ship a .tar.gz today; an AppImage is a single double-clickable file (the Linux
# equivalent of "a real app"). Run AFTER pyinstaller, on a Linux runner. The native
# window still needs WebKitGTK installed; without it Orrin falls back to a browser tab.
set -euo pipefail

VERSION="${ORRIN_VERSION:-0.0.0}"
ARCH="${ARCH:-x86_64}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DIST="$ROOT/dist"
APPDIR="$DIST/Orrin.AppDir"

[ -d "$DIST/Orrin" ] || { echo "dist/Orrin not found — run pyinstaller first"; exit 1; }

rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin"
cp -a "$DIST/Orrin/." "$APPDIR/usr/bin/"

# Icon — generated with Pillow (already a dependency), so there's no asset to ship.
python - "$APPDIR/orrin.png" <<'PY'
import sys
from PIL import Image, ImageDraw
img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
ImageDraw.Draw(img).ellipse((32, 32, 224, 224), fill=(99, 102, 241, 255))
img.save(sys.argv[1])
PY

cat > "$APPDIR/orrin.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Orrin
Exec=Orrin
Icon=orrin
Categories=Utility;
Terminal=false
EOF

cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/Orrin" "$@"
EOF
chmod +x "$APPDIR/AppRun"

# appimagetool (pinned to the continuous release). CI has no FUSE, so extract-and-run.
TOOL="$DIST/appimagetool"
if [ ! -x "$TOOL" ]; then
  curl -fsSL -o "$TOOL" \
    "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-${ARCH}.AppImage"
  chmod +x "$TOOL"
fi

OUT="$DIST/Orrin-linux-${ARCH}.AppImage"
ARCH="$ARCH" "$TOOL" --appimage-extract-and-run "$APPDIR" "$OUT"
echo "built $OUT"
