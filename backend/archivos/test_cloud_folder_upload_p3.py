from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.conf import settings
from django.test import SimpleTestCase

from .activity import (
    registrar_subida_documental,
)
from .cloud_folder_upload_views import (
    FOLDER_UPLOAD_PERMISSION,
    _can_upload_cloud_folder,
)
from .models import Archivo


class _PermissionUser:
    def __init__(
        self,
        *,
        authenticated=True,
        superuser=False,
        staff=False,
        permissions=None,
    ):
        self.is_authenticated = authenticated
        self.is_superuser = superuser
        self.is_staff = staff
        self.permissions = set(
            permissions or []
        )

    def has_perm(self, permission):
        return (
            permission
            in self.permissions
        )


class CloudFolderUploadP3Tests(
    SimpleTestCase
):
    def test_permiso_es_independiente_de_staff(
        self,
    ):
        staff_without_permission = (
            _PermissionUser(
                staff=True,
            )
        )

        normal_with_permission = (
            _PermissionUser(
                staff=False,
                permissions={
                    FOLDER_UPLOAD_PERMISSION,
                },
            )
        )

        superuser = _PermissionUser(
            superuser=True,
        )

        self.assertFalse(
            _can_upload_cloud_folder(
                staff_without_permission
            )
        )

        self.assertTrue(
            _can_upload_cloud_folder(
                normal_with_permission
            )
        )

        self.assertTrue(
            _can_upload_cloud_folder(
                superuser
            )
        )

    def test_modelo_declara_upload_folder(
        self,
    ):
        permissions = dict(
            Archivo._meta.permissions
        )

        self.assertIn(
            "upload_folder",
            permissions,
        )

    def test_actividad_incluye_auditoria_operacion(
        self,
    ):
        actor = SimpleNamespace(
            pk=10,
        )

        team = SimpleNamespace(
            pk=20,
        )

        archivo = SimpleNamespace(
            pk=30,
            nombre_logico="ejemplo.pdf",
            nombre_original="ejemplo.pdf",
        )

        with patch(
            "archivos.activity."
            "registrar_actividad",
            return_value="activity-ok",
        ) as registrar:
            result = (
                registrar_subida_documental(
                    actor=actor,
                    team=team,
                    archivos=[archivo],
                    destino="Destino/Carpeta",
                    url="/app/archivos/",
                    storage_provider=(
                        "nextcloud"
                    ),
                    carpetas_creadas=1,
                    operation_id="operation-p3",
                    policy="skip",
                    audit_metadata={
                        "declared_files": 1,
                        "declared_directories": 1,
                        "declared_total_size": 123,
                        "indexed_references": 1,
                        "unindexed_files": 0,
                        "finalized": True,
                        "result": "complete",
                    },
                    diferir_hasta_commit=False,
                )
            )

        self.assertEqual(
            result,
            "activity-ok",
        )

        metadata = (
            registrar.call_args.kwargs[
                "metadata"
            ]
        )

        self.assertEqual(
            metadata["operation_id"],
            "operation-p3",
        )

        self.assertEqual(
            metadata["collision_policy"],
            "skip",
        )

        self.assertEqual(
            metadata["declared_files"],
            1,
        )

        self.assertEqual(
            metadata["indexed_references"],
            1,
        )

        self.assertEqual(
            metadata["unindexed_files"],
            0,
        )

        self.assertEqual(
            metadata["result"],
            "complete",
        )

    def test_template_usa_permiso_especifico(
        self,
    ):
        path = (
            Path(settings.BASE_DIR)
            / "archivos"
            / "templates"
            / "archivos"
            / "cloud_explorer.html"
        )

        source = path.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "perms.archivos.upload_folder",
            source,
        )

        self.assertIn(
            "_cloud_folder_upload_preview.html",
            source,
        )

    def test_finalize_contiene_auditoria_operacional(
        self,
    ):
        view_path = (
            Path(settings.BASE_DIR)
            / "archivos"
            / "cloud_folder_upload_views.py"
        )

        source = view_path.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "P3_FOLDER_UPLOAD_FINAL_AUDIT",
            source,
        )

        self.assertIn(
            '"declared_files"',
            source,
        )

        self.assertIn(
            '"indexed_references"',
            source,
        )

        self.assertIn(
            '"reference_coverage_complete"',
            source,
        )

        self.assertIn(
            "audit_metadata=(",
            source,
        )

        self.assertIn(
            "operation_id=(",
            source,
        )

    def test_selector_completo_usa_permiso(
        self,
    ):
        template_path = (
            Path(settings.BASE_DIR)
            / "archivos"
            / "templates"
            / "archivos"
            / "cloud_explorer.html"
        )

        source = template_path.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "P3_FOLDER_UPLOAD_TEMPLATE_RBAC",
            source,
        )

        marker_position = source.index(
            "P3_FOLDER_UPLOAD_TEMPLATE_RBAC"
        )

        button_position = source.index(
            'id="folderUploadChooseButton"'
        )

        permission_position = source.rfind(
            "perms.archivos.upload_folder",
            marker_position,
            button_position,
        )

        self.assertGreaterEqual(
            permission_position,
            0,
        )

