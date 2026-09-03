from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from django.apps import apps
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone


CONTRACT_TYPES = {"PER. CONT.", "M.O. CONT."}


def clean_json(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def clean_dict(data):
    if not isinstance(data, dict):
        return {}
    return {str(k): clean_json(v) for k, v in data.items()}


def precio_hora_from_recurso(recurso):
    unidad = (recurso.unidad or "").strip().upper()
    if unidad in {"H", "HR", "HRS", "HORA", "HORAS"}:
        return recurso.precio_unidad_uso
    return None


class Command(BaseCommand):
    help = "Crea empleados contratados desde RecursoCatalogo y reconcilia TareaRecursoReal PER. CONT. / M.O. CONT."

    def add_arguments(self, parser):
        parser.add_argument("--team", required=True)
        parser.add_argument("--commit", action="store_true")
        parser.add_argument("--sample", type=int, default=30)
        parser.add_argument("--json-out", default="")

    def handle(self, *args, **options):
        Team = apps.get_model("usuarios", "Team")
        EmpleadoObra = apps.get_model("planificacion_obra", "EmpleadoObra")
        RecursoCatalogo = apps.get_model("planificacion_obra", "RecursoCatalogo")
        TareaRecursoReal = apps.get_model("planificacion_obra", "TareaRecursoReal")

        team_name = options["team"]
        commit = bool(options["commit"])
        sample = int(options["sample"] or 30)

        try:
            team = Team.objects.get(name=team_name)
        except Team.DoesNotExist as exc:
            raise CommandError(f"No existe Team con name={team_name}") from exc

        empleados = {
            e.legacy_id: e
            for e in EmpleadoObra.objects.filter(team=team).exclude(legacy_id=None)
        }

        recursos = {
            r.legacy_id: r
            for r in RecursoCatalogo.objects.filter(team=team).exclude(legacy_id=None)
        }

        qs_null = TareaRecursoReal.objects.filter(
            team=team,
            legacy_tipo_recurso__in=list(CONTRACT_TYPES),
            empleado__isnull=True,
        )
        qs_generic = TareaRecursoReal.objects.filter(
            team=team,
            legacy_tipo_recurso__in=list(CONTRACT_TYPES),
            empleado__legacy_id=0,
        )
        qs = (qs_null | qs_generic).distinct()

        candidatos = {}
        descartados = Counter()
        to_reconcile = []

        for r in qs:
            legacy_id = r.legacy_id_recurso
            emp = empleados.get(legacy_id)
            rec = recursos.get(legacy_id)

            if emp and emp.legacy_id != 0:
                to_reconcile.append((r, emp))
                continue

            if not rec:
                descartados["sin_recurso_catalogo"] += 1
                continue

            if rec.tipo not in CONTRACT_TYPES:
                descartados[f"recurso_tipo_{rec.tipo or 'VACIO'}"] += 1
                continue

            candidatos[legacy_id] = rec

        created_employees = 0
        reconciled = 0
        backup_dir = None

        report = {
            "mode": "COMMIT" if commit else "DRY_RUN",
            "team": {"id": team.id, "name": str(team)},
            "pending_contract_reales": qs.count(),
            "candidate_employees_count": len(candidatos),
            "discarded": dict(descartados),
            "candidate_sample": [
                {
                    "legacy_id": rec.legacy_id,
                    "nombre": rec.nombre,
                    "tipo": rec.tipo,
                    "unidad": rec.unidad,
                    "precio_unidad_uso": clean_json(rec.precio_unidad_uso),
                    "usos": qs.filter(legacy_id_recurso=rec.legacy_id).count(),
                }
                for rec in list(candidatos.values())[:sample]
            ],
            "created": {
                "empleados_contratados": 0,
                "reales_reconciled": 0,
            },
            "backup": None,
        }

        self.stdout.write("")
        self.stdout.write("=== SYNC ACCESS CONTRATADOS OBRA ===")
        self.stdout.write(f"Team: {team}")
        self.stdout.write(f"Modo: {'COMMIT' if commit else 'DRY-RUN'}")
        self.stdout.write(f"Pendientes contratados: {qs.count()}")
        self.stdout.write(f"Candidatos empleados contratados: {len(candidatos)}")
        self.stdout.write("Descartados:")
        for k, v in descartados.most_common():
            self.stdout.write(f"  {k}: {v}")

        if commit:
            backup_dir = Path("/app/backups") / f"contratados_obra_sync_{timezone.now().strftime('%Y%m%d_%H%M%S')}"
            backup_dir.mkdir(parents=True, exist_ok=True)
            report["backup"] = str(backup_dir)

            call_command(
                "dumpdata",
                "planificacion_obra",
                output=str(backup_dir / "planificacion_obra_before.json"),
                indent=2,
                verbosity=0,
            )

            with transaction.atomic():
                for legacy_id, rec in sorted(candidatos.items()):
                    emp, created = EmpleadoObra.objects.get_or_create(
                        team=team,
                        legacy_id=legacy_id,
                        defaults={
                            "nombre": rec.nombre,
                            "tipo": "CONTRATADO",
                            "categoria": "OTRO",
                            "situacion": "ACTIVO",
                            "precio_hora": precio_hora_from_recurso(rec),
                            "empresa_origen": "RecursoCatalogo / tblRecursos",
                            "observaciones": (
                                f"Empleado contratado generado desde RecursoCatalogo. "
                                f"Tipo recurso={rec.tipo}; unidad={rec.unidad}; "
                                f"precio_unidad_uso={rec.precio_unidad_uso}"
                            ),
                            "raw_data": {
                                "origen": "RecursoCatalogo",
                                "legacy_id_recurso": rec.legacy_id,
                                "nombre_recurso": rec.nombre,
                                "tipo_recurso": rec.tipo,
                                "unidad": rec.unidad,
                                "precio_unidad_uso": clean_json(rec.precio_unidad_uso),
                                "raw_recurso": clean_dict(rec.raw_data),
                            },
                        },
                    )
                    empleados[legacy_id] = emp
                    if created:
                        created_employees += 1

                qs_after = (
                    TareaRecursoReal.objects
                    .filter(team=team, legacy_tipo_recurso__in=list(CONTRACT_TYPES), empleado__isnull=True)
                    |
                    TareaRecursoReal.objects
                    .filter(team=team, legacy_tipo_recurso__in=list(CONTRACT_TYPES), empleado__legacy_id=0)
                ).distinct()

                for r in qs_after:
                    emp = empleados.get(r.legacy_id_recurso)
                    rec = recursos.get(r.legacy_id_recurso)
                    if not emp or emp.legacy_id == 0:
                        continue
                    if not rec or rec.tipo not in CONTRACT_TYPES:
                        continue

                    updated = TareaRecursoReal.objects.filter(
                        team=team,
                        id=r.id,
                    ).update(
                        empleado=emp,
                        legacy_personal=emp.legacy_id,
                        updated_at=timezone.now(),
                    )
                    reconciled += updated

            report["created"]["empleados_contratados"] = created_employees
            report["created"]["reales_reconciled"] = reconciled

        if options["json_out"]:
            out = Path(options["json_out"])
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
            self.stdout.write(f"JSON guardado en: {out}")

        self.stdout.write("")
        self.stdout.write("=== RESULTADO ===")
        self.stdout.write(json.dumps(report["created"], indent=2, ensure_ascii=False))
        self.stdout.write("OK")
