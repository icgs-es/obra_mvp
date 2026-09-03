#!/usr/bin/env bash
set -euo pipefail

TEAM_ID="${1:-1}"
REPORT_DIR="/opt/obra_mvp/reports/planificacion_obra"
TS="$(date +%Y%m%d_%H%M%S)"

CONTAINER_AUDIT="/tmp/audit_planificacion_obra_${TS}.csv"
CONTAINER_TIPO="/tmp/coste_real_por_obra_tipo_${TS}.csv"
CONTAINER_DESV="/tmp/desviaciones_obra_${TS}.csv"

HOST_AUDIT="${REPORT_DIR}/audit_planificacion_obra_${TS}.csv"
HOST_TIPO="${REPORT_DIR}/coste_real_por_obra_tipo_${TS}.csv"
HOST_DESV="${REPORT_DIR}/desviaciones_obra_${TS}.csv"

mkdir -p "$REPORT_DIR"

echo "=== GENERAR INFORMES PLANIFICACION OBRA ==="
echo "Team ID: $TEAM_ID"
echo ""

echo "=== 1/3 AUDITORIA GENERAL POR OBRA ==="
docker compose -f docker-compose.prod.yml exec web sh -lc "
cd /app/backend || cd /app
python manage.py audit_planificacion_obra --team-id ${TEAM_ID} --csv ${CONTAINER_AUDIT}
"

echo ""
echo "=== 2/3 COSTE REAL POR OBRA Y TIPO DE RECURSO ==="
docker compose -f docker-compose.prod.yml exec -T web sh <<PYSH
cd /app/backend || cd /app

python manage.py shell <<'PY'
from decimal import Decimal
from pathlib import Path
import csv
from django.db.models import Sum, Count
from planificacion_obra.models import TareaRecursoReal, ObraPlanificacion

TEAM_ID = int("${TEAM_ID}")
output = Path("${CONTAINER_TIPO}")

obras = {
    o.legacy_cod_obra: o.nombre
    for o in ObraPlanificacion.objects.filter(team_id=TEAM_ID)
}

qs = (
    TareaRecursoReal.objects
    .filter(team_id=TEAM_ID)
    .values("legacy_cod_obra", "legacy_tipo_recurso")
    .annotate(
        filas=Count("id"),
        coste_real=Sum("costo_recurso_real"),
        cantidad=Sum("cantidad"),
        horas_reales=Sum("horas_reales"),
    )
    .order_by("legacy_cod_obra", "legacy_tipo_recurso")
)

with output.open("w", newline="", encoding="utf-8-sig") as f:
    writer = csv.writer(f, delimiter=";")
    writer.writerow([
        "cod_obra",
        "obra",
        "tipo_recurso",
        "filas",
        "cantidad",
        "horas_reales",
        "coste_real",
    ])

    for row in qs:
        cod_obra = row["legacy_cod_obra"]
        tipo = row["legacy_tipo_recurso"] or "-"
        coste = row["coste_real"] or Decimal("0")
        cantidad = row["cantidad"] or Decimal("0")
        horas = row["horas_reales"] or Decimal("0")

        writer.writerow([
            cod_obra,
            obras.get(cod_obra, ""),
            tipo,
            row["filas"],
            str(cantidad).replace(".", ","),
            str(horas).replace(".", ","),
            str(coste).replace(".", ","),
        ])

print(f"CSV generado: {output}")
print("Filas:", qs.count())
PY
PYSH

echo ""
echo "=== 3/3 DESVIACIONES EJECUTIVAS POR OBRA ==="
docker compose -f docker-compose.prod.yml exec -T web sh <<PYSH
cd /app/backend || cd /app

python manage.py shell <<'PY'
from decimal import Decimal
from pathlib import Path
import csv
from django.db.models import Sum, Count
from planificacion_obra.models import ObraPlanificacion, TareaRecursoPrevisto, TareaRecursoReal

TEAM_ID = int("${TEAM_ID}")
output = Path("${CONTAINER_DESV}")

def money(value):
    return str((value or Decimal("0")).quantize(Decimal("0.0001"))).replace(".", ",")

def pct(value):
    return str((value or Decimal("0")).quantize(Decimal("0.01"))).replace(".", ",")

def estado_desviacion(previsto, real):
    previsto = previsto or Decimal("0")
    real = real or Decimal("0")

    if previsto == 0 and real > 0:
        return "SIN_PREVISTO_CON_COSTE_REAL"
    if previsto == 0 and real == 0:
        return "SIN_MOVIMIENTO_ECONOMICO"

    ejecucion = (real / previsto) * Decimal("100")

    if ejecucion > Decimal("110"):
        return "SOBRECOSTE"
    if ejecucion >= Decimal("85"):
        return "EJECUCION_ALTA"
    if ejecucion >= Decimal("40"):
        return "EJECUCION_NORMAL"
    return "EJECUCION_BAJA"

obras = ObraPlanificacion.objects.filter(team_id=TEAM_ID).order_by("legacy_cod_obra")

with output.open("w", newline="", encoding="utf-8-sig") as f:
    writer = csv.writer(f, delimiter=";")
    writer.writerow([
        "cod_obra",
        "obra",
        "tareas",
        "recursos_previstos",
        "coste_previsto",
        "recursos_reales",
        "coste_real",
        "ejecucion_pct",
        "desviacion_real_menos_previsto",
        "estado",
    ])

    for obra in obras:
        previstos = TareaRecursoPrevisto.objects.filter(team_id=TEAM_ID, legacy_cod_obra=obra.legacy_cod_obra)
        reales = TareaRecursoReal.objects.filter(team_id=TEAM_ID, legacy_cod_obra=obra.legacy_cod_obra)

        coste_previsto = previstos.aggregate(v=Sum("costo_recurso"))["v"] or Decimal("0")
        coste_real = reales.aggregate(v=Sum("costo_recurso_real"))["v"] or Decimal("0")
        desviacion = coste_real - coste_previsto
        ejecucion = (coste_real / coste_previsto * Decimal("100")) if coste_previsto else Decimal("0")

        writer.writerow([
            obra.legacy_cod_obra,
            obra.nombre,
            obra.tareas.count(),
            previstos.count(),
            money(coste_previsto),
            reales.count(),
            money(coste_real),
            pct(ejecucion),
            money(desviacion),
            estado_desviacion(coste_previsto, coste_real),
        ])

print(f"CSV generado: {output}")
PY
PYSH

echo ""
echo "=== COPIAR INFORMES AL HOST ==="
docker compose -f docker-compose.prod.yml cp "web:${CONTAINER_AUDIT}" "$HOST_AUDIT"
docker compose -f docker-compose.prod.yml cp "web:${CONTAINER_TIPO}" "$HOST_TIPO"
docker compose -f docker-compose.prod.yml cp "web:${CONTAINER_DESV}" "$HOST_DESV"

echo ""
echo "=== INFORMES GENERADOS ==="
ls -lh "$HOST_AUDIT"
ls -lh "$HOST_TIPO"
ls -lh "$HOST_DESV"

echo ""
echo "Rutas:"
echo "$HOST_AUDIT"
echo "$HOST_TIPO"
echo "$HOST_DESV"
