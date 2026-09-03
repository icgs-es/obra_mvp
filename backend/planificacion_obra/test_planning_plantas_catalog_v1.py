import inspect

from django.test import SimpleTestCase

from planificacion_obra import views


class PlanningPlantasCatalogV1Tests(
    SimpleTestCase,
):

    def test_catalogo_sin_tareas_aparece(
        self,
    ):
        result = (
            views._planning_merge_planta_names_v1(
                ["ASCENSOR"],
                [],
            )
        )

        self.assertEqual(
            result,
            ["ASCENSOR"],
        )


    def test_legacy_se_conserva(
        self,
    ):
        result = (
            views._planning_merge_planta_names_v1(
                ["ASCENSOR"],
                ["PRINCIPAL"],
            )
        )

        self.assertEqual(
            result,
            [
                "ASCENSOR",
                "PRINCIPAL",
            ],
        )


    def test_no_duplica_catalogo_y_legacy(
        self,
    ):
        result = (
            views._planning_merge_planta_names_v1(
                [
                    "PRINCIPAL",
                    "ASCENSOR",
                ],
                [
                    "ascensor",
                    "PRINCIPAL",
                ],
            )
        )

        self.assertEqual(
            result,
            [
                "PRINCIPAL",
                "ASCENSOR",
            ],
        )


    def test_planning_usa_unidadobra_planta(
        self,
    ):
        source = inspect.getsource(
            views.planning_list
        )

        self.assertIn(
            "UnidadObraPlanta",
            source,
        )

        self.assertIn(
            "catalog_plantas",
            source,
        )

        self.assertIn(
            "_planning_merge_planta_names_v1",
            source,
        )


    def test_viviendas_sin_tareas_se_conserva(
        self,
    ):
        source = inspect.getsource(
            views.planning_list
        )

        self.assertIn(
            "PLANNING_VIVIENDAS_SIN_TAREAS_V1_2",
            source,
        )
