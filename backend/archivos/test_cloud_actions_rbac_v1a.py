
import inspect

from django.contrib.auth import (
    get_user_model,
)
from django.contrib.auth.models import (
    Group,
    Permission,
)
from django.test import TestCase

from archivos.cloud_rbac import (
    cloud_path_allowed,
)
from archivos.models import (
    ReglaAccesoRaizCloud,
)

from archivos import cloud_actions


class CloudActionsRbacV1ATests(
    TestCase
):

    def setUp(self):

        User = get_user_model()

        self.group = Group.objects.create(
            name="Arquitectura Actions Test"
        )

        self.rule = (
            ReglaAccesoRaizCloud.objects
            .create(
                nombre_raiz="ARQUITECTURA_TEST",
                activa=True,
            )
        )

        self.rule.grupos.add(
            self.group
        )


        self.user = User.objects.create_user(
            username="actions_user",
            password="x",
        )

        self.user.groups.add(
            self.group
        )


        self.staff = User.objects.create_user(
            username="actions_staff",
            password="x",
            is_staff=True,
        )


        self.superuser = (
            User.objects.create_superuser(
                username="actions_root",
                password="x",
                email="root@test.invalid",
            )
        )


        self.permissions = {}

        for codename in (
            "add_archivo",
            "add_carpeta",
            "change_archivo",
            "change_carpeta",
            "delete_archivo",
            "delete_carpeta",
        ):

            self.permissions[codename] = (
                Permission.objects.get(
                    content_type__app_label="archivos",
                    codename=codename,
                )
            )


        self.user.user_permissions.add(
            *self.permissions.values()
        )


    def test_delete_permission_plus_scope(
        self,
    ):

        path = (
            "ARQUITECTURA_TEST/"
            "OBRA/documento.dwg"
        )

        self.assertTrue(
            cloud_actions._can_manage(
                self.user,
                path,
                permission=(
                    "archivos.delete_archivo"
                ),
            )
        )


    def test_unrelated_root_denied(
        self,
    ):

        self.assertFalse(
            cloud_actions._can_manage(
                self.user,
                (
                    "ADMINISTRACION_TEST/"
                    "documento.pdf"
                ),
                permission=(
                    "archivos.delete_archivo"
                ),
            )
        )


    def test_staff_no_documental_bypass(
        self,
    ):

        self.staff.user_permissions.add(
            self.permissions[
                "delete_archivo"
            ]
        )

        self.assertFalse(
            cloud_actions._can_manage(
                self.staff,
                (
                    "ARQUITECTURA_TEST/"
                    "documento.dwg"
                ),
                permission=(
                    "archivos.delete_archivo"
                ),
            )
        )


    def test_superuser_full_bypass(
        self,
    ):

        self.assertTrue(
            cloud_actions._can_manage(
                self.superuser,
                (
                    "RAIZ_SIN_REGLA/"
                    "documento.dwg"
                ),
                permission=(
                    "archivos.delete_archivo"
                ),
            )
        )


    def test_actions_have_root_gates(
        self,
    ):

        for fn in (
            cloud_actions.cloud_item_rename,
            cloud_actions.cloud_item_move,
            cloud_actions.cloud_item_delete,
        ):

            source = inspect.getsource(
                fn
            )

            self.assertIn(
                "cloud_root_scope_allowed",
                source,
            )


    def test_move_has_destination_gate(
        self,
    ):

        source = inspect.getsource(
            cloud_actions.cloud_item_move
        )

        self.assertIn(
            "destination_permission",
            source,
        )

        self.assertIn(
            "cloud_path_allowed",
            source,
        )


    def test_can_manage_has_no_staff_bypass(
        self,
    ):

        source = inspect.getsource(
            cloud_actions._can_manage
        )

        self.assertNotIn(
            "is_staff",
            source,
        )

        self.assertIn(
            "cloud_path_allowed",
            source,
        )

