from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from archivos.team_scope import (
    DocumentTeamResolutionError,
    resolve_document_team,
)
from usuarios.models import Team, UserProfile


class DocumentDefaultTeamTests(TestCase):
    def setUp(self):
        User = get_user_model()

        self.user = User.objects.create_user(
            username="document_default_user",
        )

        self.team_1 = Team.objects.create(
            name="Default team one",
        )

        self.team_2 = Team.objects.create(
            name="Default team two",
        )

        self.user.teams.add(
            self.team_1,
            self.team_2,
        )

    def request(self, active_team_id):
        return SimpleNamespace(
            user=self.user,
            session={
                "active_team_id": active_team_id,
            },
        )

    def test_perfil_se_crea_automaticamente(self):
        self.assertTrue(
            UserProfile.objects.filter(
                user=self.user
            ).exists()
        )

    def test_predeterminada_resuelve_modo_todas(self):
        profile = self.user.profile
        profile.empresa_documental_predeterminada = (
            self.team_2
        )
        profile.save()

        resolved = resolve_document_team(
            self.request("all")
        )

        self.assertEqual(resolved, self.team_2)

    def test_empresa_activa_prevalece(self):
        profile = self.user.profile
        profile.empresa_documental_predeterminada = (
            self.team_2
        )
        profile.save()

        resolved = resolve_document_team(
            self.request(self.team_1.id)
        )

        self.assertEqual(resolved, self.team_1)

    def test_rechaza_predeterminada_no_permitida(self):
        profile = self.user.profile
        profile.empresa_documental_predeterminada = (
            self.team_2
        )
        profile.save()

        self.user.teams.remove(self.team_2)

        with self.assertRaises(
            DocumentTeamResolutionError
        ):
            resolve_document_team(
                self.request("all")
            )

    def test_modelo_rechaza_empresa_ajena(self):
        external_team = Team.objects.create(
            name="External default team",
        )

        profile = self.user.profile
        profile.empresa_documental_predeterminada = (
            external_team
        )

        with self.assertRaises(ValidationError):
            profile.full_clean()
