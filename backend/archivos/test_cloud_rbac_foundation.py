from django.contrib.auth import (
    get_user_model,
)
from django.contrib.auth.models import (
    Group,
    Permission,
)
from django.test import TestCase

from archivos.cloud_rbac import (
    allowed_cloud_root_names,
    cloud_path_allowed,
    cloud_root_scope_allowed,
    filter_cloud_root_items,
)
from archivos.models import (
    ReglaAccesoRaizCloud,
)


class CloudRbacFoundationTests(
    TestCase
):
    def setUp(self):
        User = get_user_model()

        self.group_constructora = (
            Group.objects.create(
                name="Constructora Test"
            )
        )

        self.group_admin = (
            Group.objects.create(
                name="Administracion Test"
            )
        )

        self.read_folder = (
            Permission.objects.get(
                content_type__app_label=(
                    "archivos"
                ),
                codename="view_carpeta",
            )
        )

        self.read_file = (
            Permission.objects.get(
                content_type__app_label=(
                    "archivos"
                ),
                codename="view_archivo",
            )
        )

        self.add_folder = (
            Permission.objects.get(
                content_type__app_label=(
                    "archivos"
                ),
                codename="add_carpeta",
            )
        )

        self.user_constructora = (
            User.objects.create_user(
                username=(
                    "rbac_constructora"
                ),
                password="test-password",
            )
        )

        self.user_constructora.groups.add(
            self.group_constructora
        )

        self.user_constructora.user_permissions.add(
            self.read_folder,
            self.read_file,
            self.add_folder,
        )

        self.user_admin = (
            User.objects.create_user(
                username="rbac_admin",
                password="test-password",
            )
        )

        self.user_admin.groups.add(
            self.group_admin
        )

        self.user_admin.user_permissions.add(
            self.read_folder,
            self.read_file,
        )

        self.staff_without_scope = (
            User.objects.create_user(
                username=(
                    "rbac_staff_no_scope"
                ),
                password="test-password",
                is_staff=True,
            )
        )

        self.staff_without_scope.user_permissions.add(
            self.read_folder,
            self.read_file,
            self.add_folder,
        )

        self.superuser = (
            User.objects.create_superuser(
                username=(
                    "rbac_superuser"
                ),
                password="test-password",
                email="root@example.test",
            )
        )

        self.rule_constructora = (
            ReglaAccesoRaizCloud.objects.create(
                nombre_raiz=(
                    "CONSTRUCTORA"
                ),
                activa=True,
            )
        )

        self.rule_constructora.grupos.add(
            self.group_constructora
        )

        self.rule_admin = (
            ReglaAccesoRaizCloud.objects.create(
                nombre_raiz=(
                    "ADMINISTRACION"
                ),
                activa=True,
            )
        )

        self.rule_admin.grupos.add(
            self.group_admin
        )

    def test_descendants_inherit_root_scope(
        self,
    ):
        self.assertTrue(
            cloud_path_allowed(
                self.user_constructora,
                (
                    "CONSTRUCTORA/"
                    "PROYECTOS/COMPETA"
                ),
                permission=(
                    "archivos.view_carpeta"
                ),
            )
        )

    def test_unrelated_root_is_denied(
        self,
    ):
        self.assertFalse(
            cloud_path_allowed(
                self.user_constructora,
                "ADMINISTRACION/PERSONAL",
                permission=(
                    "archivos.view_carpeta"
                ),
            )
        )

    def test_permission_and_scope_are_required(
        self,
    ):
        self.user_constructora.user_permissions.remove(
            self.add_folder
        )

        self.user_constructora = (
            get_user_model()
            .objects.get(
                pk=(
                    self.user_constructora.pk
                )
            )
        )

        self.assertFalse(
            cloud_path_allowed(
                self.user_constructora,
                "CONSTRUCTORA",
                permission=(
                    "archivos.add_carpeta"
                ),
            )
        )

    def test_staff_has_no_documental_bypass(
        self,
    ):
        self.assertFalse(
            cloud_root_scope_allowed(
                self.staff_without_scope,
                "CONSTRUCTORA",
            )
        )

        self.assertFalse(
            cloud_path_allowed(
                self.staff_without_scope,
                "CONSTRUCTORA",
                permission=(
                    "archivos.view_carpeta"
                ),
            )
        )

    def test_superuser_has_full_bypass(
        self,
    ):
        self.assertTrue(
            cloud_path_allowed(
                self.superuser,
                "TODO LO DEMAS/PRIVADO",
                permission=(
                    "archivos.delete_archivo"
                ),
            )
        )

    def test_root_filter_only_returns_allowed_roots(
        self,
    ):
        items = [
            {
                "name": "ADMINISTRACION",
            },
            {
                "name": "CONSTRUCTORA",
            },
            {
                "name": "INFORMATICA",
            },
            {
                "name": "TODO LO DEMAS",
            },
        ]

        filtered = (
            filter_cloud_root_items(
                self.user_constructora,
                items,
            )
        )

        self.assertEqual(
            [
                item["name"]
                for item in filtered
            ],
            [
                "CONSTRUCTORA",
            ],
        )

    def test_allowed_roots_come_from_groups(
        self,
    ):
        self.assertEqual(
            allowed_cloud_root_names(
                self.user_admin,
                permission=(
                    "archivos.view_carpeta"
                ),
            ),
            {
                "ADMINISTRACION",
            },
        )
