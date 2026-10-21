#!/bin/bash
# ==============================================================================
# build_package.sh - Erstellt das offizielle Release-Paket fuer PyPI & GitHub
# ==============================================================================
set -e

PROJECT_DIR="/opt/shadow-sentinel"
VENV_PIP="/opt/admin-agent/venv/bin/pip"
VENV_PYTHON="/opt/admin-agent/venv/bin/python3"

echo "[BUILD] 1. Stelle sicher, dass 'build' und 'twine' installiert sind..."
$VENV_PIP install --upgrade build twine

echo "[BUILD] 2. Wechsle ins Projektverzeichnis: $PROJECT_DIR"
cd "$PROJECT_DIR"

echo "[BUILD] 3. Bereinige vorherige Build-Artefakte..."
rm -rf dist/ build/ *.egg-info shadow_sentinel/*.egg-info

echo "[BUILD] 4. Erstelle universelles Wheel (.whl) und Quell-Archiv (.tar.gz)..."
$VENV_PYTHON -m build

echo "[BUILD] 5. Validiere Paket-Metadaten mit Twine..."
$VENV_PYTHON -m twine check dist/*

echo ""
echo "=============================================================================="
echo "✅ BUILD ERFOLGREICH ABGESCHLOSSEN!"
echo "Die distributionsfertigen Pakete liegen in: $PROJECT_DIR/dist/"
ls -la dist/
echo "=============================================================================="
