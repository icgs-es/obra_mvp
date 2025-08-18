#!/usr/bin/env bash
set -euo pipefail
if [[ ! -f 'infra/docker-compose.dev.yml' ]]; then echo 'Ejecuta desde la RAÍZ del proyecto.'; exit 1; fi
COMPOSE='docker compose -f infra/docker-compose.dev.yml'
$COMPOSE up -d --build
echo 'Esperando DB 5s...'; sleep 5
$COMPOSE exec web python manage.py makemigrations || true
$COMPOSE exec web python manage.py migrate
echo 'OK -> http://localhost:8001/health'
