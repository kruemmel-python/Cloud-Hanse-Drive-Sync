#!/usr/bin/env bash
set -euo pipefail

PYTHON_EXE="${PYTHON_EXE:-python3}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SPEC_PATH="$SCRIPT_DIR/hanse_pygame.spec"
DIST_PATH="$SCRIPT_DIR/dist/linux"
WORK_PATH="$SCRIPT_DIR/.pyinstaller/linux"

mkdir -p "$DIST_PATH" "$WORK_PATH"

"$PYTHON_EXE" -m PyInstaller --noconfirm --clean --distpath "$DIST_PATH" --workpath "$WORK_PATH" "$SPEC_PATH"
status=$?
if [ "$status" -ne 0 ]; then
  echo "PyInstaller failed with exit code $status." >&2
  exit "$status"
fi

echo
echo "Ubuntu build complete."
echo "Binary: $DIST_PATH/Hanse_Atheria/Hanse_Atheria"
