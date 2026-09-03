from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from django.conf import settings
from django.test import SimpleTestCase

from apps.gestion.albaran_delete_rules import (
    ALBARAN_DELETE_PERMISSION,
    can_user_delete_albaran,
    static_line_blockers,
)


class _User:
    def __init__(
        self,
        *,
        authenticated=True,
        superuser=False,
        permissions=None,
    ):
        self.is_authenticated = (
            authenticated
        )

        self.is_superuser = (
            superuser
        )

        self.permissions = set(
            permissions or []
        )

    def has_perm(
        self,
        permission,
    ):
        return (
            permission
            in self.permissions
        )


def _line(
    **overrides,
):
    values = {
        "facturado": False,
        "factura_legacy": "",
        "en_almacen": False,
        "id_almacen_legacy": None,
        "en_partida": False,
        "cantidad_en_partidas": (
            Decimal("0")
        ),
        "raw_data": {},
    }

    values.update(
        overrides
    )

    return SimpleNamespace(
        **values
    )


class AlbaranDeleteV2Tests(
    SimpleTestCase
):
    def test_permiso_es_administrable(
        self,
    ):
        user = _User(
            permissions={
                ALBARAN_DELETE_PERMISSION,
            },
        )

        self.assertTrue(
            can_user_delete_albaran(
                user
            )
        )

    def test_superusuario_tiene_bypass_de_permiso(
        self,
    ):
        self.assertTrue(
            can_user_delete_albaran(
                _User(
                    superuser=True,
                )
            )
        )

    def test_usuario_sin_permiso_no_puede(
        self,
    ):
        self.assertFalse(
            can_user_delete_albaran(
                _User()
            )
        )

    def test_linea_limpia_no_bloquea(
        self,
    ):
        self.assertEqual(
            static_line_blockers(
                _line()
            ),
            [],
        )

    def test_linea_facturada_bloquea(
        self,
    ):
        codes = {
            blocker["code"]
            for blocker
            in static_line_blockers(
                _line(
                    facturado=True,
                )
            )
        }

        self.assertIn(
            "FACTURADA",
            codes,
        )

    def test_linea_almacen_bloquea(
        self,
    ):
        codes = {
            blocker["code"]
            for blocker
            in static_line_blockers(
                _line(
                    en_almacen=True,
                )
            )
        }

        self.assertIn(
            "EN_ALMACEN",
            codes,
        )

    def test_linea_partida_bloquea(
        self,
    ):
        codes = {
            blocker["code"]
            for blocker
            in static_line_blockers(
                _line(
                    en_partida=True,
                    cantidad_en_partidas=(
                        Decimal("2")
                    ),
                )
            )
        }

        self.assertIn(
            "EN_PARTIDA",
            codes,
        )

        self.assertIn(
            "CANTIDAD_PARTIDA",
            codes,
        )

    def test_trazabilidad_raw_almacen_bloquea(
        self,
    ):
        codes = {
            blocker["code"]
            for blocker
            in static_line_blockers(
                _line(
                    raw_data={
                        "movimiento_almacen_id": 10,
                    },
                )
            )
        }

        self.assertIn(
            "RAW_ALMACEN",
            codes,
        )

    def test_vista_no_retrocede_contador(
        self,
    ):
        path = (
            Path(settings.BASE_DIR)
            / "apps"
            / "gestion"
            / "views.py"
        )

        source = path.read_text(
            encoding="utf-8"
        )

        start = source.index(
            "def albaran_delete("
        )

        end = source.index(
            "\ndef ",
            start + 10,
        )

        function_source = source[
            start:end
        ]

        self.assertIn(
            (
                "ALBARAN_DELETE_"
                "ANY_CLEAN_V2"
            ),
            function_source,
        )

        self.assertNotIn(
            (
                "_gestion_recalcular_"
                "ult_codigo_albaran_empresa"
            ),
            function_source,
        )

    def test_lineas_no_tienen_bypass_operativo(
        self,
    ):
        path = (
            Path(settings.BASE_DIR)
            / "apps"
            / "gestion"
            / "views.py"
        )

        source = path.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            (
                "ALBARAN_LINE_DELETE_"
                "OPERATIONAL_GUARD_V2"
            ),
            source,
        )

    def test_listado_muestra_boton_por_permiso(
        self,
    ):
        path = (
            Path(settings.BASE_DIR)
            / "templates"
            / "gestion"
            / "albaranes_list.html"
        )

        source = path.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "ALBARAN_DELETE_PERMISSION_V2",
            source,
        )

        self.assertIn(
            (
                "perms.gestion."
                "delete_"
                "albaranproveedorgestion"
            ),
            source,
        )

        self.assertIn(
            (
                "'gestion:"
                "albaran_delete'"
            ),
            source,
        )

    def test_confirmacion_informa_reglas_v2(
        self,
    ):
        path = (
            Path(settings.BASE_DIR)
            / "templates"
            / "gestion"
            / "albaran_confirm_delete.html"
        )

        source = path.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            (
                "ALBARAN_DELETE_ANY_"
                "CLEAN_V2_INFO"
            ),
            source,
        )

        self.assertIn(
            (
                "cualquier albarán "
                "de la serie"
            ),
            source,
        )

    def test_listado_no_conserva_boton_legacy_sin_permiso(
        self,
    ):
        path = (
            Path(settings.BASE_DIR)
            / "templates"
            / "gestion"
            / "albaranes_list.html"
        )

        source = path.read_text(
            encoding="utf-8"
        )

        legacy = (
            "/app/gestion/albaranes/"
            "{{ a.id }}/eliminar/"
        )

        protected = (
            "{% url "
            "'gestion:albaran_delete' "
            "a.id %}"
        )

        permission_condition = (
            "{% if request.user.is_superuser "
            "or perms.gestion."
            "delete_albaranproveedorgestion %}"
        )

        self.assertNotIn(
            legacy,
            source,
        )

        self.assertEqual(
            source.count(protected),
            1,
        )

        marker_position = source.index(
            "ALBARAN_DELETE_PERMISSION_V2"
        )

        condition_position = source.index(
            permission_condition,
            marker_position,
        )

        button_position = source.index(
            protected,
            condition_position,
        )

        endif_position = source.index(
            "{% endif %}",
            button_position,
        )

        self.assertLess(
            marker_position,
            condition_position,
        )

        self.assertLess(
            condition_position,
            button_position,
        )

        self.assertLess(
            button_position,
            endif_position,
        )

    def test_lock_del_albaran_no_reutiliza_queryset_con_select_related(
        self,
    ):
        path = (
            Path(settings.BASE_DIR)
            / "apps"
            / "gestion"
            / "views.py"
        )

        source = path.read_text(
            encoding="utf-8"
        )

        start = source.index(
            "def albaran_delete("
        )

        end = source.index(
            "\ndef ",
            start + 10,
        )

        function_source = source[
            start:end
        ]

        self.assertIn(
            (
                "ALBARAN_DELETE_LOCK_"
                "BASE_ROW_V2_1"
            ),
            function_source,
        )

        self.assertIn(
            (
                "AlbaranProveedorGestion."
                "objects"
            ),
            function_source,
        )

        self.assertNotIn(
            (
                "albaran_qs\n"
                "                    "
                ".select_for_update()"
            ),
            function_source,
        )

    def test_vista_desvincula_auditoria_antes_de_eliminar(
        self,
    ):
        path = (
            Path(settings.BASE_DIR)
            / "apps"
            / "gestion"
            / "views.py"
        )

        source = path.read_text(
            encoding="utf-8"
        )

        start = source.index(
            "def albaran_delete("
        )

        end = source.index(
            "\ndef ",
            start + 10,
        )

        function_source = source[
            start:end
        ]

        marker_position = (
            function_source.index(
                (
                    "ALBARAN_DELETE_AUDIT_"
                    "DETACH_V2_2"
                )
            )
        )

        detach_position = (
            function_source.index(
                "albaran_id=None",
                marker_position,
            )
        )

        delete_position = (
            function_source.index(
                (
                    "locked_albaran."
                    "delete()"
                ),
                detach_position,
            )
        )

        self.assertLess(
            marker_position,
            detach_position,
        )

        self.assertLess(
            detach_position,
            delete_position,
        )

    def test_vista_no_expone_error_sql_al_usuario(
        self,
    ):
        import ast
        import textwrap

        path = (
            Path(settings.BASE_DIR)
            / "apps"
            / "gestion"
            / "views.py"
        )

        source = path.read_text(
            encoding="utf-8"
        )

        start = source.index(
            "def albaran_delete("
        )

        end = source.index(
            "\ndef ",
            start + 10,
        )

        function_source = source[
            start:end
        ]

        self.assertNotIn(
            'f"albarán: {exc}"',
            function_source,
        )

        function_tree = ast.parse(
            textwrap.dedent(
                function_source
            )
        )

        string_constants = [
            node.value
            for node in ast.walk(
                function_tree
            )
            if (
                isinstance(
                    node,
                    ast.Constant,
                )
                and isinstance(
                    node.value,
                    str,
                )
            )
        ]

        expected_message = (
            "No se pudo eliminar el "
            "albarán. La operación se "
            "ha revertido y no se ha "
            "modificado ningún dato."
        )

        self.assertIn(
            expected_message,
            string_constants,
        )

