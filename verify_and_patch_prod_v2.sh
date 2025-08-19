
#!/usr/bin/env bash
# verify_and_patch_prod_v2.sh — Verifica y (opcionalmente) parchea el despliegue sin machacar tus cambios.
# Uso:
#   bash verify_and_patch_prod_v2.sh /opt/obra_mvp [--patch]
#
# - Sin --patch: solo informa problemas.
# - Con --patch: aplica correcciones mínimas (rutas .env, build context, Caddyfile, SSL flags).
set -euo pipefail

PROJECT_DIR="${1:-/opt/obra_mvp}"
PATCH="${2:-}"
COMPOSE="${PROJECT_DIR}/infra/docker-compose.prod.yml"
ENVFILE="${PROJECT_DIR}/deploy/.env.prod"
CADDYFILE="${PROJECT_DIR}/infra/caddy/Caddyfile"
WEBDOCKER="${PROJECT_DIR}/infra/web.Dockerfile"
PRODSET="${PROJECT_DIR}/backend/config/settings/prod.py"
MANAGE="${PROJECT_DIR}/backend/manage.py"

echo "→ Proyecto: ${PROJECT_DIR}"

fail=0
warn(){ echo "WARN: $*"; }
err(){ echo "ERROR: $*"; fail=1; }

# 0) Archivos clave
[ -f "$COMPOSE" ]  || { err "Falta $COMPOSE"; }
[ -f "$ENVFILE" ]  || { err "Falta $ENVFILE"; }
[ -f "$WEBDOCKER" ]|| { err "Falta $WEBDOCKER"; }
[ -f "$MANAGE" ]   || { err "Falta $MANAGE"; }
[ -f "$CADDYFILE" ]|| { warn "Falta $CADDYFILE (no crítico si usas otra ruta)"; }
[ -f "$PRODSET" ]  || { warn "Falta $PRODSET (el pack suele traerlo)"; }

# 1) docker-compose: version, env_file, build.context, Caddyfile path
if [ -f "$COMPOSE" ]; then
  echo "→ Revisando $COMPOSE"
  # a) version obsoleto
  if grep -qE '^\s*version:' "$COMPOSE"; then
    echo "  - Tiene 'version:' (obsoleto)."
    if [ "$PATCH" = "--patch" ]; then
      cp "$COMPOSE" "$COMPOSE.bak.$(date +%s)"
      sed -i '/^\s*version:/d' "$COMPOSE"
      echo "    * Eliminado 'version:'"
    else
      warn "Quita 'version:' para evitar warnings."
    fi
  fi

  # b) env_file a ruta absoluta (web, db, caddy)
  if ! grep -q "$ENVFILE" "$COMPOSE"; then
    echo "  - env_file no apunta a $ENVFILE"
    if [ "$PATCH" = "--patch" ]; then
      cp "$COMPOSE" "$COMPOSE.bak.$(date +%s)"
      awk -v envf="$ENVFILE" '
        BEGIN{in_env=0}
        # Detecta env_file:
        /^\s*env_file\s*:\s*$/ {print; print gensub(/^(\s*).*/, "\\1- " envf, 1); in_env=1; next}
        # Si venían entradas previas tipo "- xyz", sáltalas
        in_env==1 && /^\s*-\s*/ { next }
        { in_env=0; print }
      ' "$COMPOSE" > "$COMPOSE.tmp" && mv "$COMPOSE.tmp" "$COMPOSE"
      echo "    * Ajustado env_file → $ENVFILE"
    else
      warn "Ajusta env_file a ruta absoluta $ENVFILE en web/db/caddy."
    fi
  fi

  # c) build.context debe ser '..' porque el compose está en infra/
  if ! awk '
      /^\s*build:\s*$/ {b=1; next}
      b==1 && /^\s*context:\s*\.\.$/ {ok=1; b=0}
      b==1 && /^\s*context:\s*\.$/ {ok=0}
      END{exit ok?0:1}
    ' "$COMPOSE"; then
    echo "  - build.context no apunta a '..'"
    if [ "$PATCH" = "--patch" ]; then
      cp "$COMPOSE" "$COMPOSE.bak.$(date +%s)"
      awk '
        /^\s*build:\s*$/ {print; b=1; next}
        b==1 && /^\s*context:\s*\.$/ {sub(/\.$/,".."); print; b=0; next}
        {print}
      ' "$COMPOSE" > "$COMPOSE.tmp" && mv "$COMPOSE.tmp" "$COMPOSE"
      echo "    * Ajustado build.context a '..'"
    else
      warn "Cambia context: . → .. dentro del bloque build:"
    fi
  fi

  # d) Ruta del Caddyfile en volumes
  if grep -q '\./infra/caddy/Caddyfile' "$COMPOSE"; then
    echo "  - Monta ./infra/caddy/Caddyfile (incorrecto desde infra/)"
    if [ "$PATCH" = "--patch" ]; then
      cp "$COMPOSE" "$COMPOSE.bak.$(date +%s)"
      sed -i 's#\./infra/caddy/Caddyfile#./caddy/Caddyfile#g' "$COMPOSE"
      echo "    * Corregido a ./caddy/Caddyfile"
    else
      warn "Usa ./caddy/Caddyfile en el volumen de caddy."
    fi
  fi
