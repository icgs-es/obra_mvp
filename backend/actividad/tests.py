from django.contrib.auth import get_user_model
from django.test import TestCase

from usuarios.models import Team

from .models import ActividadPlataforma
from .services import registrar_actividad


class ObjetoPrueba:
    pk = 45

    class _meta:
        label_lower = "pruebas.objeto"

    def __init__(self, team):
        self.team = team

    def __str__(self):
        return "Objeto de prueba"


class RegistrarActividadTests(TestCase):
    def setUp(self):
        User = get_user_model()

        self.user = User.objects.create_user(
            username="actividad_test",
            password="test",
        )

        self.team = Team.objects.create(
            name="Empresa de prueba",
        )

        self.team.members.add(self.user)

    def test_registro_explicito(self):
        actividad = registrar_actividad(
            modulo="ARCHIVOS",
            accion="SUBIR",
            actor=self.user,
            team=self.team,
            objeto_repr="video.mp4",
            descripcion="Subió un vídeo.",
            diferir_hasta_commit=False,
        )

        self.assertEqual(
            ActividadPlataforma.objects.count(),
            1,
        )
        self.assertEqual(actividad.actor, self.user)
        self.assertEqual(actividad.team, self.team)
        self.assertEqual(actividad.modulo, "ARCHIVOS")
        self.assertEqual(actividad.accion, "SUBIR")

    def test_infiere_datos_del_objeto(self):
        objeto = ObjetoPrueba(self.team)

        actividad = registrar_actividad(
            modulo="PRUEBAS",
            accion="CREAR",
            actor=self.user,
            objeto=objeto,
            diferir_hasta_commit=False,
        )

        self.assertEqual(actividad.team, self.team)
        self.assertEqual(
            actividad.tipo_objeto,
            "pruebas.objeto",
        )
        self.assertEqual(actividad.objeto_id, 45)
        self.assertEqual(
            actividad.objeto_repr,
            "Objeto de prueba",
        )

    def test_clave_idempotencia_evitar_duplicados(self):
        params = {
            "modulo": "GESTION",
            "accion": "CREAR",
            "actor": self.user,
            "team": self.team,
            "objeto_repr": "Factura 100",
            "clave_idempotencia": "test-factura-100",
            "diferir_hasta_commit": False,
        }

        primera = registrar_actividad(**params)
        segunda = registrar_actividad(**params)

        self.assertEqual(
            ActividadPlataforma.objects.count(),
            1,
        )
        self.assertEqual(primera.pk, segunda.pk)

    def test_rechaza_metadata_no_diccionario(self):
        with self.assertRaises(TypeError):
            registrar_actividad(
                modulo="PRUEBAS",
                accion="CREAR",
                metadata=["valor-no-valido"],
                diferir_hasta_commit=False,
            )
