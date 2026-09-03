import logging

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import AdjuntoIA, PurgaAdjuntoIAPendiente
from .private_storage import private_ia_storage


logger = logging.getLogger(__name__)


def create_attachments(*, conversation, message, owner, validated_attachments):
    created = []
    attempted = []
    try:
        for upload, metadata in validated_attachments:
            attachment = AdjuntoIA(
                conversation=conversation,
                message=message,
                owner=owner,
                file=upload,
                status=AdjuntoIA.Estado.UPLOADED,
                **metadata,
            )
            attempted.append(attachment)
            attachment.full_clean(exclude=("file",))
            attachment.save()
            created.append(attachment)
        return created
    except Exception:
        for attachment in attempted:
            storage_name = str(getattr(attachment.file, "name", "") or "")
            if not storage_name:
                continue
            try:
                private_ia_storage.delete(storage_name)
            except Exception:
                logger.error("INTASA IA partial attachment cleanup failed")
        raise


def schedule_physical_delete(attachment_refs, failure_bucket=None):
    refs = tuple(attachment_refs)

    def delete_after_commit():
        for attachment_id, storage_name in refs:
            try:
                private_ia_storage.delete(storage_name)
            except Exception:
                if failure_bucket is not None:
                    failure_bucket.append(str(attachment_id))
                try:
                    PurgaAdjuntoIAPendiente.objects.update_or_create(
                        attachment_id=attachment_id,
                        defaults={"storage_name": storage_name},
                    )
                except Exception:
                    logger.error("INTASA IA purge registration failed")
                logger.error("INTASA IA physical attachment delete failed")

    transaction.on_commit(delete_after_commit)
