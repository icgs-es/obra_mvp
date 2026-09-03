import datetime as dt
from decimal import Decimal
from unittest.mock import (
    MagicMock,
    patch,
)

from django.test import (
    TestCase,
    override_settings,
)
from django.urls import reverse

from actividad.models import (
    ActividadPlataforma,
)

from . import (
    test_activity_recursos_reales
    as resource_adapter_tests,
)
from .models import (
    EmpleadoObra,
    TareaRecursoReal,
)


@override_settings(SECURE_SSL_REDIRECT=False)
class ResourceRealCreateViewTests(
    TestCase
):
    def setUp(self):
        (
            resource_adapter_tests
            .ResourceRealActivityAdapterTests
            .setUp(self)
        )

        self.client.force_login(
            self.actor
        )

        session = self.client.session
        session[
            "active_team_id"
        ] = str(self.team.pk)
        session.save()

        self.sequence = 900000

        self.employee = next(
            (
                value
                for value
                in vars(self).values()
                if isinstance(
                    value,
                    EmpleadoObra,
                )
            ),
            None,
        )

        if self.employee is None:
            self.employee = (
                EmpleadoObra.objects
                .filter(
                    team=self.team
                )
                .order_by("pk")
                .first()
            )

        if self.employee is None:
            self.employee = (
                EmpleadoObra.objects.create(
                    team=self.team,
                    legacy_id=990001,
                    nombre=(
                        "Empleado prueba "
                        "recurso real"
                    ),
                    tipo=(
                        EmpleadoObra.Tipo
                        .ADMINISTRADA
                    ),
                    situacion=(
                        EmpleadoObra.Situacion
                        .ACTIVO
                    ),
                    precio_hora=Decimal(
                        "10.0000"
                    ),
                )
            )

        self.assertIsInstance(
            self.employee,
            EmpleadoObra,
        )

    def fill_common(
        self,
        obj,
        tarea,
    ):
        self.sequence += 1

        obj.team = tarea.team
        obj.tarea_obra = tarea
        obj.unidad_obra = (
            tarea.unidad_obra
        )
        obj.partida = tarea.partida

        obj.legacy_id_recurso_tarea = (
            self.sequence
        )

        obj.legacy_cod_obra = (
            tarea.legacy_cod_obra
        )

        obj.legacy_cod_fase = (
            tarea.legacy_cod_fase
        )

        obj.legacy_cod_vivienda = (
            tarea.legacy_cod_vivienda
            or ""
        )

        obj.legacy_planta = (
            tarea.legacy_planta
            or ""
        )

        obj.legacy_capitulo = (
            tarea.legacy_capitulo
            or ""
        )

        obj.legacy_partida = (
            tarea.legacy_partida
            or ""
        )

        obj.legacy_tipo_recurso = (
            obj.legacy_tipo_recurso
            or ""
        )

        obj.id_proveedor = (
            obj.id_proveedor
            or ""
        )

        obj.cod_albaran = (
            obj.cod_albaran
            or ""
        )

        obj.cod_factura = (
            obj.cod_factura
            or ""
        )

        raw = obj.raw_data or {}

        raw.update({
            "origen": (
                "portal_manual"
            ),
            "creado_desde": (
                "tarea_recurso_"
                "real_create"
            ),
            "created_by_user_id": (
                self.actor.pk
            ),
        })

        obj.raw_data = raw

    def valid_form(
        self,
        base,
    ):
        form = MagicMock()
        form.is_valid.return_value = True
        form.save.return_value = base

        return form

    def create_url(self):
        return reverse(
            (
                "planificacion_obra:"
                "tarea_recurso_real_create"
            ),
            args=[
                self.tarea.pk,
            ],
        )

    def activities(self):
        return (
            ActividadPlataforma.objects
            .filter(
                modulo=(
                    "planificacion_obra"
                ),
                accion=(
                    "crear_recurso_real_manual"
                ),
            )
        )

    def created_reals(self):
        return (
            TareaRecursoReal.objects
            .filter(
                legacy_id_recurso_tarea__gte=(
                    900001
                ),
            )
            .order_by("pk")
        )

    def test_resource_single_registers_one_activity(
        self,
    ):
        base = TareaRecursoReal(
            empleado=None,
            recurso=None,
            unidad="UD",
            cantidad=Decimal(
                "2.0000"
            ),
            precio_unidad=Decimal(
                "3.0000"
            ),
            costo_recurso_real=(
                Decimal("6.0000")
            ),
            raw_data={},
        )

        form = self.valid_form(
            base
        )

        with patch(
            (
                "planificacion_obra."
                "views._tr_get_tarea_"
                "for_user"
            ),
            return_value=self.tarea,
        ), patch(
            (
                "planificacion_obra.forms."
                "TareaRecursoRealManualForm"
            ),
            return_value=form,
        ), patch(
            (
                "planificacion_obra.views."
                "_tr_fill_common_real"
            ),
            side_effect=self.fill_common,
        ):
            with self.captureOnCommitCallbacks(
                execute=True
            ):
                response = self.client.post(
                    self.create_url(),
                    {
                        "tipo_recurso_ui": (
                            "MATERIAL"
                        ),
                    },
                )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.assertEqual(
            self.created_reals().count(),
            1,
        )

        self.assertEqual(
            self.activities().count(),
            1,
        )

        activity = (
            self.activities().get()
        )

        self.assertEqual(
            activity.actor,
            self.actor,
        )

        self.assertEqual(
            activity.team,
            self.team,
        )

        self.assertEqual(
            activity.metadata[
                "cantidad_registros"
            ],
            1,
        )

        self.assertEqual(
            activity.metadata[
                "recurso_real_ids"
            ],
            list(
                self.created_reals()
                .values_list(
                    "pk",
                    flat=True,
                )
            ),
        )

    def test_employee_without_dates_registers_one_activity(
        self,
    ):
        base = TareaRecursoReal(
            empleado=self.employee,
            recurso=None,
            unidad="",
            cantidad=Decimal(
                "4.0000"
            ),
            horas_reales=None,
            precio_unidad=Decimal(
                "10.0000"
            ),
            inicio_recurso_real=None,
            fin_recurso_real=None,
            observaciones="",
            raw_data={},
        )

        form = self.valid_form(
            base
        )

        with patch(
            (
                "planificacion_obra."
                "views._tr_get_tarea_"
                "for_user"
            ),
            return_value=self.tarea,
        ), patch(
            (
                "planificacion_obra.forms."
                "TareaRecursoRealManualForm"
            ),
            return_value=form,
        ), patch(
            (
                "planificacion_obra.views."
                "_tr_fill_common_real"
            ),
            side_effect=self.fill_common,
        ):
            with self.captureOnCommitCallbacks(
                execute=True
            ):
                response = self.client.post(
                    self.create_url(),
                    {
                        "tipo_recurso_ui": (
                            "M.O. ADM."
                        ),
                    },
                )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.assertEqual(
            self.created_reals().count(),
            1,
        )

        created = (
            self.created_reals().get()
        )

        self.assertEqual(
            created.cantidad,
            Decimal("4.0000"),
        )

        self.assertEqual(
            created.horas_reales,
            Decimal("4.0000"),
        )

        self.assertEqual(
            self.activities().count(),
            1,
        )

    def test_workday_range_is_one_summary_activity(
        self,
    ):
        day_one = dt.date(
            2026,
            7,
            20,
        )

        day_two = dt.date(
            2026,
            7,
            21,
        )

        base = TareaRecursoReal(
            empleado=self.employee,
            recurso=None,
            unidad="HRS",
            cantidad=Decimal(
                "3.0000"
            ),
            horas_reales=Decimal(
                "3.0000"
            ),
            precio_unidad=Decimal(
                "10.0000"
            ),
            inicio_recurso_real=day_one,
            fin_recurso_real=day_two,
            observaciones="",
            raw_data={},
        )

        form = self.valid_form(
            base
        )

        with patch(
            (
                "planificacion_obra."
                "views._tr_get_tarea_"
                "for_user"
            ),
            return_value=self.tarea,
        ), patch(
            (
                "planificacion_obra.forms."
                "TareaRecursoRealManualForm"
            ),
            return_value=form,
        ), patch(
            (
                "planificacion_obra.views."
                "_tr_employee_workdays"
            ),
            return_value=[
                (
                    day_one,
                    Decimal("3.0000"),
                ),
                (
                    day_two,
                    Decimal("3.0000"),
                ),
            ],
        ), patch(
            (
                "planificacion_obra.views."
                "_tr_fill_common_real"
            ),
            side_effect=self.fill_common,
        ):
            with self.captureOnCommitCallbacks(
                execute=True
            ):
                response = self.client.post(
                    self.create_url(),
                    {
                        "tipo_recurso_ui": (
                            "M.O. ADM."
                        ),
                    },
                )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.assertEqual(
            self.created_reals().count(),
            2,
        )

        self.assertEqual(
            self.activities().count(),
            1,
        )

        activity = (
            self.activities().get()
        )

        self.assertEqual(
            activity.metadata[
                "cantidad_registros"
            ],
            2,
        )

        self.assertEqual(
            activity.metadata[
                "cantidad_total"
            ],
            "6.0000",
        )

    def test_confirmed_non_workday_range_is_one_summary_activity(
        self,
    ):
        day_one = dt.date(
            2026,
            7,
            25,
        )

        day_two = dt.date(
            2026,
            7,
            26,
        )

        base = TareaRecursoReal(
            empleado=self.employee,
            recurso=None,
            unidad="HRS",
            cantidad=Decimal(
                "2.0000"
            ),
            horas_reales=Decimal(
                "2.0000"
            ),
            precio_unidad=Decimal(
                "10.0000"
            ),
            inicio_recurso_real=day_one,
            fin_recurso_real=day_two,
            observaciones="",
            raw_data={},
        )

        form = self.valid_form(
            base
        )

        with patch(
            (
                "planificacion_obra."
                "views._tr_get_tarea_"
                "for_user"
            ),
            return_value=self.tarea,
        ), patch(
            (
                "planificacion_obra.forms."
                "TareaRecursoRealManualForm"
            ),
            return_value=form,
        ), patch(
            (
                "planificacion_obra.views."
                "_tr_employee_workdays"
            ),
            return_value=[],
        ), patch(
            (
                "planificacion_obra.views."
                "_tr_fill_common_real"
            ),
            side_effect=self.fill_common,
        ):
            with self.captureOnCommitCallbacks(
                execute=True
            ):
                response = self.client.post(
                    self.create_url(),
                    {
                        "confirmar_no_laborable": (
                            "1"
                        ),
                        "tipo_recurso_ui": (
                            "M.O. ADM."
                        ),
                    },
                )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.assertEqual(
            self.created_reals().count(),
            2,
        )

        self.assertEqual(
            self.activities().count(),
            1,
        )

        activity = (
            self.activities().get()
        )

        self.assertEqual(
            activity.metadata[
                "cantidad_registros"
            ],
            2,
        )

        for created in (
            self.created_reals()
        ):
            self.assertTrue(
                created.raw_data[
                    "no_laborable_confirmado"
                ]
            )

    def test_create_rolls_back_if_activity_fails(
        self,
    ):
        base = TareaRecursoReal(
            empleado=None,
            recurso=None,
            unidad="UD",
            cantidad=Decimal(
                "2.0000"
            ),
            precio_unidad=Decimal(
                "3.0000"
            ),
            costo_recurso_real=(
                Decimal("6.0000")
            ),
            raw_data={},
        )

        form = self.valid_form(
            base
        )

        with patch(
            (
                "planificacion_obra."
                "views._tr_get_tarea_"
                "for_user"
            ),
            return_value=self.tarea,
        ), patch(
            (
                "planificacion_obra.forms."
                "TareaRecursoRealManualForm"
            ),
            return_value=form,
        ), patch(
            (
                "planificacion_obra.views."
                "_tr_fill_common_real"
            ),
            side_effect=self.fill_common,
        ), patch(
            (
                "planificacion_obra.views."
                "registrar_creacion_"
                "recursos_reales_manuales"
            ),
            side_effect=RuntimeError(
                "activity failure"
            ),
        ):
            with self.assertRaises(
                RuntimeError
            ):
                self.client.post(
                    self.create_url(),
                    {
                        "tipo_recurso_ui": (
                            "MATERIAL"
                        ),
                    },
                )

        self.assertEqual(
            self.created_reals().count(),
            0,
        )

        self.assertEqual(
            self.activities().count(),
            0,
        )

    def test_invalid_form_creates_nothing(
        self,
    ):
        form = MagicMock()
        form.is_valid.return_value = False

        with patch(
            (
                "planificacion_obra."
                "views._tr_get_tarea_"
                "for_user"
            ),
            return_value=self.tarea,
        ), patch(
            (
                "planificacion_obra.forms."
                "TareaRecursoRealManualForm"
            ),
            return_value=form,
        ), patch(
            (
                "planificacion_obra.views."
                "registrar_creacion_"
                "recursos_reales_manuales"
            )
        ) as recorder:
            response = self.client.post(
                self.create_url(),
                {},
            )

        self.assertEqual(
            response.status_code,
            200,
        )

        recorder.assert_not_called()

        self.assertEqual(
            self.created_reals().count(),
            0,
        )

        self.assertEqual(
            self.activities().count(),
            0,
        )