fi

# 2) prod.py — SSL redir configurable + CSRF http/https (útil si pruebas por IP)
if [ -f "$PRODSET" ]; then
  echo "→ Revisando $PRODSET"
  need_patch=0
  grep -q 'SECURE_SSL_REDIRECT = os.getenv("SECURE_SSL_REDIRECT"' "$PRODSET" || need_patch=1
  grep -q 'http://' "$PRODSET" || need_patch=1
  if [ $need_patch -eq 1 ]; then
    echo "  - prod.py no parece soportar modo IP/HTTP."
    if [ "$PATCH" = "--patch" ]; then
      cp "$PRODSET" "$PRODSET.bak.$(date +%s)"
      python3 - "$PRODSET" <<'PY'
import sys, re, os
p = sys.argv[1]
s = open(p,'r',encoding='utf-8').read()
s = s.replace("SECURE_SSL_REDIRECT = True",
              "SECURE_SSL_REDIRECT = os.getenv(\"SECURE_SSL_REDIRECT\", \"true\").lower() == \"true\"")
s = s.replace("SESSION_COOKIE_SECURE = True","SESSION_COOKIE_SECURE = SECURE_SSL_REDIRECT")
s = s.replace("CSRF_COOKIE_SECURE = True","CSRF_COOKIE_SECURE = SECURE_SSL_REDIRECT")
if "CSRF_TRUSTED_ORIGINS" not in s or "http://" not in s:
    block = '''
CSRF_TRUSTED_ORIGINS = []
for h in ALLOWED_HOSTS:
    h = h.strip()
    if not h or h == "*":
        continue
    CSRF_TRUSTED_ORIGINS.append(f"https://{h}")
    CSRF_TRUSTED_ORIGINS.append(f"http://{h}")
'''
    s += "\n"+block+"\n"
open(p,'w',encoding='utf-8').write(s)
print("    * prod.py parcheado para SSL opcional y CSRF http/https")
PY
    else
      warn "Ajusta prod.py: SECURE_SSL_REDIRECT configurable + CSRF_TRUSTED_ORIGINS http/https."
    fi
  fi
fi

# 3) Detecta paquete del proyecto (wsgi)
if [ -f "$MANAGE" ]; then
  pkg=$(ls -1 ${PROJECT_DIR}/backend/*/wsgi.py 2>/dev/null | sed -E 's#.*/backend/([^/]+)/wsgi.py#\1#' || true)
  if [ -n "${pkg:-}" ]; then
    echo "→ Paquete Django detectado: ${pkg}"
  else
    warn "No encuentro backend/*/wsgi.py. Crea backend/config/wsgi.py si hace falta."
  fi
fi

if [ $fail -ne 0 ]; then
  echo "✖ Hay errores. Corrige o ejecuta con --patch para aplicar arreglos mínimos."
  exit 1
fi

echo "✔ Verificaciones completadas. Usa '--patch' para aplicar fixes mínimos."
