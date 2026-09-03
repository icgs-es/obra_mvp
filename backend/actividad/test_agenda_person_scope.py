from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.utils import timezone

from agenda.models import Calendar, Event
from usuarios.models import Team
from actividad.models import ActividadPlataforma
from actividad.selectors import actividad_visible_para_usuario


class AgendaPersonScopeActivityTests(TestCase):

    def setUp(self):
        User = get_user_model()

        self.team_a = Team.objects.create(name="Empresa A Scope")
        self.team_b = Team.objects.create(name="Empresa B Scope")

        self.actor = User.objects.create_user(
            username="scope_actor"
        )
        self.manager = User.objects.create_user(
            username="scope_manager"
        )
        self.outsider = User.objects.create_user(
            username="scope_outsider"
        )

        self.actor.teams.add(self.team_b)
        self.manager.teams.add(self.team_a)
        self.outsider.teams.add(self.team_a)

        gerencia, _ = Group.objects.get_or_create(
            name="Gerencia"
        )
        self.manager.groups.add(gerencia)

        calendar = Calendar.objects.create(
            nombre="Personal",
            tipo="PERSONAL",
            owner=self.actor,
        )

        self.event = Event.objects.create(
            title="Evento privado",
            calendar=calendar,
            start=timezone.now(),
            visibility=Event.Visibility.PRIVADA,
            team=self.team_b,
            created_by=self.actor,
        )

        self.activity = ActividadPlataforma.objects.create(
            team=self.team_b,
            actor=self.actor,
            modulo="agenda",
            accion="crear_evento",
            tipo_objeto="agenda.event",
            objeto_id=self.event.pk,
            objeto_repr=self.event.title,
            visibilidad=ActividadPlataforma.Visibilidad.OBJETO,
        )

        self.gestion = ActividadPlataforma.objects.create(
            team=self.team_b,
            actor=self.actor,
            modulo="gestion",
            accion="editar",
            tipo_objeto="gestion.factura",
            objeto_id=999,
            objeto_repr="Factura",
            visibilidad=ActividadPlataforma.Visibilidad.EQUIPO,
        )

    def test_gerencia_ve_agenda_sin_compartir_team(self):
        qs = actividad_visible_para_usuario(
            user=self.manager,
            active_team_id="all",
        )
        self.assertIn(self.activity, qs)

    def test_selector_empresa_no_oculta_agenda(self):
        qs = actividad_visible_para_usuario(
            user=self.manager,
            active_team_id=str(self.team_a.pk),
        )
        self.assertIn(self.activity, qs)

    def test_usuario_ordinario_no_ve_privada_ajena(self):
        qs = actividad_visible_para_usuario(
            user=self.outsider,
            active_team_id="all",
        )
        self.assertNotIn(self.activity, qs)

    def test_actor_conserva_acceso(self):
        qs = actividad_visible_para_usuario(
            user=self.actor,
            active_team_id="all",
        )
        self.assertIn(self.activity, qs)

    def test_gestion_continua_aislada_por_team(self):
        qs = actividad_visible_para_usuario(
            user=self.manager,
            active_team_id="all",
        )
        self.assertNotIn(self.gestion, qs)