@override_settings(
    SECURE_SSL_REDIRECT=False
)
class ResourceRealUpdateViewTests(
    TestCase
):
    def setUp(self):
        ResourceRealCreateViewTests.setUp(
            self
        )

        self.real = TareaRecursoReal(
            empleado=None,
            recurso=None,
            unidad="UD",
            cantidad=Decimal(
                "2.0000"
            ),
            precio_unidad=Decimal(
                "3.0000"
            ),
            costo_recurso=Decimal(
                "6.0000"
            ),
            costo_recurso_real=Decimal(
                "6.0000"
            ),
            observaciones="Inicial",
            raw_data={},
        )

        ResourceRealCreateViewTests.fill_common(
            self,
            self.real,
            self.tarea,
        )

        self.real.save()

    def update_url(self):
        return reverse(
            (
                "planificacion_obra:"
                "tarea_recurso_real_update"
            ),
            args=[
                self.real.pk,
            ],
        )

    def update_activities(self):
        return (
            ActividadPlataforma.objects
            .filter(
                modulo=(
                    "planificacion_obra"
                ),
                accion=(
                    "editar_recurso_real_manual"
                ),
                objeto_id=self.real.pk,
            )
        )

    def form_for(
        self,
        callback,
    ):
        form = MagicMock()
        form.is_valid.return_value = True
        form.save.side_effect = (
            lambda commit=False: callback()
        )

        return form

    def test_update_registers_one_activity(
        self,
    ):
        def mutate():
            self.real.cantidad = Decimal(
                "5.0000"
            )

            self.real.costo_recurso_real = (
                Decimal("15.0000")
            )

            self.real.observaciones = (
                "Cantidad corregida"
            )

            return self.real

        form = self.form_for(
            mutate
        )

        with patch(
            (
                "planificacion_obra.views."
                "_get_real_for_user"
            ),
            return_value=self.real,
        ), patch(
            (
                "planificacion_obra.forms."
                "TareaRecursoRealManualForm"
            ),
            return_value=form,
        ):
            with self.captureOnCommitCallbacks(
                execute=True
            ):
                response = self.client.post(
                    self.update_url(),
                    {},
                )

        self.assertEqual(
            response.status_code,
            302,
        )

        persisted = (
            TareaRecursoReal.objects
            .get(pk=self.real.pk)
        )

        self.assertEqual(
            persisted.cantidad,
            Decimal("5.0000"),
        )

        self.assertEqual(
            persisted.costo_recurso_real,
            Decimal("15.0000"),
        )

        self.assertEqual(
            self.update_activities().count(),
            1,
        )

        activity = (
            self.update_activities().get()
        )

        self.assertEqual(
            activity.actor,
            self.actor,
        )

        self.assertEqual(
            activity.team,
            self.team,
        )

        self.assertEqual(
            activity.visibilidad,
            "EQUIPO",
        )

        self.assertEqual(
            activity.metadata[
                "categoria_cambio"
            ],
            "CANTIDAD_HORAS_COSTE",
        )

        self.assertIn(
            "cantidad",
            activity.metadata[
                "campos_cambiados"
            ],
        )

        self.assertEqual(
            activity.metadata[
                "cambios"
            ]["cantidad"],
            {
                "anterior": "2.0000",
                "nuevo": "5.0000",
            },
        )

    def test_unchanged_update_creates_no_activity(
        self,
    ):
        form = self.form_for(
            lambda: self.real
        )

        with patch(
            (
                "planificacion_obra.views."
                "_get_real_for_user"
            ),
            return_value=self.real,
        ), patch(
            (
                "planificacion_obra.forms."
                "TareaRecursoRealManualForm"
            ),
            return_value=form,
        ):
            with self.captureOnCommitCallbacks(
                execute=True
            ):
                response = self.client.post(
                    self.update_url(),
                    {},
                )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.assertEqual(
            self.update_activities().count(),
            0,
        )

    def test_update_rolls_back_if_activity_fails(
        self,
    ):
        original_quantity = (
            self.real.cantidad
        )

        original_cost = (
            self.real
            .costo_recurso_real
        )

        def mutate():
            self.real.cantidad = Decimal(
                "9.0000"
            )

            self.real.costo_recurso_real = (
                Decimal("27.0000")
            )

            return self.real

        form = self.form_for(
            mutate
        )

        with patch(
            (
                "planificacion_obra.views."
                "_get_real_for_user"
            ),
            return_value=self.real,
        ), patch(
            (
                "planificacion_obra.forms."
                "TareaRecursoRealManualForm"
            ),
            return_value=form,
        ), patch(
            (
                "planificacion_obra.views."
                "registrar_cambio_"
                "recurso_real_manual"
            ),
            side_effect=RuntimeError(
                "activity failure"
            ),
        ):
            with self.assertRaises(
                RuntimeError
            ):
                self.client.post(
                    self.update_url(),
                    {},
                )

        persisted = (
            TareaRecursoReal.objects
            .get(pk=self.real.pk)
        )

        self.assertEqual(
            persisted.cantidad,
            original_quantity,
        )

        self.assertEqual(
            persisted.costo_recurso_real,
            original_cost,
        )

        self.assertEqual(
            self.update_activities().count(),
            0,
        )


