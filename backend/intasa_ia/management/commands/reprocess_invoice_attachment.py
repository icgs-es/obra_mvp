from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from intasa_ia.models import AdjuntoIA, MensajeIA, ProcesamientoMensajeIA
from intasa_ia.tasks import process_document_message


class Command(BaseCommand):
    help = "Encola el reprocesamiento explícito de un único PDF de factura INTASA IA."

    def add_arguments(self, parser):
        parser.add_argument("attachment_id")

    def handle(self, *args, **options):
        try:
            attachment = AdjuntoIA.objects.select_related("message").get(
                pk=options["attachment_id"]
            )
        except (AdjuntoIA.DoesNotExist, ValueError) as exc:
            raise CommandError("Adjunto no encontrado") from exc
        if attachment.extension.lower() != ".pdf":
            raise CommandError("Solo se admite un PDF en este comando")
        with transaction.atomic():
            attachment = AdjuntoIA.objects.select_for_update().get(pk=attachment.pk)
            message = attachment.message
            processing, _ = ProcesamientoMensajeIA.objects.get_or_create(message=message)
            previous = processing.assistant_message
            if previous is not None:
                metadata = dict(previous.metadata or {})
                metadata["superseded_by_hotfix"] = "invoice_party_roles_v1"
                previous.metadata = metadata
                previous.save(update_fields=("metadata",))
            processing.assistant_message = None
            processing.status = ProcesamientoMensajeIA.Estado.QUEUED
            processing.error_code = ""
            processing.save(update_fields=("assistant_message", "status", "error_code", "updated_at"))
            transaction.on_commit(
                lambda: process_document_message.delay(processing.pk, str(processing.task_key))
            )
        self.stdout.write(self.style.SUCCESS("Reprocesamiento encolado para un único adjunto."))
