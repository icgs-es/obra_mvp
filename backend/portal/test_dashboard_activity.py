from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from actividad.models import ActividadPlataforma
from usuarios.models import Team

from .activity_presentation import (
    compactar_actividades,
    nombre_familiar,
)
from .views import (
    _dashboard_activity_context,
    _presentar_actividad,
)


class PortalDashboardActivityTests(TestCase):
    def setUp(self):
        User = get_user_model()

        self.user = User.objects.create_user(
            username="portal_activity_user",
        )

        self.other_user = User.objects.create_user(
            username="portal_activity_other",
        )

        self.external_user = User.objects.create_user(
            username="portal_activity_external",
        )

        self.team = Team.objects.create(
            name="Empresa visible",
        )

        self.external_team = Team.objects.create(
            name="Empresa externa",
        )

        self.team.members.add(
            self.user,
            self.other_user,
        )

        self.external_team.members.add(
            self.external_user
        )

        tz = timezone.get_current_timezone()

        self.today = timezone.make_aware(
            datetime(2026, 7, 18, 10, 0),
            tz,
        )

        self.yesterday = timezone.make_aware(
            datetime(2026, 7, 17, 12, 0),
            tz,
        )

        self.today_activity = (
            ActividadPlataforma.objects.create(
                team=self.team,
                actor=self.other_user,
                modulo="archivos",
                accion="subida",
                descripcion=(
                    "ha subido 2 archivos "
                    "a FORMACION."
                ),
                metadata={
                    "cantidad": 2,
                    "nombres": [
                        "uno.pdf",
                        "dos.pdf",
                    ],
                },
                url="/app/archivos/",
                visibilidad=(
                    ActividadPlataforma
                    .Visibilidad
                    .EQUIPO
                ),
                ocurrida_en=self.today,
            )
        )

        self.yesterday_activity = (
            ActividadPlataforma.objects.create(
                team=self.team,
                actor=self.user,
                modulo="gestion",
                accion="crear",
                descripcion=(
                    "ha creado una factura."
                ),
                visibilidad=(
                    ActividadPlataforma
                    .Visibilidad
                    .EQUIPO
                ),
                ocurrida_en=self.yesterday,
            )
        )

        ActividadPlataforma.objects.create(
            team=self.external_team,
            actor=self.external_user,
            modulo="archivos",
            accion="subida",
            descripcion="actividad externa",
            visibilidad=(
                ActividadPlataforma
                .Visibilidad
                .EQUIPO
            ),
            ocurrida_en=self.today,
        )

        ActividadPlataforma.objects.create(
            team=self.team,
            actor=self.user,
            modulo="sistema",
            accion="interno",
            descripcion="actividad oculta",
            visible_en_dashboard=False,
            ocurrida_en=self.today,
        )

    def request(
        self,
        active_team_id="all",
        get=None,
    ):
        return SimpleNamespace(
            user=self.user,
            session={
                "active_team_id": active_team_id,
            },
            GET=get or {},
        )

    @patch(
        "portal.views.timezone.localdate",
        return_value=datetime(
            2026,
            7,
            18,
        ).date(),
    )
    def test_modo_todas_agrupa_hoy_y_ayer(
        self,
        _localdate,
    ):
        context = _dashboard_activity_context(
            self.request()
        )

        self.assertEqual(
            context["actividad_hoy_count"],
            1,
        )

        self.assertEqual(
            context["actividad_semana_count"],
            2,
        )

        self.assertEqual(
            context[
                "actividad_mia_semana_count"
            ],
            1,
        )

        self.assertEqual(
            [
                grupo["label"]
                for grupo
                in context["actividad_grupos"]
            ],
            ["Hoy", "Ayer"],
        )

        today_item = (
            context["actividad_grupos"]
            [0]["items"][0]
        )

        self.assertEqual(
            today_item.detalle_nombres,
            ["uno.pdf", "dos.pdf"],
        )

    @patch(
        "portal.views.timezone.localdate",
        return_value=datetime(
            2026,
            7,
            18,
        ).date(),
    )
    def test_filtro_mi_actividad(
        self,
        _localdate,
    ):
        context = _dashboard_activity_context(
            self.request(
                get={
                    "actividad_alcance": "mi",
                }
            )
        )

        self.assertEqual(
            context["actividad_alcance"],
            "mi",
        )

        self.assertEqual(
            context["actividad_semana_count"],
            1,
        )

        item = (
            context["actividad_grupos"]
            [0]["items"][0]
        )

        self.assertEqual(
            item.id,
            self.yesterday_activity.id,
        )

    @patch(
        "portal.views.timezone.localdate",
        return_value=datetime(
            2026,
            7,
            18,
        ).date(),
    )
    def test_filtro_modulo_case_insensitive(
        self,
        _localdate,
    ):
        context = _dashboard_activity_context(
            self.request(
                get={
                    "actividad_modulo": (
                        "ARCHIVOS"
                    ),
                }
            )
        )

        self.assertEqual(
            context[
                "actividad_modulo_activo"
            ],
            "archivos",
        )

        self.assertEqual(
            context["actividad_semana_count"],
            1,
        )

        item = (
            context["actividad_grupos"]
            [0]["items"][0]
        )

        self.assertEqual(
            item.id,
            self.today_activity.id,
        )

    @patch(
        "portal.views.timezone.localdate",
        return_value=datetime(
            2026,
            7,
            18,
        ).date(),
    )
    def test_empresa_ajena_no_expone_actividad(
        self,
        _localdate,
    ):
        context = _dashboard_activity_context(
            self.request(
                active_team_id=(
                    self.external_team.id
                )
            )
        )

        self.assertEqual(
            context["actividad_semana_count"],
            0,
        )

        self.assertEqual(
            context["actividad_grupos"],
            [],
        )