@override_settings(
    SECURE_SSL_REDIRECT=False
)
class ResourceRealDeleteViewTests(
    TestCase
):
    def setUp(self):
        ResourceRealCreateViewTests.setUp(
            self
        )

        self.real = TareaRecursoReal(
            empleado=None,
            recurso=None,
            unidad="UD",
            cantidad=Decimal(
                "2.0000"
            ),
            precio_unidad=Decimal(
                "3.0000"
            ),
            costo_recurso=Decimal(
                "6.0000"
            ),
            costo_recurso_real=Decimal(
                "6.0000"
            ),
            observaciones=(
                "Recurso para eliminar"
            ),
            raw_data={},
        )

        ResourceRealCreateViewTests.fill_common(
            self,
            self.real,
            self.tarea,
        )

        self.real.save()
        self.real_id = self.real.pk

    def delete_url(self):
        return reverse(
            (
                "planificacion_obra:"
                "tarea_recurso_real_delete"
            ),
            args=[
                self.real_id,
            ],
        )

    def delete_activities(self):
        return (
            ActividadPlataforma.objects
            .filter(
                modulo=(
                    "planificacion_obra"
                ),
                accion=(
                    "eliminar_recurso_real_manual"
                ),
                objeto_id=self.real_id,
            )
        )

    def test_get_does_not_delete_or_register_activity(
        self,
    ):
        with patch(
            (
                "planificacion_obra.views."
                "_get_real_for_user"
            ),
            return_value=self.real,
        ):
            response = self.client.get(
                self.delete_url()
            )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertTrue(
            TareaRecursoReal.objects
            .filter(pk=self.real_id)
            .exists()
        )

        self.assertEqual(
            self.delete_activities().count(),
            0,
        )

    def test_delete_registers_one_activity(
        self,
    ):
        with patch(
            (
                "planificacion_obra.views."
                "_get_real_for_user"
            ),
            return_value=self.real,
        ):
            with self.captureOnCommitCallbacks(
                execute=True
            ):
                response = self.client.post(
                    self.delete_url(),
                    {},
                )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.assertFalse(
            TareaRecursoReal.objects
            .filter(pk=self.real_id)
            .exists()
        )

        self.assertEqual(
            self.delete_activities().count(),
            1,
        )

        activity = (
            self.delete_activities().get()
        )

        self.assertEqual(
            activity.actor,
            self.actor,
        )

        self.assertEqual(
            activity.team,
            self.team,
        )

        self.assertEqual(
            activity.visibilidad,
            "EQUIPO",
        )

        self.assertEqual(
            activity.objeto_id,
            self.real_id,
        )

        self.assertEqual(
            activity.metadata[
                "recurso_real_id"
            ],
            self.real_id,
        )

        self.assertEqual(
            activity.metadata[
                "anterior"
            ]["id"],
            self.real_id,
        )

        self.assertEqual(
            activity.metadata[
                "anterior"
            ]["cantidad"],
            "2.0000",
        )

    def test_delete_rolls_back_if_activity_fails(
        self,
    ):
        with patch(
            (
                "planificacion_obra.views."
                "_get_real_for_user"
            ),
            return_value=self.real,
        ), patch(
            (
                "planificacion_obra.views."
                "registrar_eliminacion_"
                "recurso_real_manual"
            ),
            side_effect=RuntimeError(
                "activity failure"
            ),
        ):
            with self.assertRaises(
                RuntimeError
            ):
                self.client.post(
                    self.delete_url(),
                    {},
                )

        self.assertTrue(
            TareaRecursoReal.objects
            .filter(pk=self.real_id)
            .exists()
        )

        self.assertEqual(
            self.delete_activities().count(),
            0,
        )

    def test_derived_resource_is_not_deleted(
        self,
    ):
        raw = dict(
            self.real.raw_data
            or {}
        )

        raw.update({
            "origen": (
                "portal_asignacion_obra"
            ),
            "source": (
                "portal_asignacion_obra"
            ),
        })

        self.real.raw_data = raw

        self.real.save(
            update_fields=[
                "raw_data",
                "updated_at",
            ]
        )

        with patch(
            (
                "planificacion_obra.views."
                "_get_real_for_user"
            ),
            return_value=self.real,
        ):
            response = self.client.post(
                self.delete_url(),
                {},
            )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.assertTrue(
            TareaRecursoReal.objects
            .filter(pk=self.real_id)
            .exists()
        )

        self.assertEqual(
            self.delete_activities().count(),
            0,
        )
