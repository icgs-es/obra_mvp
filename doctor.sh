#!/usr/bin/env bash
set -euo pipefail

COMPOSE="docker compose -f infra/docker-compose.dev.yml"

echo "== 1) Docker daemon =="
systemctl is-active docker || { echo "Docker daemon NO activo. Ejecuta: sudo systemctl enable --now docker"; exit 1; }
echo "Docker activo."

echo
echo "== 2) Servicios compose =="
$COMPOSE ps || { echo "No pude leer servicios. ¿Estás en la RAÍZ del proyecto?"; exit 1; }

echo
echo "== 3) Logs web (últimas 120 líneas) =="
$COMPOSE logs --no-color --tail=120 web || true

echo
echo "== 4) Puertos escuchando (8001/5050/5432) =="
ss -lntp | egrep ':8001|:5050|:5432' || echo "No veo puertos abiertos aún."

echo
echo "== 5) Health desde host =="
curl -sS http://localhost:8001/health || echo "No responde health."

echo
echo "== 6) Check Django dentro del contenedor =="
$COMPOSE exec web python manage.py check || true

echo
echo "== 7) Rutas Django cargadas =="
$COMPOSE exec web python - <<'PY' || true
from django.urls import get_resolver
print([p.pattern._route for p in get_resolver().url_patterns])
PY

echo
echo "== 8) Recordatorio =="
echo "Si web está 'Exited', revisa arriba 'Logs web' para la traza exacta."
