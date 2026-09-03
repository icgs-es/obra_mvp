import hashlib
import json

import requests
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from activos.models import ActivoCore
from usuarios.models import Team


class Command(BaseCommand):
    help = "Sincroniza activos desde SeaTable hacia ActivoCore (v1 manual, solo importación)."

    def add_arguments(self, parser):
        parser.add_argument("--team-id", type=int, required=True)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--base-url", type=str, required=True)
        parser.add_argument("--api-token", type=str, required=True)
        parser.add_argument("--table-name", type=str, default="Activos")
        parser.add_argument("--limit", type=int, default=0)

    def handle(self, *args, **options):
        team_id = options["team_id"]
        dry_run = options["dry_run"]
        base_url = options["base_url"].rstrip("/")
        api_token = options["api_token"]
        table_name = options["table_name"]
        limit = options["limit"]

        try:
            team = Team.objects.get(pk=team_id)
        except Team.DoesNotExist:
            raise CommandError(f"No existe Team con id={team_id}")

        self.stdout.write(self.style.SUCCESS(f"Team destino: {team.id} - {team}"))

        # 1) Obtener access token de la base
        token_url = f"{base_url}/api/v2.1/dtable/app-access-token/"
        token_headers = {
            "Authorization": f"Token {api_token}",
            "Accept": "application/json",
        }

        token_response = requests.get(token_url, headers=token_headers, timeout=30)

        if token_response.status_code != 200:
            raise CommandError(
                f"Error obteniendo base token [{token_response.status_code}]: {token_response.text[:500]}"
            )

        token_data = token_response.json()
        access_token = token_data.get("access_token")
        dtable_uuid = token_data.get("dtable_uuid")

        if not access_token or not dtable_uuid:
            raise CommandError("Respuesta inválida de SeaTable: faltan access_token o dtable_uuid")

        # 2) Leer metadata para localizar la tabla y sus columnas
        metadata_url = f"{base_url}/api-gateway/api/v2/dtables/{dtable_uuid}/metadata/"
        metadata_headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

        metadata_response = requests.get(metadata_url, headers=metadata_headers, timeout=30)

        if metadata_response.status_code != 200:
            raise CommandError(
                f"Error leyendo metadata [{metadata_response.status_code}]: {metadata_response.text[:500]}"
            )

        metadata = metadata_response.json()
        tables = metadata.get("metadata", {}).get("tables", [])

        selected_table = None
        for table in tables:
            if table.get("name") == table_name:
                selected_table = table
                break

        if not selected_table:
            raise CommandError(f"No se encontró la tabla '{table_name}' en metadata")

        column_map = {}
        for col in selected_table.get("columns", []):
            column_map[col.get("key")] = col.get("name")

        # 3) Leer filas de la tabla
        rows_url = f"{base_url}/api-gateway/api/v2/dtables/{dtable_uuid}/rows/"
        rows_headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }
        params = {
            "table_name": table_name,
        }

        response = requests.get(rows_url, headers=rows_headers, params=params, timeout=30)

        if response.status_code != 200:
            raise CommandError(
                f"Error leyendo filas [{response.status_code}]: {response.text[:500]}"
            )

        data = response.json()

        if isinstance(data, dict) and "rows" in data:
            rows = data["rows"]
        elif isinstance(data, list):
            rows = data
        else:
            raise CommandError("Respuesta inesperada al leer filas de SeaTable")

        if limit and limit > 0:
            rows = rows[:limit]

        created = 0
        updated = 0
        skipped = 0

        for row in rows:
            seatable_row_id = row.get("_id")
            if not seatable_row_id:
                skipped += 1
                self.stdout.write(self.style.WARNING("Fila omitida: no tiene _id"))
                continue

            translated_row = {}
            for key, value in row.items():
                translated_row[column_map.get(key, key)] = value

            codigo_externo = row.get("0000") or translated_row.get("Coll ID") or seatable_row_id

            payload_for_hash = {
                "codigo_externo": codigo_externo,
            }

            sync_hash = hashlib.sha256(
                json.dumps(payload_for_hash, sort_keys=True, ensure_ascii=False).encode("utf-8")
            ).hexdigest()

            defaults = {
                "team": team,
                "origen_sync": "seatable",
                "last_synced_at": timezone.now(),
                "sync_hash": sync_hash,
                "codigo_externo": codigo_externo,
                "seatable_row_id": seatable_row_id,
            }

            if dry_run:
                exists = ActivoCore.objects.filter(seatable_row_id=seatable_row_id).exists()
                if exists:
                    updated += 1
                else:
                    created += 1
                continue

            _, was_created = ActivoCore.objects.update_or_create(
                seatable_row_id=seatable_row_id,
                defaults=defaults,
            )

            if was_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(self.style.SUCCESS("Proceso finalizado"))
        self.stdout.write(f"Creados: {created}")
        self.stdout.write(f"Actualizados: {updated}")
        self.stdout.write(f"Omitidos: {skipped}")