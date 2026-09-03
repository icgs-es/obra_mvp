from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from .cloud_views import (
    CLOUD_CREATE_FOLDER_PERMISSION,
    CLOUD_UPLOAD_FILE_PERMISSION,
    _can_manage_cloud,
)


class PermissionUser:
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

    def has_perm(
        self,
        permission,
    ):
        return (
            permission
            in self.permissions
        )


class CloudManagementPermissionTests(
    SimpleTestCase
):
    def test_normal_con_add_carpeta_puede_crear(
        self,
    ):
        user = PermissionUser(
            permissions={
                CLOUD_CREATE_FOLDER_PERMISSION,
            }
        )

        self.assertTrue(
            _can_manage_cloud(
                user,
                CLOUD_CREATE_FOLDER_PERMISSION,
            )
        )

        self.assertFalse(
            _can_manage_cloud(
                user,
                CLOUD_UPLOAD_FILE_PERMISSION,
            )
        )

    def test_normal_con_add_archivo_puede_subir(
        self,
    ):
        user = PermissionUser(
            permissions={
                CLOUD_UPLOAD_FILE_PERMISSION,
            }
        )

        self.assertTrue(
            _can_manage_cloud(
                user,
                CLOUD_UPLOAD_FILE_PERMISSION,
            )
        )

        self.assertFalse(
            _can_manage_cloud(
                user,
                CLOUD_CREATE_FOLDER_PERMISSION,
            )
        )

    def test_usuario_sin_permisos_no_gestiona(
        self,
    ):
        user = PermissionUser()

        self.assertFalse(
            _can_manage_cloud(user)
        )

    def test_staff_without_permission_has_no_bypass_and_superuser_keeps_it(
        self,
    ):
        self.assertFalse(
            _can_manage_cloud(
                PermissionUser(
                    staff=True
                ),
                CLOUD_UPLOAD_FILE_PERMISSION,
            )
        )

        self.assertTrue(
            _can_manage_cloud(
                PermissionUser(
                    superuser=True
                ),
                CLOUD_CREATE_FOLDER_PERMISSION,
            )
        )

    def test_template_declara_rbac_individual(
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

        for value in (
            "CLOUD_MANAGEMENT_TOOLBAR_RBAC_V1",
            "CLOUD_CREATE_FOLDER_RBAC_V1",
            "CLOUD_UPLOAD_FILES_RBAC_V1",
            "perms.archivos.add_carpeta",
            "perms.archivos.add_archivo",
            "perms.archivos.upload_folder",
        ):
            self.assertIn(
                value,
                source,
            )
