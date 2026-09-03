
import inspect

from pathlib import Path

from django.test import SimpleTestCase

from apps.gestion import views as gestion_views

from obra_movil import (
    views as mobile_views,
)

from obra_movil import (
    forms_almacen_rapido as forms_rapido,
)


class BusquedasArticulosSinLimiteV1Tests(
    SimpleTestCase,
):

    def test_gestion_articulos_sin_300(
        self,
    ):

        source = inspect.getsource(
            gestion_views.articulos_compra_list
        )

        self.assertIn(
            "BUSQUEDAS_ARTICULOS_SIN_LIMITE_V1",
            source,
        )

        self.assertNotIn(
            "qs[:300]",
            source,
        )

        self.assertIn(
            "articulos = list(qs)",
            source,
        )


    def test_mobile_form_archivo_sin_80(
        self,
    ):
        """
        No inspeccionar AlmacenRapidoForm.__init__ en runtime:
        está envuelto por _alm_ux2f2_init_excluir_personal_generico.

        El contrato que queremos validar pertenece al archivo fuente
        forms_almacen_rapido.py.
        """

        source_path = Path(
            forms_rapido.__file__
        )

        source = source_path.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "BUSQUEDAS_ARTICULOS_SIN_LIMITE_V1",
            source,
        )

        self.assertNotIn(
            'order_by("tipo", "nombre", "legacy_id", "id")[:80]',
            source,
        )

        self.assertNotIn(
            ")[:80]",
            source[
                source.find(
                    "elif q_recurso:"
                ):
                source.find(
                    "self.recursos_disponibles_count"
                )
            ],
        )


    def test_mobile_api_sin_12(
        self,
    ):

        source = inspect.getsource(
            mobile_views.almacen_rapido_articulos_api
        )

        self.assertIn(
            "BUSQUEDAS_ARTICULOS_SIN_LIMITE_V1",
            source,
        )

        self.assertNotIn(
            "limit = 12",
            source,
        )

        self.assertNotIn(
            "[:limit]",
            source,
        )


    def test_mobile_api_conserva_relevancia(
        self,
    ):

        source = inspect.getsource(
            mobile_views.almacen_rapido_articulos_api
        )

        self.assertIn(
            "_alm_ux1g_relevance_score",
            source,
        )

        self.assertIn(
            "sorted(",
            source,
        )
