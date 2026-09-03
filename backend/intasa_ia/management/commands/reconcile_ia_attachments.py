from pathlib import Path

from django.core.management.base import BaseCommand

from intasa_ia.models import AdjuntoIA, PurgaAdjuntoIAPendiente
from intasa_ia.private_storage import private_ia_root, private_ia_storage


class Command(BaseCommand):
    help = "Detecta adjuntos IA inconsistentes; no elimina huérfanos por defecto."

    def add_arguments(self, parser):
        parser.add_argument(
            "--retry-pending",
            action="store_true",
            help="Reintenta únicamente purgas ya registradas y elimina el marcador al confirmar.",
        )

    def handle(self, *args, **options):
        registered = {
            name for name in AdjuntoIA.objects.exclude(file="").values_list("file", flat=True)
        }
        missing = sorted(name for name in registered if not private_ia_storage.exists(name))
        root = Path(private_ia_root())
        physical = set()
        if root.exists():
            physical = {
                path.relative_to(root).as_posix()
                for path in root.rglob("*")
                if path.is_file()
            }
        pending_names = set(
            PurgaAdjuntoIAPendiente.objects.values_list("storage_name", flat=True)
        )
        orphaned = sorted(physical - registered - pending_names)

        retried = 0
        retry_failed = 0
        if options["retry_pending"]:
            for pending in PurgaAdjuntoIAPendiente.objects.all().iterator():
                try:
                    private_ia_storage.delete(pending.storage_name)
                    pending.delete()
                    retried += 1
                except Exception:
                    pending.attempts += 1
                    pending.error_code = "storage_delete_failed"
                    pending.save(update_fields=("attempts", "error_code", "updated_at"))
                    retry_failed += 1

        self.stdout.write(
            f"registered={len(registered)} missing={len(missing)} "
            f"orphaned={len(orphaned)} pending={len(pending_names)} "
            f"retried={retried} retry_failed={retry_failed}"
        )
        for name in missing:
            self.stdout.write(f"MISSING id={Path(name).stem}")
        for name in orphaned:
            self.stdout.write(f"ORPHAN id={Path(name).stem}")
