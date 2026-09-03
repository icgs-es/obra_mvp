from unittest.mock import patch

from django.contrib.auth import (
    get_user_model,
)
from django.contrib.auth.models import (
    Group,
    Permission,
)
from django.test import TestCase
from django.urls import reverse


class CloudManagementCompleteV1Tests(
    TestCase
):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.management_group = (
            Group.objects.create(
                name=(
                    "Archivos Gestión Completa Test"
                )
            )
        )

        cls.reading_group = (
            Group.objects.create(
                name="Archivos Lectura Test"
            )
        )

        management_permissions = (
            Permission.objects.filter(
                content_type__app_label=(
                    "archivos"
                ),
                codename__in={
                    "view_archivo",
                    "view_carpeta",
                    "add_archivo",
                    "add_carpeta",
                    "change_archivo",
                    "change_carpeta",
                    "delete_archivo",
                    "delete_carpeta",
                    "upload_folder",
                },
            )
        )

        reading_permissions = (
            Permission.objects.filter(
                content_type__app_label=(
                    "archivos"
                ),
                codename__in={
                    "view_archivo",
                    "view_carpeta",
                },
            )
        )

        cls.management_group.permissions.set(
            management_permissions
        )

        cls.reading_group.permissions.set(
            reading_permissions
        )

        cls.manager = (
            User.objects.create_user(
                username=(
                    "management_complete"
                ),
                password="test-password",
            )
        )

        cls.manager.groups.add(
            cls.management_group
        )

        cls.reader = (
            User.objects.create_user(
                username="reading_only",
                password="test-password",
            )
        )

        cls.reader.groups.add(
            cls.reading_group
        )

        cls.staff_without_permissions = (
            User.objects.create_user(
                username=(
                    "staff_without_permissions"
                ),
                password="test-password",
                is_staff=True,
            )
        )

    def render_explorer(
        self,
        user,
    ):
        self.client.force_login(
            user
        )

        with patch(
            "archivos.cloud_views."
            "NextcloudCloudGateway"
        ) as gateway_class:
            gateway = (
                gateway_class.return_value
            )

            gateway.normalize_path.side_effect = (
                lambda value, allow_empty=True:
                str(value or "")
                .strip()
                .strip("/")
            )

            gateway.list_directory.return_value = [
                {
                    "name": "CARPETA PILOTO",
                    "is_folder": True,
                    "size": 0,
                    "modified": "",
                    "storage_key": (
                        "CONSTRUCTORA/"
                        "CARPETA PILOTO"
                    ),
                    "mime_type": (
                        "httpd/unix-directory"
                    ),
                    "etag": "",
                    "file_id": 999,
                }
            ]

            gateway.config = {
                "hidden_root_items": [],
            }

            return self.client.get(
                reverse(
                    "archivos:"
                    "explorador_raiz"
                ),
                {
                    "path": "CONSTRUCTORA",
                },
                secure=True,
            )

    def test_manager_sees_all_actions(
        self,
    ):
        response = self.render_explorer(
            self.manager
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        for label in (
            "Renombrar",
            "Mover",
            "Eliminar",
        ):
            self.assertContains(
                response,
                label,
            )

    def test_reader_does_not_see_actions(
        self,
    ):
        response = self.render_explorer(
            self.reader
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        for label in (
            "Renombrar",
            "Mover",
            "Eliminar",
        ):
            self.assertNotContains(
                response,
                label,
            )

    def test_staff_without_permissions_does_not_see_actions(
        self,
    ):
        response = self.render_explorer(
            self.staff_without_permissions
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        for label in (
            "Renombrar",
            "Mover",
            "Eliminar",
        ):
            self.assertNotContains(
                response,
                label,
            )
