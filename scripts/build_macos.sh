#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION="$(.venv/bin/python -c 'import re; from pathlib import Path; print(re.search(r"^version = \"([^\"]+)\"", Path("pyproject.toml").read_text(), re.M).group(1))')"
.venv/bin/python -m PyInstaller --noconfirm --clean --windowed --name "Little Cursor" \
  --osx-bundle-identifier io.littlecursor.desktop \
  --add-data 'ui:ui' --add-data 'mcp.json:.' --add-data 'examples/demo_workspace:examples/demo_workspace' \
  --hidden-import examples.mcp_server app.py
mkdir -p release
hdiutil create -volname 'Little Cursor' -srcfolder 'dist/Little Cursor.app' -ov -format UDZO "release/LittleCursor-${VERSION}-macOS.dmg"
