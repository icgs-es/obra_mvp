from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from actividad.models import (
    ActividadPlataforma,
)

from .activity import (
    registrar_operacion_documental,
)


class DocumentMutationActivityTests(
    SimpleTestCase
):
    def setUp(self):
        self.actor = SimpleNamespace(
            pk=2,
        )

        self.team = SimpleNamespace(
            pk=1,
        )

        self.document = SimpleNamespace(
            pk=100,
        )

    @patch(
        "archivos.activity."
        "registrar_actividad"
    )
    def test_create_folder_team_activity(
        self,
        registrar,
    ):
        registrar_operacion_documental(
            actor=self.actor,
            team=self.team,
            accion="crear_carpeta",
            tipo_elemento="carpeta",
            nombre="Contratos",
            ruta_destino="TECNICOS",
            url="/app/archivos/carpeta/100/",
            objeto=self.document,
            operation_id="create-1",
            diferir_hasta_commit=False,
        )

        kwargs = registrar.call_args.kwargs

        self.assertEqual(
            kwargs["accion"],
            "crear_carpeta",
        )

        self.assertEqual(
            kwargs["visibilidad"],
            (
                ActividadPlataforma
                .Visibilidad
                .EQUIPO
            ),
        )

        self.assertIn(
            "Contratos",
            kwargs["descripcion"],
        )

        self.assertEqual(
            kwargs["clave_idempotencia"],
            (
                "archivos:operacion:"
                "crear_carpeta:create-1"
            ),
        )

    @patch(
        "archivos.activity."
        "registrar_actividad"
    )
    def test_rename_file(
        self,
        registrar,
    ):
        registrar_operacion_documental(
            actor=self.actor,
            team=self.team,
            accion="renombrar",
            tipo_elemento="archivo",
            nombre_anterior="viejo.pdf",
            nombre_nuevo="nuevo.pdf",
            ruta_origen="TECNICOS",
            ruta_destino="TECNICOS",
            objeto=self.document,
            operation_id="rename-1",
        )

        kwargs = registrar.call_args.kwargs

        self.assertIn(
            "viejo.pdf",
            kwargs["descripcion"],
        )

        self.assertIn(
            "nuevo.pdf",
            kwargs["descripcion"],
        )

        self.assertEqual(
            kwargs["metadata"][
                "nombre_anterior"
            ],
            "viejo.pdf",
        )

    @patch(
        "archivos.activity."
        "registrar_actividad"
    )
    def test_move_folder(
        self,
        registrar,
    ):
        registrar_operacion_documental(
            actor=self.actor,
            team=self.team,
            accion="mover",
            tipo_elemento="carpeta",
            nombre="Planos",
            ruta_origen="OBRAS",
            ruta_destino="TECNICOS/Planos",
            objeto=self.document,
            operation_id="move-1",
        )

        kwargs = registrar.call_args.kwargs

        self.assertIn(
            "OBRAS",
            kwargs["descripcion"],
        )

        self.assertIn(
            "TECNICOS/Planos",
            kwargs["descripcion"],
        )

    @patch(
        "archivos.activity."
        "registrar_actividad"
    )
    def test_deleted_object_explicit_reference(
        self,
        registrar,
    ):
        registrar_operacion_documental(
            actor=self.actor,
            team=self.team,
            accion="eliminar",
            tipo_elemento="archivo",
            nombre="borrar.pdf",
            ruta_origen="FORMACION",
            objeto=None,
            tipo_objeto=(
                "archivos.archivo"
            ),
            objeto_id=500,
            operation_id="delete-1",
        )

        kwargs = registrar.call_args.kwargs

        self.assertIsNone(
            kwargs["objeto"]
        )

        self.assertEqual(
            kwargs["tipo_objeto"],
            "archivos.archivo",
        )

        self.assertEqual(
            kwargs["objeto_id"],
            500,
        )

    @patch(
        "archivos.activity."
        "registrar_actividad"
    )
    def test_legacy_without_team_is_private(
        self,
        registrar,
    ):
        registrar_operacion_documental(
            actor=self.actor,
            team=None,
            accion="eliminar",
            tipo_elemento="archivos",
            cantidad=2,
            nombres=[
                "a.pdf",
                "b.pdf",
            ],
            operation_id="legacy-1",
        )

        kwargs = registrar.call_args.kwargs

        self.assertEqual(
            kwargs["visibilidad"],
            (
                ActividadPlataforma
                .Visibilidad
                .ACTOR
            ),
        )

        self.assertIn(
            "2 archivos",
            kwargs["descripcion"],
        )

    def test_invalid_action_rejected(
        self,
    ):
        with self.assertRaises(
            ValueError
        ):
            registrar_operacion_documental(
                actor=self.actor,
                team=self.team,
                accion="descargar",
                tipo_elemento="archivo",
            )



class DocumentMutationGrammarTests(
    SimpleTestCase
):
    def setUp(self):
        self.actor = SimpleNamespace(
            pk=2,
        )

        self.team = SimpleNamespace(
            pk=1,
        )

        self.folder = SimpleNamespace(
            pk=200,
        )

    @patch(
        "archivos.activity."
        "registrar_actividad"
    )
    def test_folder_grammar(
        self,
        registrar,
    ):
        cases = [
            (
                "renombrar",
                {
                    "nombre_anterior": "Anterior",
                    "nombre_nuevo": "Nueva",
                },
                "ha renombrado la carpeta",
            ),
            (
                "mover",
                {
                    "nombre": "Planos",
                    "ruta_origen": "OBRAS",
                    "ruta_destino": "TECNICOS",
                },
                "ha movido la carpeta",
            ),
            (
                "eliminar",
                {
                    "nombre": "Temporal",
                    "ruta_origen": "TECNICOS",
                },
                "ha eliminado la carpeta",
            ),
        ]

        for action, extra, expected in cases:
            registrar.reset_mock()

            registrar_operacion_documental(
                actor=self.actor,
                team=self.team,
                accion=action,
                tipo_elemento="carpeta",
                objeto=self.folder,
                operation_id=(
                    f"grammar-{action}"
                ),
                **extra,
            )

            description = (
                registrar
                .call_args
                .kwargs["descripcion"]
            )

            self.assertIn(
                expected,
                description,
            )

            self.assertNotIn(
                "el carpeta",
                description,
            )
