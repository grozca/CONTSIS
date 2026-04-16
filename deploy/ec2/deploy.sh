#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

mkdir -p runtime/data/config runtime/alertas/config runtime/logs runtime/data

if [ ! -f .env ]; then
  cp .env.example .env
  echo ".env created from .env.example. Review it before exposing the service."
fi

docker compose up -d --build

echo
echo "CONTSIS is starting."
echo "Check status with: docker compose ps"
echo "Check logs with: docker compose logs -f"