class PortalActivityCompactionTests(TestCase):
    def setUp(self):
        User = get_user_model()

        self.isabel = User.objects.create_user(
            username="isabel.login",
            first_name="Isabel",
            last_name="Mendez",
        )

        self.carle = User.objects.create_user(
            username="carle",
            first_name="",
            last_name="Usuario",
        )

        self.team_a = Team.objects.create(
            name="Empresa A",
        )

        self.team_b = Team.objects.create(
            name="Empresa B",
        )

        self.team_a.members.add(
            self.isabel,
            self.carle,
        )

        tz = timezone.get_current_timezone()

        self.base_time = timezone.make_aware(
            datetime(2026, 7, 23, 16, 30),
            tz,
        )

    def crear_actividad(
        self,
        *,
        actor=None,
        team=None,
        modulo="planificacion_obra",
        accion="crear_recurso_real_manual",
        tipo_objeto="TareaRecursoReal",
        ocurrida_en=None,
        metadata=None,
        descripcion=(
            "Se registró un recurso real manual."
        ),
        url="/app/detalle/",
    ):
        return ActividadPlataforma.objects.create(
            actor=actor or self.isabel,
            team=team or self.team_a,
            modulo=modulo,
            accion=accion,
            tipo_objeto=tipo_objeto,
            descripcion=descripcion,
            metadata=metadata or {},
            url=url,
            visibilidad=(
                ActividadPlataforma
                .Visibilidad
                .EQUIPO
            ),
            ocurrida_en=(
                ocurrida_en
                or self.base_time
            ),
        )

    def compactar(self, actividades):
        return compactar_actividades(
            [
                _presentar_actividad(item)
                for item in actividades
            ]
        )

    def test_agrupa_y_conserva_individuales(
        self,
    ):
        primera = self.crear_actividad(
            metadata={
                "cantidad_registros": 2,
            },
        )

        segunda = self.crear_actividad(
            ocurrida_en=(
                self.base_time
                - timedelta(minutes=10)
            ),
        )

        tercera = self.crear_actividad(
            ocurrida_en=(
                self.base_time
                - timedelta(minutes=20)
            ),
        )

        grupos = self.compactar(
            [primera, segunda, tercera]
        )

        self.assertEqual(len(grupos), 1)

        grupo = grupos[0]

        self.assertEqual(grupo.cantidad, 4)
        self.assertEqual(
            grupo.descripcion,
            (
                "registró 4 recursos "
                "reales manuales."
            ),
        )
        self.assertEqual(
            grupo.horario_label,
            "16:10–16:30",
        )
        self.assertEqual(
            {
                item.id
                for item in grupo.actividades
            },
            {
                primera.id,
                segunda.id,
                tercera.id,
            },
        )
        self.assertEqual(grupo.url, "")

    def test_separa_claves_funcionales(
        self,
    ):
        actividades = [
            self.crear_actividad(),
            self.crear_actividad(
                accion=(
                    "editar_recurso_real_manual"
                ),
            ),
            self.crear_actividad(
                actor=self.carle,
            ),
            self.crear_actividad(
                team=self.team_b,
            ),
            self.crear_actividad(
                modulo="archivos",
                accion="subida",
                tipo_objeto="archivos.archivo",
            ),
            self.crear_actividad(
                tipo_objeto="OtroTipo",
            ),
        ]

        grupos = self.compactar(
            actividades
        )

        self.assertEqual(
            len(grupos),
            len(actividades),
        )

    def test_separa_por_ventana_y_dia(
        self,
    ):
        actividades = [
            self.crear_actividad(
                ocurrida_en=self.base_time,
            ),
            self.crear_actividad(
                ocurrida_en=(
                    self.base_time
                    - timedelta(minutes=59)
                ),
            ),
            self.crear_actividad(
                ocurrida_en=(
                    self.base_time
                    - timedelta(minutes=61)
                ),
            ),
            self.crear_actividad(
                ocurrida_en=(
                    self.base_time
                    - timedelta(days=1)
                ),
            ),
        ]

        grupos = self.compactar(
            actividades
        )

        self.assertEqual(len(grupos), 3)

        self.assertEqual(
            sorted(
                len(group.actividades)
                for group in grupos
            ),
            [1, 1, 2],
        )

    def test_nombre_visible(
        self,
    ):
        self.assertEqual(
            nombre_familiar(self.isabel),
            "Isabel",
        )

        self.assertEqual(
            nombre_familiar(self.carle),
            "carle",
        )

        self.assertEqual(
            nombre_familiar(None),
            "Sistema",
        )

    def test_individual_conserva_url(
        self,
    ):
        actividad = self.crear_actividad(
            url="/app/objeto/99/",
        )

        grupo = self.compactar(
            [actividad]
        )[0]

        self.assertEqual(
            grupo.id,
            actividad.id,
        )

        self.assertEqual(
            grupo.url,
            "/app/objeto/99/",
        )

        self.assertEqual(
            len(grupo.actividades),
            1,
        )

    @patch(
        "portal.views.timezone.localdate",
        return_value=datetime(
            2026,
            7,
            24,
        ).date(),
    )
    def test_dashboard_renderiza_grupo(
        self,
        _localdate,
    ):
        self.crear_actividad()

        self.crear_actividad(
            ocurrida_en=(
                self.base_time
                - timedelta(minutes=5)
            ),
        )

        self.client.force_login(
            self.isabel
        )

        response = self.client.get(
            "/app/",
            secure=True,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "Isabel",
        )

        self.assertContains(
            response,
            (
                "registró 2 recursos "
                "reales manuales."
            ),
        )

        self.assertContains(
            response,
            "Ver actividades (2)",
        )

        self.assertContains(
            response,
            'href="/app/detalle/"',
            count=2,
        )
