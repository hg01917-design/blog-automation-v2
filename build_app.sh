#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
DIST_DIR="$ROOT_DIR/dist"
BUILD_DIR="$ROOT_DIR/build"
SPEC_FILE="$ROOT_DIR/Blog Automation v2.spec"

echo "[1/4] Build cleanup targets"
echo "- $DIST_DIR"
echo "- $BUILD_DIR"

echo "[2/4] Removing old build outputs"
rm -rf "$DIST_DIR" "$BUILD_DIR"

echo "[3/4] Running PyInstaller"
python3 -m PyInstaller "$SPEC_FILE"

echo "[4/4] Build complete"
echo "Output directory: $DIST_DIR"
