#!/usr/bin/env bash
set -euo pipefail

tauri_cache="${TAURI_CACHE_DIR:-$HOME/.cache/tauri}"
plugin="$tauri_cache/linuxdeploy-plugin-gtk.sh"

if [[ ! -f "$plugin" ]]; then
  echo "linuxdeploy GTK plugin not found at $plugin; skipping patch."
  exit 0
fi

if grep -q "CogniX Arch gdk-pixbuf guard" "$plugin"; then
  echo "linuxdeploy GTK plugin already patched."
  exit 0
fi

perl -0pi -e 's|copy_tree "\$gdk_pixbuf_binarydir" "\$APPDIR/"|# CogniX Arch gdk-pixbuf guard\nif [ -d "$gdk_pixbuf_binarydir" ]; then\n    copy_tree "$gdk_pixbuf_binarydir" "$APPDIR/"\nelse\n    echo "WARNING: GDK PixBuf binary directory is missing: $gdk_pixbuf_binarydir"\n    echo "Continuing without external GDK PixBuf loaders; this is expected on some Arch Linux builds."\n    mkdir -p "$APPDIR/$gdk_pixbuf_binarydir"\nfi|g' "$plugin"

perl -0pi -e 's|if \[ -x "\$gdk_pixbuf_query" \]; then\n    echo "Updating pixbuf cache in \$APPDIR/\$gdk_pixbuf_cache_file"\n    "\$gdk_pixbuf_query" > "\$APPDIR/\$gdk_pixbuf_cache_file"\nelse\n    echo "WARNING: gdk-pixbuf-query-loaders not found"\nfi|if [ -x "$gdk_pixbuf_query" ] && [ -d "$gdk_pixbuf_moduledir" ]; then\n    echo "Updating pixbuf cache in $APPDIR/$gdk_pixbuf_cache_file"\n    "$gdk_pixbuf_query" > "$APPDIR/$gdk_pixbuf_cache_file"\nelse\n    echo "WARNING: gdk-pixbuf-query-loaders or loader module directory not found"\n    mkdir -p "$(dirname "$APPDIR/$gdk_pixbuf_cache_file")"\n    : > "$APPDIR/$gdk_pixbuf_cache_file"\nfi|g' "$plugin"

perl -0pi -e 's|PATCH_ARRAY=\(\n    "\$gtk3_immodulesdir"\n    "\$gtk3_printbackendsdir"\n    "\$gdk_pixbuf_moduledir"\n\)|PATCH_ARRAY=(\n    "$gtk3_immodulesdir"\n    "$gtk3_printbackendsdir"\n)\nif [ -d "$gdk_pixbuf_moduledir" ]; then\n    PATCH_ARRAY+=( "$gdk_pixbuf_moduledir" )\nelse\n    echo "WARNING: Skipping missing GDK PixBuf module directory: $gdk_pixbuf_moduledir"\nfi|g' "$plugin"

chmod +x "$plugin"
echo "Patched linuxdeploy GTK plugin for Arch-compatible AppImage builds."
