from decimal import Decimal
import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Sum, Count

from usuarios.models import Team
from planificacion_obra.models import (
    ObraPlanificacion,
    FaseObra,
    UnidadObra,
    CapituloCatalogo,
    PartidaCatalogo,
    RecursoCatalogo,
    EmpleadoObra,
    AlmacenObra,
    TareaObra,
    RecursoAlmacenMovimiento,
    TareaRecursoPrevisto,
    TareaRecursoReal,
)


class Command(BaseCommand):
    help = "Auditoría global del módulo Planificación de Obra."

    def add_arguments(self, parser):
        parser.add_argument("--team-id", type=int, default=1)
        parser.add_argument("--obra", type=int, default=None, help="Filtrar por legacy CodObra")
        parser.add_argument("--csv", type=str, default=None, help="Ruta para exportar resumen por obra en CSV")

    def money(self, value):
        value = value or Decimal("0")
        return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def pct(self, value, total):
        if not total:
            return "0,00%"
        result = (value / total) * Decimal("100")
        return f"{result:.2f}%".replace(".", ",")

    def handle(self, *args, **options):
        team_id = options["team_id"]
        obra_cod = options["obra"]

        team = Team.objects.filter(id=team_id).first()
        if not team:
            raise CommandError(f"No existe Team con id={team_id}")

        obras = ObraPlanificacion.objects.filter(team=team).order_by("legacy_cod_obra")
        if obra_cod is not None:
            obras = obras.filter(legacy_cod_obra=obra_cod)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=== AUDITORIA PLANIFICACION OBRA ==="))
        self.stdout.write(f"Team: {team.id} · {team.name}")

        self.stdout.write("")
        self.stdout.write("=== CONTEOS GLOBALES ===")
        self.stdout.write(f"Obras: {ObraPlanificacion.objects.filter(team=team).count()}")
        self.stdout.write(f"Fases: {FaseObra.objects.filter(team=team).count()}")
        self.stdout.write(f"Unidades: {UnidadObra.objects.filter(team=team).count()}")
        self.stdout.write(f"Capítulos catálogo: {CapituloCatalogo.objects.filter(team=team).count()}")
        self.stdout.write(f"Partidas catálogo: {PartidaCatalogo.objects.filter(team=team).count()}")
        self.stdout.write(f"Recursos catálogo: {RecursoCatalogo.objects.filter(team=team).count()}")
        self.stdout.write(f"Empleados: {EmpleadoObra.objects.filter(team=team).count()}")
        self.stdout.write(f"Almacenes: {AlmacenObra.objects.filter(team=team).count()}")
        self.stdout.write(f"Tareas: {TareaObra.objects.filter(team=team).count()}")
        self.stdout.write(f"Movimientos almacén: {RecursoAlmacenMovimiento.objects.filter(team=team).count()}")
        self.stdout.write(f"Recursos previstos: {TareaRecursoPrevisto.objects.filter(team=team).count()}")
        self.stdout.write(f"Recursos reales: {TareaRecursoReal.objects.filter(team=team).count()}")

        self.stdout.write("")
        self.stdout.write("=== RESUMEN POR OBRA ===")

        total_previsto_global = Decimal("0")
        total_real_global = Decimal("0")
        csv_rows = []

        for obra in obras:
            tareas = TareaObra.objects.filter(team=team, obra=obra)
            previstos = TareaRecursoPrevisto.objects.filter(team=team, legacy_cod_obra=obra.legacy_cod_obra)
            reales = TareaRecursoReal.objects.filter(team=team, legacy_cod_obra=obra.legacy_cod_obra)
            movimientos = RecursoAlmacenMovimiento.objects.filter(team=team, legacy_cod_obra=obra.legacy_cod_obra)

            coste_previsto = previstos.aggregate(total=Sum("costo_recurso"))["total"] or Decimal("0")
            coste_real = reales.aggregate(total=Sum("costo_recurso_real"))["total"] or Decimal("0")
            desviacion = coste_real - coste_previsto

            total_previsto_global += coste_previsto
            total_real_global += coste_real

            self.stdout.write("")
            self.stdout.write(self.style.WARNING(f"{obra.legacy_cod_obra} · {obra.nombre}"))
            self.stdout.write(f"  Tareas: {tareas.count()}")
            self.stdout.write(f"  Recursos previstos: {previstos.count()}")
            self.stdout.write(f"  Coste previsto: {self.money(coste_previsto)} €")
            self.stdout.write(f"  Recursos reales: {reales.count()}")
            self.stdout.write(f"  Coste real: {self.money(coste_real)} €")
            self.stdout.write(f"  Ejecución económica: {self.pct(coste_real, coste_previsto)}")
            self.stdout.write(f"  Desviación real - previsto: {self.money(desviacion)} €")
            self.stdout.write(f"  Movimientos almacén: {movimientos.count()}")

            csv_rows.append({
                "cod_obra": obra.legacy_cod_obra,
                "obra": obra.nombre,
                "tareas": tareas.count(),
                "recursos_previstos": previstos.count(),
                "coste_previsto": coste_previsto,
                "recursos_reales": reales.count(),
                "coste_real": coste_real,
                "ejecucion_economica_pct": (coste_real / coste_previsto * Decimal("100")) if coste_previsto else Decimal("0"),
                "desviacion_real_menos_previsto": desviacion,
                "movimientos_almacen": movimientos.count(),
            })

        self.stdout.write("")
        self.stdout.write("=== TOTALES ECONOMICOS ===")
        self.stdout.write(f"Coste previsto total: {self.money(total_previsto_global)} €")
        self.stdout.write(f"Coste real total: {self.money(total_real_global)} €")
        self.stdout.write(f"Ejecución económica global: {self.pct(total_real_global, total_previsto_global)}")
        self.stdout.write(f"Desviación global: {self.money(total_real_global - total_previsto_global)} €")

        self.stdout.write("")
        self.stdout.write("=== COSTE REAL POR TIPO RECURSO ===")
        qs_tipo = (
            TareaRecursoReal.objects
            .filter(team=team)
            .values("legacy_tipo_recurso")
            .annotate(total=Sum("costo_recurso_real"), filas=Count("id"))
            .order_by("-total")
        )
        for row in qs_tipo:
            tipo = row["legacy_tipo_recurso"] or "-"
            total = row["total"] or Decimal("0")
            self.stdout.write(f"{tipo}: {row['filas']} filas · {self.money(total)} €")

        self.stdout.write("")
        self.stdout.write("=== PENDIENTES / NO ENLAZADOS ===")
        self.stdout.write(f"Previstos sin tarea: {TareaRecursoPrevisto.objects.filter(team=team, tarea_obra__isnull=True).count()}")
        self.stdout.write(f"Previstos sin recurso catálogo: {TareaRecursoPrevisto.objects.filter(team=team, recurso__isnull=True).count()}")
        self.stdout.write(f"Reales sin tarea: {TareaRecursoReal.objects.filter(team=team, tarea_obra__isnull=True).count()}")
        self.stdout.write(f"Reales sin unidad: {TareaRecursoReal.objects.filter(team=team, unidad_obra__isnull=True).count()}")
        self.stdout.write(f"Reales sin partida: {TareaRecursoReal.objects.filter(team=team, partida__isnull=True).count()}")
        self.stdout.write(f"Reales sin empleado ni recurso: {TareaRecursoReal.objects.filter(team=team, empleado__isnull=True, recurso__isnull=True).count()}")
        self.stdout.write(f"Movimientos almacén sin obra: {RecursoAlmacenMovimiento.objects.filter(team=team, obra__isnull=True).count()}")
        self.stdout.write(f"Movimientos almacén sin almacén: {RecursoAlmacenMovimiento.objects.filter(team=team, almacen__isnull=True).count()}")
        self.stdout.write(f"Movimientos almacén sin recurso catálogo: {RecursoAlmacenMovimiento.objects.filter(team=team, recurso__isnull=True).count()}")

        csv_path = options.get("csv")
        if csv_path:
            output_path = Path(csv_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            fieldnames = [
                "cod_obra",
                "obra",
                "tareas",
                "recursos_previstos",
                "coste_previsto",
                "recursos_reales",
                "coste_real",
                "ejecucion_economica_pct",
                "desviacion_real_menos_previsto",
                "movimientos_almacen",
            ]

            with output_path.open("w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
                writer.writeheader()
                for row in csv_rows:
                    writer.writerow({
                        "cod_obra": row["cod_obra"],
                        "obra": row["obra"],
                        "tareas": row["tareas"],
                        "recursos_previstos": row["recursos_previstos"],
                        "coste_previsto": str(row["coste_previsto"]).replace(".", ","),
                        "recursos_reales": row["recursos_reales"],
                        "coste_real": str(row["coste_real"]).replace(".", ","),
                        "ejecucion_economica_pct": str(row["ejecucion_economica_pct"].quantize(Decimal("0.01"))).replace(".", ","),
                        "desviacion_real_menos_previsto": str(row["desviacion_real_menos_previsto"]).replace(".", ","),
                        "movimientos_almacen": row["movimientos_almacen"],
                    })

            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS(f"CSV exportado: {output_path}"))

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("AUDITORIA FINALIZADA."))
