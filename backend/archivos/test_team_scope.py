from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import TestCase

from usuarios.models import Team

from .models import Carpeta
from .team_scope import (
    DocumentTeamResolutionError,
    resolve_document_team,
)


class DocumentTeamScopeTests(TestCase):
    def setUp(self):
        User = get_user_model()

        self.user = User.objects.create_user(
            username="document_user",
        )

        self.superuser = User.objects.create_superuser(
            username="document_admin",
            email="admin@example.com",
            password="test",
        )

        self.team_1 = Team.objects.create(
            name="Empresa documental uno",
        )

        self.team_2 = Team.objects.create(
            name="Empresa documental dos",
        )

        self.user.teams.add(
            self.team_1,
            self.team_2,
        )

    def request(self, user, active_team_id=None):
        return SimpleNamespace(
            user=user,
            session={
                "active_team_id": active_team_id,
            },
        )

    def test_empresa_activa_valida(self):
        team = resolve_document_team(
            self.request(
                self.user,
                self.team_2.id,
            )
        )

        self.assertEqual(
            team,
            self.team_2,
        )

    def test_todas_con_varias_empresas_rechaza(self):
        with self.assertRaises(
            DocumentTeamResolutionError
        ):
            resolve_document_team(
                self.request(
                    self.user,
                    "all",
                )
            )

    def test_unica_empresa_es_resoluble(self):
        self.user.teams.remove(self.team_2)

        team = resolve_document_team(
            self.request(
                self.user,
                "all",
            )
        )

        self.assertEqual(
            team,
            self.team_1,
        )

    def test_carpeta_hereda_empresa(self):
        folder = Carpeta.objects.create(
            nombre="Carpeta con empresa",
            owner=self.user,
            team=self.team_1,
            visibilidad="PRIVADA",
        )

        team = resolve_document_team(
            self.request(
                self.user,
                "all",
            ),
            folder=folder,
        )

        self.assertEqual(
            team,
            self.team_1,
        )

    def test_carpeta_de_empresa_no_permitida(self):
        external = get_user_model().objects.create_user(
            username="external_document_user",
        )

        folder = Carpeta.objects.create(
            nombre="Carpeta ajena",
            owner=self.user,
            team=self.team_1,
            visibilidad="PRIVADA",
        )

        with self.assertRaises(
            DocumentTeamResolutionError
        ):
            resolve_document_team(
                self.request(
                    external,
                    "all",
                ),
                folder=folder,
            )

    def test_superusuario_puede_usar_team_activo(self):
        team = resolve_document_team(
            self.request(
                self.superuser,
                self.team_2.id,
            )
        )

        self.assertEqual(
            team,
            self.team_2,
        )

    def test_staff_without_functional_permission_cannot_read_private_folder(self):
        staff = get_user_model().objects.create_user(
            username="document_staff_without_functional_permission",
            is_staff=True,
        )
        staff.teams.add(self.team_1)
        folder = Carpeta.objects.create(
            nombre="Privada de otro usuario",
            owner=self.user,
            team=self.team_1,
            visibilidad="PRIVADA",
        )

        self.assertFalse(folder.puede_ver(staff))
        self.assertFalse(folder.puede_escribir(staff))
