from django.core.management.base import BaseCommand

from ayuda.services import validate_library


class Command(BaseCommand):
    help = "Valida la biblioteca Markdown de Ayuda INTASA."

    def handle(self, *args, **options):
        articles = validate_library()

        self.stdout.write(
            f"AYUDA_DOCUMENTS={len(articles)}"
        )

        for article in articles:
            self.stdout.write(
                "AYUDA_ARTICLE "
                f"id={article.article_id} "
                f"module={article.module!r} "
                f"submodule={article.submodule!r}"
            )

        self.stdout.write(
            self.style.SUCCESS(
                "AYUDA_LIBRARY_VALID=YES"
            )
        )
