import json

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError

from apps.gestion.services.pdf_extractor import (
    extract_pdf_text,
    extract_albaran_lines_from_text,
)


class Command(BaseCommand):
    help = "Dry-run de extracción de líneas OCR para albarán. No escribe en BD."

    def add_arguments(self, parser):
        parser.add_argument("--albaran-id", type=int)
        parser.add_argument("--max-pages", type=int, default=3)

    def handle(self, *args, **options):
        Albaran = apps.get_model("gestion", "AlbaranProveedorGestion")

        albaran_id = options.get("albaran_id")
        max_pages = options.get("max_pages") or 3

        if albaran_id:
            albaran = Albaran.objects.filter(id=albaran_id).select_related("team", "proveedor").first()
        else:
            albaran = (
                Albaran.objects
                .filter(raw_data__created_from="gestion_albaran_desde_pdf")
                .select_related("team", "proveedor")
                .order_by("-id")
                .first()
            )

        if not albaran:
            raise CommandError("No se encontró albarán para analizar.")

        adjunto = albaran.adjuntos.order_by("-id").first()
        if not adjunto:
            raise CommandError("El albarán no tiene adjunto PDF.")

        if adjunto.ocr_texto:
            text = adjunto.ocr_texto
            source = "adjunto.ocr_texto"
        else:
            extracted = extract_pdf_text(adjunto.archivo.path, max_pages=max_pages)
            text = extracted.get("text") or ""
            source = "extract_pdf_text"

        lineas = extract_albaran_lines_from_text(text)

        result = {
            "modo": "DRY_RUN_SIN_GUARDAR_LINEAS",
            "albaran": {
                "id": albaran.id,
                "team": str(albaran.team),
                "cod_albaran": albaran.cod_albaran,
                "num_albaran_proveedor": albaran.num_albaran_proveedor,
                "fecha_albaran": str(albaran.fecha_albaran),
                "proveedor": str(albaran.proveedor) if albaran.proveedor_id else None,
                "importe_albaran": str(albaran.importe_albaran),
            },
            "adjunto": {
                "id": adjunto.id,
                "archivo": adjunto.archivo.name,
                "ocr_estado": adjunto.ocr_estado,
                "texto_origen": source,
                "ocr_text_len": len(text),
            },
            "lineas_detectadas": lineas,
        }

        self.stdout.write(json.dumps(result, indent=2, ensure_ascii=False, default=str))
