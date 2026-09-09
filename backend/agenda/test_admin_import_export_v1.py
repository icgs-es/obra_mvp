from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class AgendaAdminImportExportV1Tests(TestCase):
    def setUp(self):
        User = get_user_model()

        self.normal = User.objects.create_user(
            username="agenda_io_normal",
            password="test-pass-123",
        )

        self.admin = User.objects.create_superuser(
            username="agenda_io_admin",
            email="agenda-admin@example.com",
            password="test-pass-123",
        )

    def test_regular_user_cannot_import(self):
        self.client.force_login(self.normal)
        response = self.client.get(
            reverse("agenda:import"),
            secure=True,
        )
        self.assertEqual(response.status_code, 403)

    def test_regular_user_cannot_export(self):
        self.client.force_login(self.normal)
        response = self.client.get(
            reverse("agenda:export"),
            secure=True,
        )
        self.assertEqual(response.status_code, 403)

    def test_superuser_can_open_import(self):
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("agenda:import"),
            secure=True,
        )
        self.assertEqual(response.status_code, 200)

    def test_superuser_can_export(self):
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("agenda:export"),
            secure=True,
        )
        self.assertEqual(response.status_code, 200)
