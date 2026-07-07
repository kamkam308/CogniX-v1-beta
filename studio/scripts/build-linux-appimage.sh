#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
studio_dir="$(cd "$script_dir/.." && pwd)"

cd "$studio_dir"
bash "$script_dir/patch-linuxdeploy-gtk.sh"

if NO_STRIP=1 npm exec tauri -- build --bundles appimage; then
  exit 0
fi

echo "Initial AppImage build failed; patching linuxdeploy GTK plugin again and retrying once."
bash "$script_dir/patch-linuxdeploy-gtk.sh"
NO_STRIP=1 npm exec tauri -- build --bundles appimage
