from django.contrib.auth import get_user_model
from django.test import TestCase

from usuarios.models import Team

from .cloud_references import (
    CloudReferenceError,
    upsert_cloud_uploaded_reference,
)
from .models import Archivo, Carpeta


class CloudReferenceTests(TestCase):
    def setUp(self):
        User = get_user_model()

        self.actor = User.objects.create_user(
            username="cloud_actor",
        )

        self.team = Team.objects.create(
            name="Empresa cloud",
        )

        self.other_team = Team.objects.create(
            name="Otra empresa cloud",
        )

        self.folder = Carpeta.objects.create(
            nombre="Índice cloud",
            slug="intasa-cloud-system",
            owner=self.actor,
            visibilidad="GLOBAL",
        )

        self.item = {
            "storage_key": (
                "FORMACION/Manual/documento.pdf"
            ),
            "file_id": "remote-test-001",
            "size": 2048,
            "etag": "etag-test-001",
            "content_type": "application/pdf",
        }

    def test_crea_referencia_con_actor_y_empresa(self):
        archivo, created = (
            upsert_cloud_uploaded_reference(
                folder=self.folder,
                item=self.item,
                actor=self.actor,
                team=self.team,
            )
        )

        self.assertTrue(created)
        self.assertEqual(
            archivo.team,
            self.team,
        )
        self.assertEqual(
            archivo.subido_por,
            self.actor,
        )
        self.assertEqual(
            archivo.storage_object_id,
            "remote-test-001",
        )
        self.assertEqual(
            Archivo.objects.count(),
            1,
        )

    def test_actualizacion_idempotente(self):
        first, _created = (
            upsert_cloud_uploaded_reference(
                folder=self.folder,
                item=self.item,
                actor=self.actor,
                team=self.team,
            )
        )

        updated_item = {
            **self.item,
            "etag": "etag-test-002",
            "size": 4096,
        }

        second, created = (
            upsert_cloud_uploaded_reference(
                folder=self.folder,
                item=updated_item,
                actor=self.actor,
                team=self.team,
            )
        )

        self.assertFalse(created)
        self.assertEqual(
            first.pk,
            second.pk,
        )
        self.assertEqual(
            Archivo.objects.count(),
            1,
        )

        second.refresh_from_db()

        self.assertEqual(
            second.tamano_bytes,
            4096,
        )
        self.assertEqual(
            second.storage_version,
            "etag-test-002",
        )

    def test_no_reasigna_a_otra_empresa(self):
        upsert_cloud_uploaded_reference(
            folder=self.folder,
            item=self.item,
            actor=self.actor,
            team=self.team,
        )

        with self.assertRaises(
            CloudReferenceError
        ):
            upsert_cloud_uploaded_reference(
                folder=self.folder,
                item=self.item,
                actor=self.actor,
                team=self.other_team,
            )

        archivo = Archivo.objects.get(
            storage_object_id="remote-test-001",
        )

        self.assertEqual(
            archivo.team,
            self.team,
        )
