from . import test_cloud_references as reference_tests
from .cloud_references import (
    upsert_cloud_uploaded_reference,
)


class CloudReferenceVersionAllocationTests(
    reference_tests.CloudReferenceTests
):
    # No repetimos los tests heredados. Reutilizamos únicamente
    # su setUp estable para crear usuario, empresa y carpeta.
    test_actualizacion_idempotente = None
    test_crea_referencia_con_actor_y_empresa = None
    test_no_reasigna_a_otra_empresa = None

    def _fixture_value(self, *names):
        for name in names:
            value = getattr(
                self,
                name,
                None,
            )

            if value is not None:
                return value

        self.fail(
            "No se encontró fixture para: "
            + ", ".join(names)
        )

    def test_mismo_nombre_en_rutas_distintas(
        self,
    ):
        folder = self._fixture_value(
            "folder",
            "carpeta",
        )

        actor = self._fixture_value(
            "actor",
            "user",
            "usuario",
        )

        team = self._fixture_value(
            "team",
            "empresa",
        )

        filename = (
            "_p2b3_nombre_repetido.pdf"
        )

        first, first_created = (
            upsert_cloud_uploaded_reference(
                folder=folder,
                actor=actor,
                team=team,
                item={
                    "storage_key": (
                        "Ruta-A/"
                        + filename
                    ),
                    "file_id": "p2b3-1001",
                    "size": 101,
                    "etag": "etag-a",
                    "content_type": (
                        "application/pdf"
                    ),
                },
            )
        )

        second, second_created = (
            upsert_cloud_uploaded_reference(
                folder=folder,
                actor=actor,
                team=team,
                item={
                    "storage_key": (
                        "Ruta-B/"
                        + filename
                    ),
                    "file_id": "p2b3-1002",
                    "size": 202,
                    "etag": "etag-b",
                    "content_type": (
                        "application/pdf"
                    ),
                },
            )
        )

        self.assertTrue(
            first_created
        )

        self.assertTrue(
            second_created
        )

        self.assertEqual(
            first.nombre_logico,
            second.nombre_logico,
        )

        self.assertEqual(
            first.version,
            1,
        )

        self.assertEqual(
            second.version,
            2,
        )

        self.assertNotEqual(
            first.storage_object_id,
            second.storage_object_id,
        )

        repeated, repeated_created = (
            upsert_cloud_uploaded_reference(
                folder=folder,
                actor=actor,
                team=team,
                item={
                    "storage_key": (
                        "Ruta-B/"
                        + filename
                    ),
                    "file_id": "p2b3-1002",
                    "size": 303,
                    "etag": "etag-b2",
                    "content_type": (
                        "application/pdf"
                    ),
                },
            )
        )

        self.assertFalse(
            repeated_created
        )

        self.assertEqual(
            repeated.pk,
            second.pk,
        )

        self.assertEqual(
            repeated.version,
            2,
        )

        self.assertEqual(
            repeated.tamano_bytes,
            303,
        )
