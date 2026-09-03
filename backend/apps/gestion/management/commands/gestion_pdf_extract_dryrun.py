from django.core.management.base import BaseCommand, CommandError
from django.apps import apps

from apps.gestion.services.pdf_extractor import extract_from_documento_adjunto, dumps_result


class Command(BaseCommand):
    help = "Dry-run OCR/text extraction for DocumentoCompraAdjunto. No escribe en BD."

    def add_arguments(self, parser):
        parser.add_argument("--doc-id", type=int, help="ID de DocumentoCompraAdjunto")
        parser.add_argument(
            "--tipo",
            choices=["FACTURA_PDF", "ALBARAN_PDF"],
            help="Usar último documento de este tipo si no se indica --doc-id",
        )
        parser.add_argument("--max-pages", type=int, default=3)

    def handle(self, *args, **options):
        Documento = apps.get_model("gestion", "DocumentoCompraAdjunto")

        doc_id = options.get("doc_id")
        tipo = options.get("tipo")
        max_pages = options.get("max_pages") or 3

        if doc_id:
            try:
                documento = Documento.objects.get(id=doc_id)
            except Documento.DoesNotExist:
                raise CommandError(f"No existe DocumentoCompraAdjunto id={doc_id}")
        else:
            qs = Documento.objects.exclude(archivo="")
            if tipo:
                qs = qs.filter(tipo_documento=tipo)
            documento = qs.order_by("-id").first()
            if not documento:
                raise CommandError("No se encontró ningún DocumentoCompraAdjunto con archivo")

        result = extract_from_documento_adjunto(documento, max_pages=max_pages)
        self.stdout.write(dumps_result(result))
