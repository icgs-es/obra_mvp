#!/usr/bin/env bash
set -euo pipefail

# snapshot_now.sh
# Uso:
#   ./snapshot_now.sh "mensaje de commit opcional"
#
# Hace:
#  1) Inicializa git si no existe
#  2) Crea/actualiza .gitignore si no existe
#  3) Commit con mensaje (o mensaje por defecto con timestamp)
#  4) Crea una tag anotada con timestamp
#  5) Genera ZIP/TAR.GZ del HEAD en carpeta backups/ (solo archivos trackeados)
#  6) Genera un ZIP 'full' excluyendo directorios pesados comunes (por si aún no trackeaste todo)

PROJECT_ROOT="$(pwd)"
BACKUPS_DIR="${PROJECT_ROOT}/backups"
TS="$(date +"%Y%m%d-%H%M%S")"
TAG="snapshot-${TS}"
COMMIT_MSG="${1:-estado estable (${TS})}"

echo "→ Proyecto: ${PROJECT_ROOT}"
mkdir -p "${BACKUPS_DIR}"

# 1) init git si no existe
if [ ! -d .git ]; then
  echo "→ Inicializando repositorio git..."
  git init
  git config user.name "${GIT_AUTHOR_NAME:-local-user}" || true
  git config user.email "${GIT_AUTHOR_EMAIL:-local@example.com}" || true
fi

# 2) .gitignore mínimo si no existe
if [ ! -f .gitignore ]; then
  echo "→ Creando .gitignore básico..."
  cat > .gitignore <<'EOF'
# Python/Django
__pycache__/
*.py[cod]
*.pyo
*.pyd
*.sqlite3
db.sqlite3
*.log
*.pot
*.pyc
*.egg-info/
.venv/
venv/
.env
.env.*
*.env

# Node/Front
node_modules/
dist/
build/

# Django static/media
staticfiles/
static_root/
media/

# VCS/IDE
.git/
*.swp
*.swo
.idea/
.vscode/
.DS_Store

# Coverage / pytest
.coverage
htmlcov/
.pytest_cache/

# Docker local volumes (si existieran)
infra/pgdata/
infra/pgadmin_data/
EOF
fi

# 3) commit
echo "→ Añadiendo cambios y creando commit..."
git add -A
if git diff --cached --quiet; then
  echo "   (No hay cambios para commitear)"
else
  git commit -m "${COMMIT_MSG}"
fi

# 4) tag
if git rev-parse "${TAG}" >/dev/null 2>&1; then
  echo "→ Tag ${TAG} ya existe; creando una nueva con sufijo..."
  TAG="${TAG}-dup"
fi
git tag -a "${TAG}" -m "Snapshot automático ${TS}" || true
echo "→ Tag creada: ${TAG}"

# 5) backups con git archive (solo lo trackeado)
ZIP_NAME="obra_mvp_${TS}.zip"
TAR_NAME="obra_mvp_${TS}.tar"
echo "→ Creando backups en ${BACKUPS_DIR} (solo tracked)..."
git archive --format=zip --output "${BACKUPS_DIR}/${ZIP_NAME}" HEAD
git archive --format=tar --output "${BACKUPS_DIR}/${TAR_NAME}" HEAD
gzip -f "${BACKUPS_DIR}/${TAR_NAME}"

# 6) backup FULL (excluyendo comunes)
FULL_ZIP="obra_mvp_${TS}_full.zip"
echo "→ Creando backup FULL (excluye venv/node_modules/__pycache__/media/staticfiles/infra/pgdata)..."
zip -r "${BACKUPS_DIR}/${FULL_ZIP}" . \
  -x "*.git/*" ".git/*" \
     "node_modules/*" \
     "venv/*" ".venv/*" \
     "__pycache__/*" \
     "media/*" \
     "staticfiles/*" "static_root/*" \
     "infra/pgdata/*" "infra/pgadmin_data/*"

echo "✔ Hecho."
echo "   - Commit/tag: $(git rev-parse --short HEAD)  (${TAG})"
echo "   - ZIP tracked: ${BACKUPS_DIR}/${ZIP_NAME}"
echo "   - TAR.GZ tracked: ${BACKUPS_DIR}/${TAR_NAME}.gz"
echo "   - ZIP FULL: ${BACKUPS_DIR}/${FULL_ZIP}"
