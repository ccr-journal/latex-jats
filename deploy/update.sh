#!/usr/bin/env bash
# Pull the latest images, recreate containers, and reclaim disk space
# from superseded image layers. Run from the directory containing
# docker-compose.yml and .env.
set -euo pipefail

docker compose pull
docker compose up -d
docker image prune -f
