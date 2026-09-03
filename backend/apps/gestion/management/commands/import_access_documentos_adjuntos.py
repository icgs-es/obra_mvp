import csv
import json
import mimetypes
from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from django.utils.text import get_valid_filename

from apps.gestion.models import (
    FacturaProveedorGestion,
    AlbaranProveedorGestion,
    DocumentoCompraAdjunto,
)


class Command(BaseCommand):
    help = "Importa adjuntos históricos exportados desde MS Access a DocumentoCompraAdjunto."

    def add_arguments(self, parser):
        parser.add_argument("--root", default="/app/backend/_imports/access/adjuntos_exportados")
        parser.add_argument("--commit", action="store_true")
        parser.add_argument("--kind", choices=["all", "facturas", "albaranes"], default="all")

    def handle(self, *args, **options):
        root = Path(options["root"])
        commit = options["commit"]
        kind = options["kind"]

        report_dir = Path("/app/backend/_reports")
        report_dir.mkdir(parents=True, exist_ok=True)

        user = get_user_model().objects.filter(is_superuser=True).first()

        report = {
            "generated_at": timezone.now().isoformat(),
            "root": str(root),
            "commit": commit,
            "kind": kind,
        }

        if kind in ("all", "facturas"):
            report["facturas"] = self.process_manifest(
                root=root,
                manifest_name="manifest_facturas.csv",
                exported_subdir="facturas",
                model=FacturaProveedorGestion,
                code_field="cod_factura",
                relation_field="factura",
                tipo_documento="FACTURA_PDF",
                commit=commit,
                user=user,
            )

        if kind in ("all", "albaranes"):
            report["albaranes"] = self.process_manifest(
                root=root,
                manifest_name="manifest_albaranes.csv",
                exported_subdir="albaranes",
                model=AlbaranProveedorGestion,
                code_field="cod_albaran",
                relation_field="albaran",
                tipo_documento="ALBARAN_PDF",
                commit=commit,
                user=user,
            )

        mode = "commit" if commit else "dry_run"
        out = report_dir / f"access_docs_import_{mode}_{timezone.now().strftime('%Y%m%d_%H%M%S')}.json"
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

        self.stdout.write("")
        self.stdout.write("=== ACCESS DOCS IMPORT ===")
        self.stdout.write(f"MODE: {'COMMIT' if commit else 'DRY-RUN'}")
        self.stdout.write(f"REPORT: {out}")

        for key in ("facturas", "albaranes"):
            r = report.get(key)
            if not r:
                continue

            self.stdout.write("")
            self.stdout.write(f"=== {key.upper()} ===")
            for field in [
                "manifest_rows",
                "blank_rows",
                "db_missing",
                "file_missing",
                "file_resolved_by_prefix",
                "ambiguous_prefix",
                "already_imported",
                "candidates",
                "created",
                "errors",
            ]:
                self.stdout.write(f"{field.upper()}: {r[field]}")

    def read_manifest(self, path):
        with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as fh:
            return list(csv.DictReader(fh, delimiter=";"))

    def resolve_file(self, files_dir, pk, exported_name):
        exact = files_dir / exported_name
        if exact.exists():
            return exact, "exact", []

        matches = sorted(files_dir.glob(f"{pk}__*"))
        if len(matches) == 1:
            return matches[0], "prefix", [m.name for m in matches]
        if len(matches) > 1:
            return None, "ambiguous", [m.name for m in matches]

        return None, "missing", []

    def process_manifest(
        self,
        root,
        manifest_name,
        exported_subdir,
        model,
        code_field,
        relation_field,
        tipo_documento,
        commit,
        user,
    ):
        manifest_path = root / manifest_name
        files_dir = root / "exported" / exported_subdir

        result = {
            "manifest": manifest_name,
            "manifest_rows": 0,
            "blank_rows": 0,
            "db_missing": 0,
            "file_missing": 0,
            "file_resolved_by_prefix": 0,
            "ambiguous_prefix": 0,
            "already_imported": 0,
            "candidates": 0,
            "created": 0,
            "errors": 0,
            "examples": {
                "db_missing": [],
                "file_missing": [],
                "ambiguous_prefix": [],
                "created_or_candidate": [],
                "errors": [],
            },
        }

        rows = self.read_manifest(manifest_path)
        result["manifest_rows"] = len(rows)

        for row in rows:
            pk = (row.get("pk_value") or "").strip()
            original = (row.get("file_name_original") or "").strip()
            exported = (row.get("file_name_exportado") or "").strip()

            if not pk or not exported:
                result["blank_rows"] += 1
                continue

            obj = model.objects.filter(**{code_field: pk}).first()
            if not obj:
                result["db_missing"] += 1
                if len(result["examples"]["db_missing"]) < 20:
                    result["examples"]["db_missing"].append({"pk": pk, "file": exported})
                continue

            file_path, resolve_mode, matches = self.resolve_file(files_dir, pk, exported)

            if resolve_mode == "prefix":
                result["file_resolved_by_prefix"] += 1

            if resolve_mode == "ambiguous":
                result["ambiguous_prefix"] += 1
                if len(result["examples"]["ambiguous_prefix"]) < 20:
                    result["examples"]["ambiguous_prefix"].append({
                        "pk": pk,
                        "manifest_file": exported,
                        "matches": matches[:20],
                    })
                continue

            if not file_path or not file_path.exists():
                result["file_missing"] += 1
                if len(result["examples"]["file_missing"]) < 20:
                    result["examples"]["file_missing"].append({
                        "pk": pk,
                        "manifest_file": exported,
                        "matches": matches[:20],
                    })
                continue

            existing_filter = {
                relation_field: obj,
                "nombre_original": original,
            }
            if DocumentoCompraAdjunto.objects.filter(**existing_filter).exists():
                result["already_imported"] += 1
                continue

            result["candidates"] += 1

            if len(result["examples"]["created_or_candidate"]) < 20:
                result["examples"]["created_or_candidate"].append({
                    "pk": pk,
                    "original": original,
                    "resolved_file": file_path.name,
                    "resolve_mode": resolve_mode,
                    "size": file_path.stat().st_size,
                })

            if not commit:
                continue

            try:
                with transaction.atomic():
                    content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
                    safe_name = get_valid_filename(file_path.name)

                    kwargs = {
                        "team": obj.team,
                        relation_field: obj,
                        "tipo_documento": tipo_documento,
                        "nombre_original": original or file_path.name,
                        "tamano_bytes": file_path.stat().st_size,
                        "content_type": content_type,
                    }

                    if user:
                        kwargs["subido_por"] = user

                    adjunto = DocumentoCompraAdjunto(**kwargs)

                    with file_path.open("rb") as fh:
                        adjunto.archivo.save(
                            f"legacy_access/{exported_subdir}/{safe_name}",
                            File(fh),
                            save=False,
                        )

                    adjunto.save()
                    result["created"] += 1

            except Exception as exc:
                result["errors"] += 1
                if len(result["examples"]["errors"]) < 20:
                    result["examples"]["errors"].append({
                        "pk": pk,
                        "file": str(file_path),
                        "error": str(exc),
                    })

        return result
