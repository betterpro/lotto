#!/usr/bin/env bash
set -euo pipefail

echo "==> Installing Python dependencies"
pip install -r requirements.txt

echo "==> Building React Mini App"
cd mini_app
npm ci
npm run build
cd ..

echo "==> Build complete"
