#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ ! -f frontend/dist/index.html ]; then
  echo "Build the interface first: cd frontend && npm ci && npm run build"
  exit 1
fi
movement_lens_python="${MOVEMENT_LENS_PYTHON:-python3}"
exec "$movement_lens_python" -m uvicorn movement_lens.app:app --host 127.0.0.1 --port 8770
