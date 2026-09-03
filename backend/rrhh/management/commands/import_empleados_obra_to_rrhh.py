from django.core.management.base import BaseCommand
from django.db import transaction

from planificacion_obra.models import EmpleadoObra
from rrhh.models import Empleado, GrupoTrabajo, EmpleadoGrupoTrabajo


class Command(BaseCommand):
    help = "Crea/actualiza rrhh.Empleado desde planificacion_obra.EmpleadoObra."

    def add_arguments(self, parser):
        parser.add_argument("--team-id", type=int, required=True)
        parser.add_argument("--commit", action="store_true")

    def handle(self, *args, **options):
        team_id = options["team_id"]
        commit = options["commit"]

        empleados_obra = EmpleadoObra.objects.filter(team_id=team_id).select_related("team").order_by("nombre")

        self.stdout.write(f"Team ID: {team_id}")
        self.stdout.write(f"EmpleadoObra origen: {empleados_obra.count()}")
        self.stdout.write(f"Modo: {'COMMIT' if commit else 'DRY-RUN'}")

        grupo_obra = GrupoTrabajo.objects.filter(
            team_id=team_id,
            tipo=GrupoTrabajo.TipoGrupo.OBRA,
            nombre="Obra",
        ).first()

        if not grupo_obra:
            raise SystemExit("No existe GrupoTrabajo 'Obra' para este team.")

        created = 0
        updated = 0
        memberships_created = 0
        skipped = 0

        with transaction.atomic():
            for eo in empleados_obra:
                nombre = (eo.nombre or "").strip()
                if not nombre:
                    skipped += 1
                    continue

                referencia = f"empleadoobra:{eo.id}"

                situacion = Empleado.Situacion.ACTIVO
                if getattr(eo, "situacion", "") == "BAJA":
                    situacion = Empleado.Situacion.BAJA

                empleado, was_created = Empleado.objects.get_or_create(
                    team=eo.team,
                    origen="access_empleado_obra",
                    referencia_externa=referencia,
                    defaults={
                        "codigo": str(eo.legacy_id or eo.id),
                        "nombre_completo": nombre,
                        "empresa_empleadora": eo.empresa_origen or eo.team.name,
                        "tipo_relacion": Empleado.TipoRelacion.PROPIO,
                        "area_principal": Empleado.AreaPrincipal.OBRA,
                        "puesto": eo.categoria or "",
                        "profesion": eo.tipo or "",
                        "situacion": situacion,
                        "fecha_alta": eo.fecha_alta,
                        "fecha_baja": eo.fecha_baja,
                        "coste_hora": eo.precio_hora,
                        "es_fichable": True,
                        "es_planificable_obra": True,
                        "activo": situacion != Empleado.Situacion.BAJA,
                        "raw_data": {
                            "source_model": "planificacion_obra.EmpleadoObra",
                            "empleado_obra_id": eo.id,
                            "legacy_id": eo.legacy_id,
                            "categoria": eo.categoria,
                            "tipo": eo.tipo,
                            "situacion": eo.situacion,
                            "raw_data": eo.raw_data,
                        },
                    },
                )

                if was_created:
                    created += 1
                else:
                    changed = False
                    updates = {
                        "nombre_completo": nombre,
                        "empresa_empleadora": eo.empresa_origen or eo.team.name,
                        "area_principal": Empleado.AreaPrincipal.OBRA,
                        "puesto": eo.categoria or "",
                        "profesion": eo.tipo or "",
                        "situacion": situacion,
                        "fecha_alta": eo.fecha_alta,
                        "fecha_baja": eo.fecha_baja,
                        "coste_hora": eo.precio_hora,
                        "es_planificable_obra": True,
                        "activo": situacion != Empleado.Situacion.BAJA,
                    }
                    for field, value in updates.items():
                        if getattr(empleado, field) != value:
                            setattr(empleado, field, value)
                            changed = True
                    if changed:
                        empleado.save()
                        updated += 1

                membership, membership_created = EmpleadoGrupoTrabajo.objects.get_or_create(
                    empleado=empleado,
                    grupo=grupo_obra,
                    defaults={
                        "rol": eo.categoria or "",
                        "activo": True,
                    },
                )
                if membership_created:
                    memberships_created += 1

            if not commit:
                transaction.set_rollback(True)

        self.stdout.write("")
        self.stdout.write(f"Creados: {created}")
        self.stdout.write(f"Actualizados: {updated}")
        self.stdout.write(f"Membresías Obra creadas: {memberships_created}")
        self.stdout.write(f"Omitidos: {skipped}")

        if not commit:
            self.stdout.write(self.style.WARNING("DRY-RUN: no se guardaron cambios."))
        else:
            self.stdout.write(self.style.SUCCESS("Importación aplicada."))
