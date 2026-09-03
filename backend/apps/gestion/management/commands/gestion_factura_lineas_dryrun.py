import json

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError

from apps.gestion.services.pdf_extractor import extract_pdf_text
from apps.gestion.services.facturas_pdf import extract_factura_lines_from_text
from apps.gestion.services.factura_router import extract_factura_lines_template_routed_v1


class Command(BaseCommand):
    help = "Dry-run de extracción de líneas OCR para factura. No escribe en BD."

    def add_arguments(self, parser):
        parser.add_argument("--factura-id", type=int)
        parser.add_argument("--max-pages", type=int, default=3)
        parser.add_argument("--show-text", action="store_true")

    def handle(self, *args, **options):
        Factura = apps.get_model("gestion", "FacturaProveedorGestion")

        factura_id = options.get("factura_id")
        max_pages = options.get("max_pages") or 3

        if factura_id:
            factura = Factura.objects.filter(id=factura_id).select_related("team", "proveedor").first()
        else:
            factura = (
                Factura.objects
                .filter(raw_data__created_from="gestion_factura_desde_pdf")
                .select_related("team", "proveedor")
                .order_by("-id")
                .first()
            )

        if not factura:
            raise CommandError("No se encontró factura para analizar.")

        adjunto = factura.adjuntos.order_by("-id").first()
        if not adjunto:
            raise CommandError("La factura no tiene adjunto PDF.")

        if adjunto.ocr_texto:
            text = adjunto.ocr_texto
            source = "adjunto.ocr_texto"
        else:
            extracted = extract_pdf_text(adjunto.archivo.path, max_pages=max_pages)
            text = extracted.get("text") or ""
            source = "extract_pdf_text"

        raw_data = factura.raw_data if isinstance(factura.raw_data, dict) else {}
        plantilla_data = raw_data.get("ocr_plantilla") if isinstance(raw_data.get("ocr_plantilla"), dict) else {}
        extraction_data = raw_data.get("ocr_extraction") if isinstance(raw_data.get("ocr_extraction"), dict) else {}
        parser_key = (plantilla_data.get("parser_key") or extraction_data.get("parser_key") or "").strip()

        # Dry-run mirrors the screen for old/manual invoices: only the exact
        # provider and team are eligible, so this command cannot cross tenants.
        if not parser_key and factura.proveedor_id:
            Plantilla = apps.get_model("gestion", "PlantillaOCRProveedor")
            plantilla = (
                Plantilla.objects.filter(
                    team=factura.team,
                    proveedor=factura.proveedor,
                    tipo_documento="FACTURA",
                    activa=True,
                )
                .order_by("prioridad", "id")
                .first()
            )
            parser_key = (plantilla.parser_key or "").strip() if plantilla else ""

        parsed = None
        if parser_key:
            parsed = extract_factura_lines_template_routed_v1(
                text,
                parser_key=parser_key,
                factura=factura,
                pdf_path=adjunto.archivo.path,
                max_pages=max_pages,
            )
        lineas = parsed if isinstance(parsed, dict) else extract_factura_lines_from_text(text)

        result = {
            "modo": "DRY_RUN_SIN_GUARDAR_LINEAS_FACTURA",
            "factura": {
                "id": factura.id,
                "team": str(factura.team),
                "cod_factura": factura.cod_factura,
                "num_factura_proveedor": factura.num_factura_proveedor,
                "fecha_emision": str(factura.fecha_emision),
                "proveedor": str(factura.proveedor) if factura.proveedor_id else None,
                "base": str(factura.importe_base_imponible),
                "iva": str(factura.importe_iva),
                "total": str(factura.importe_factura),
            },
            "adjunto": {
                "id": adjunto.id,
                "archivo": adjunto.archivo.name,
                "ocr_estado": adjunto.ocr_estado,
                "texto_origen": source,
                "ocr_text_len": len(text),
            },
            "parser_key": parser_key or "generic_fallback",
            "lineas_detectadas": lineas,
        }

        if options.get("show_text"):
            result["ocr_text_preview"] = text[:5000]

        self.stdout.write(json.dumps(result, indent=2, ensure_ascii=False, default=str))
