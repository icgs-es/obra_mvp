#!/usr/bin/env bash
set -euo pipefail

FOLDER=""
TEAM="INVERADRIDE"
APPLY=0
COMPOSE_FILE="docker-compose.prod.yml"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --folder)
      FOLDER="$2"
      shift 2
      ;;
    --team)
      TEAM="$2"
      shift 2
      ;;
    --apply)
      APPLY=1
      shift
      ;;
    *)
      echo "Argumento no reconocido: $1"
      echo "Uso:"
      echo "  ./sync_access_obras.sh --folder /app/imports/access_sync_YYYY-MM-DD"
      echo "  ./sync_access_obras.sh --folder /app/imports/access_sync_YYYY-MM-DD --apply"
      exit 1
      ;;
  esac
done

if [[ -z "$FOLDER" ]]; then
  echo "ERROR: falta --folder"
  echo "Ejemplo:"
  echo "  ./sync_access_obras.sh --folder /app/imports/access_sync_2026-05-19"
  exit 1
fi

TS=$(date +%Y%m%d_%H%M%S)
REPORT="$FOLDER/sync_access_partidas_tareas_${TS}.json"

echo "=== ACCESS SYNC OBRAS ==="
echo "Folder: $FOLDER"
echo "Team: $TEAM"
echo "Modo: $([[ "$APPLY" == "1" ]] && echo APPLY || echo DRY-RUN)"
echo ""

echo "=== 1. VALIDAR CONTENEDORES ==="
sudo docker compose -f "$COMPOSE_FILE" ps web db

echo ""
echo "=== 2. VALIDAR ARCHIVOS EN CONTENEDOR ==="
sudo docker compose -f "$COMPOSE_FILE" exec -T web sh -lc "
test -f '$FOLDER/tblPartida.xlsx' &&
test -f '$FOLDER/tblTareas.xlsx' &&
test -f '$FOLDER/tblTareasRecursos.xlsx' &&
test -f '$FOLDER/tblTareasRecursosInicial.xlsx' &&
echo 'OK: archivos principales encontrados'
"

echo ""
echo "=== 3. DJANGO CHECK ==="
sudo docker compose -f "$COMPOSE_FILE" exec -T web sh -lc "
cd /app/backend && python manage.py check
"

if [[ "$APPLY" == "1" ]]; then
  BACKUP_DIR="/opt/obra_mvp/backups/access_sync_${TS}"

  echo ""
  echo "=== 4. BACKUP DB PRE-SYNC ==="
  sudo mkdir -p "$BACKUP_DIR"

  sudo docker compose -f "$COMPOSE_FILE" exec -T db sh -lc \
    'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' | gzip | sudo tee "$BACKUP_DIR/db_before_access_sync.sql.gz" >/dev/null

  sudo ls -lh "$BACKUP_DIR/db_before_access_sync.sql.gz"
fi

echo ""
echo "=== 5. SINCRONIZAR PARTIDAS + TAREAS ==="

APPLY_FLAG=""
if [[ "$APPLY" == "1" ]]; then
  APPLY_FLAG="--apply"
fi

sudo docker compose -f "$COMPOSE_FILE" exec -T web sh -lc "
cd /app/backend &&
python manage.py sync_access_partidas_tareas \
  --folder '$FOLDER' \
  --team '$TEAM' \
  --sample 20 \
  --json-out '$REPORT' \
  $APPLY_FLAG
"

echo ""
echo "=== 6. SINCRONIZAR TAREAS RECURSOS REALES ==="

REALES_CMD="python manage.py import_access_tareas_recursos_reales_planificacion '$FOLDER' --team-id 1"

if [[ "$APPLY" == "1" ]]; then
  REALES_CMD="$REALES_CMD --commit"
fi

sudo docker compose -f "$COMPOSE_FILE" exec -T web sh -lc "
cd /app/backend &&
$REALES_CMD
"

echo ""
echo "=== 7. REPORTE PARTIDAS + TAREAS ==="
sudo docker compose -f "$COMPOSE_FILE" exec -T web sh -lc "
ls -lh '$REPORT'
"

echo ""
echo "OK: proceso terminado."
