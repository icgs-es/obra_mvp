from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase
from django.urls import reverse


class CloudFolderUploadExecuteUITests(
    SimpleTestCase
):
    def setUp(self):
        root = Path(
            settings.BASE_DIR
        )

        self.cloud_template = (
            root
            / "archivos"
            / "templates"
            / "archivos"
            / "cloud_explorer.html"
        )

        self.partial = (
            root
            / "archivos"
            / "templates"
            / "archivos"
            / "_cloud_folder_upload_preview.html"
        )

        self.preview_js = (
            root
            / "archivos"
            / "static"
            / "archivos"
            / "cloud_folder_upload_preview.js"
        )

        self.execute_js = (
            root
            / "archivos"
            / "static"
            / "archivos"
            / "cloud_folder_upload_execute.js"
        )

        self.css = (
            root
            / "archivos"
            / "static"
            / "archivos"
            / "cloud_folder_upload_preview.css"
        )

    def test_ruta_execute_existe(self):
        self.assertEqual(
            reverse(
                "archivos:"
                "cloud_folder_upload_execute"
            ),
            (
                "/app/archivos/cloud/"
                "folder-upload/execute/"
            ),
        )

    def test_panel_incluye_execute_y_progreso(self):
        source = self.partial.read_text(
            encoding="utf-8"
        )

        for marker in (
            "data-execute-url",
            "folderUploadProgressSection",
            "folderUploadProgressBar",
            "folderUploadRetryButton",
            "folderUploadRefreshButton",
            "folderUploadActivityWarning",
        ):
            self.assertIn(
                marker,
                source,
            )

    def test_preview_expone_estado_seguro(self):
        source = self.preview_js.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "P2B_EXECUTION_BRIDGE",
            source,
        )

        self.assertIn(
            "IntasaFolderUploadPreview",
            source,
        )

        self.assertIn(
            (
                "executeButton.disabled = "
                "!Boolean("
            ),
            source,
        )

    def test_execute_usa_contrato_multilote(self):
        source = self.execute_js.read_text(
            encoding="utf-8"
        )

        for marker in (
            "new XMLHttpRequest()",
            "new FormData()",
            '"token"',
            '"manifest"',
            '"directories"',
            '"files"',
            '"relpath"',
            '"finalize"',
            '"activity_file_ids"',
            '"created_folders_total"',
            "indexed_file_ids",
            "reference_errors",
        ):
            self.assertIn(
                marker,
                source,
            )

    def test_execute_tiene_limites_y_reintento(self):
        source = self.execute_js.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "clientBatchFileLimit = 8",
            source,
        )

        self.assertIn(
            "16 * 1024 * 1024",
            source,
        )

        self.assertIn(
            "retryOperation",
            source,
        )

        self.assertIn(
            "finalizeOperation",
            source,
        )

        self.assertIn(
            "beforeunload",
            source,
        )

        cloud_source = (
            self.cloud_template.read_text(
                encoding="utf-8"
            )
        )

        self.assertIn(
            (
                "cloud_folder_upload_"
                "execute.js"
            ),
            cloud_source,
        )

        self.assertIn(
            "P2B_FOLDER_UPLOAD_PROGRESS",
            self.css.read_text(
                encoding="utf-8"
            ),
        )
