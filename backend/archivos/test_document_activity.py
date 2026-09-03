from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import TransactionTestCase

from actividad.models import ActividadPlataforma
from usuarios.models import Team

from .activity import (
    registrar_subida_documental,
    ruta_carpeta_local,
)
from .models import Archivo, Carpeta


class DocumentActivityTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        User = get_user_model()

        self.actor = User.objects.create_user(
            username="activity_actor",
        )

        self.team = Team.objects.create(
            name="Activity document team",
        )

        self.actor.teams.add(self.team)

        self.root = Carpeta.objects.create(
            nombre="FORMACION",
            owner=self.actor,
            team=self.team,
            visibilidad="GLOBAL",
        )

        self.folder = Carpeta.objects.create(
            nombre="Gestion",
            parent=self.root,
            owner=self.actor,
            team=self.team,
            visibilidad="GLOBAL",
        )

    def create_file(self, name):
        return Archivo.objects.create(
            carpeta=self.folder,
            team=self.team,
            fichero="",
            nombre_original=name,
            nombre_logico=name,
            storage_provider="nextcloud",
            storage_key=f"FORMACION/Gestion/{name}",
            storage_object_id=f"remote-{name}",
            subido_por=self.actor,
        )

    def test_ruta_local_completa(self):
        self.assertEqual(
            ruta_carpeta_local(self.folder),
            "FORMACION/Gestion",
        )

    def test_un_archivo_crea_una_actividad(self):
        archivo = self.create_file("uno.pdf")

        actividad = registrar_subida_documental(
            actor=self.actor,
            team=self.team,
            archivos=[archivo],
            destino="FORMACION/Gestion",
            url="/app/archivos/?path=FORMACION/Gestion",
            storage_provider="nextcloud",
            diferir_hasta_commit=False,
        )

        self.assertIsNotNone(actividad)
        self.assertEqual(
            ActividadPlataforma.objects.count(),
            1,
        )

        actividad.refresh_from_db()

        self.assertEqual(
            actividad.modulo,
            "archivos",
        )
        self.assertEqual(
            actividad.accion,
            "subida",
        )
        self.assertEqual(
            actividad.actor,
            self.actor,
        )
        self.assertEqual(
            actividad.team,
            self.team,
        )
        self.assertEqual(
            actividad.objeto_id,
            archivo.pk,
        )
        self.assertEqual(
            actividad.metadata["cantidad"],
            1,
        )
        self.assertIn(
            "uno.pdf",
            actividad.descripcion,
        )

    def test_varios_archivos_crean_solo_una_actividad(self):
        primero = self.create_file("uno.pdf")
        segundo = self.create_file("dos.pdf")

        registrar_subida_documental(
            actor=self.actor,
            team=self.team,
            archivos=[primero, segundo],
            destino="FORMACION/Gestion",
            url="/app/archivos/?path=FORMACION/Gestion",
            storage_provider="nextcloud",
            diferir_hasta_commit=False,
        )

        self.assertEqual(
            ActividadPlataforma.objects.count(),
            1,
        )

        actividad = ActividadPlataforma.objects.get()

        self.assertEqual(
            actividad.metadata["cantidad"],
            2,
        )
        self.assertEqual(
            actividad.objeto_repr,
            "2 archivos",
        )
        self.assertEqual(
            actividad.tipo_objeto,
            "archivos.subida_documental",
        )

    def test_misma_operacion_es_idempotente(self):
        archivo = self.create_file("uno.pdf")

        for _iteration in range(2):
            registrar_subida_documental(
                actor=self.actor,
                team=self.team,
                archivos=[archivo],
                destino="FORMACION/Gestion",
                url="/app/archivos/",
                storage_provider="nextcloud",
                diferir_hasta_commit=False,
            )

        self.assertEqual(
            ActividadPlataforma.objects.count(),
            1,
        )

    def test_rollback_descarta_actividad_diferida(self):
        archivo = self.create_file("rollback.pdf")

        try:
            with transaction.atomic():
                registrar_subida_documental(
                    actor=self.actor,
                    team=self.team,
                    archivos=[archivo],
                    destino="FORMACION/Gestion",
                    url="/app/archivos/",
                    storage_provider="nextcloud",
                )

                raise RuntimeError(
                    "rollback intencional"
                )
        except RuntimeError:
            pass

        self.assertEqual(
            ActividadPlataforma.objects.count(),
            0,
        )

    def test_commit_ejecuta_actividad_diferida(self):
        archivo = self.create_file("commit.pdf")

        with transaction.atomic():
            registrar_subida_documental(
                actor=self.actor,
                team=self.team,
                archivos=[archivo],
                destino="FORMACION/Gestion",
                url="/app/archivos/",
                storage_provider="nextcloud",
            )

            self.assertEqual(
                ActividadPlataforma.objects.count(),
                0,
            )

        self.assertEqual(
            ActividadPlataforma.objects.count(),
            1,
        )
