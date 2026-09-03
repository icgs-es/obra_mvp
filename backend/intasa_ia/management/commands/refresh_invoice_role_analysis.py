from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from intasa_ia.invoice_response_guard import enforce_invoice_role_safety
from intasa_ia.invoice_role_analysis import analyze_invoice_text
from intasa_ia.models import AdjuntoIA, ProcesamientoMensajeIA


class Command(BaseCommand):
    help = "Recalcula roles de factura y corrige la respuesta asociada sin llamar al proveedor."

    def add_arguments(self, parser):
        parser.add_argument("attachment_id")

    def handle(self, *args, **options):
        try:
            with transaction.atomic():
                attachment = AdjuntoIA.objects.select_for_update().get(pk=options["attachment_id"])
                if attachment.extension.lower() != ".pdf" or not attachment.extracted_text:
                    raise CommandError("El adjunto no tiene texto PDF procesado")
                analysis = analyze_invoice_text(attachment.extracted_text)
                attachment.invoice_analysis = analysis
                attachment.save(update_fields=("invoice_analysis",))
                processing = ProcesamientoMensajeIA.objects.filter(message=attachment.message).select_related("assistant_message").first()
                if processing and processing.assistant_message_id:
                    assistant = processing.assistant_message
                    assistant.contenido = enforce_invoice_role_safety(assistant.contenido, [analysis])
                    metadata = dict(assistant.metadata or {})
                    metadata["invoice_role_hotfix"] = "v1"
                    assistant.metadata = metadata
                    assistant.save(update_fields=("contenido", "metadata"))
        except AdjuntoIA.DoesNotExist as exc:
            raise CommandError("Adjunto no encontrado") from exc
        self.stdout.write(self.style.SUCCESS("Análisis de roles actualizado sin llamada al proveedor."))
