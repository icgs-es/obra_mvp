from django.contrib.auth import (
    get_user_model,
)
from django.contrib.auth.models import Group
from django.test import (
    RequestFactory,
    TestCase,
)
from django.utils import timezone

from actividad.models import (
    ActividadPlataforma,
)
from usuarios.models import Team

from .access import (
    editable_events_for_user,
    resolve_active_agenda_team,
    resolve_calendar_for_event,
    selected_agenda_team_ids,
    visible_events_for_user,
)
from .forms import EventoForm
from .models import (
    Calendar,
    Event,
)
from .services import (
    events_between_for_user,
)


User = get_user_model()


class AgendaAccessContractTests(
    TestCase
):
    def setUp(self):
        self.team_a = Team.objects.create(
            name="Agenda Access Team A",
        )

        self.team_b = Team.objects.create(
            name="Agenda Access Team B",
        )

        self.creator = (
            User.objects.create_user(
                username="agenda_creator",
                password="x",
            )
        )

        self.member = (
            User.objects.create_user(
                username="agenda_member",
                password="x",
            )
        )

        self.manager = (
            User.objects.create_user(
                username="agenda_manager",
                password="x",
                is_staff=True,
            )
        )

        self.other = (
            User.objects.create_user(
                username="agenda_other",
                password="x",
            )
        )

        self.creator.teams.add(
            self.team_a
        )

        self.member.teams.add(
            self.team_a
        )

        self.manager.teams.add(
            self.team_a
        )
        self.manager.groups.add(
            Group.objects.get_or_create(name="Gerencia")[0]
        )

        self.other.teams.add(
            self.team_b
        )

        self.private_calendar = (
            Calendar.objects.create(
                nombre="Privado A",
                tipo="PERSONAL",
                owner=self.creator,
            )
        )

        self.legacy_private_calendar = (
            Calendar.objects.create(
                nombre="Privado legacy",
                tipo="PRIVATE",
                owner=None,
            )
        )

        self.department_calendar = (
            Calendar.objects.create(
                nombre="Departamento",
                tipo="TEAM",
            )
        )

        self.global_calendar = (
            Calendar.objects.create(
                nombre="Global",
                tipo="ORG",
            )
        )

        self.other_private_calendar = (
            Calendar.objects.create(
                nombre="Privado B",
                tipo="PERSONAL",
                owner=self.other,
            )
        )

        start = (
            timezone.now()
            + timezone.timedelta(
                hours=1
            )
        )

        end = (
            start
            + timezone.timedelta(
                hours=1
            )
        )

        self.private_a = (
            Event.objects.create(
                team=self.team_a,
                title="Privado A",
                calendar=(
                    self.private_calendar
                ),
                start=start,
                end=end,
                visibility=(
                    Event.Visibility
                    .PRIVADA
                ),
                created_by=self.creator,
            )
        )

        self.shared_a = (
            Event.objects.create(
                team=self.team_a,
                title="Global A",
                calendar=(
                    self.global_calendar
                ),
                start=start,
                end=end,
                visibility=(
                    Event.Visibility
                    .GLOBAL
                ),
                created_by=self.creator,
            )
        )

        self.shared_b = (
            Event.objects.create(
                team=self.team_b,
                title="Global B",
                calendar=(
                    self.global_calendar
                ),
                start=start,
                end=end,
                visibility=(
                    Event.Visibility
                    .GLOBAL
                ),
                created_by=self.other,
            )
        )

        self.legacy_private = (
            Event.objects.create(
                team=None,
                title="Privado legacy",
                calendar=(
                    self.legacy_private_calendar
                ),
                start=start,
                end=end,
                visibility=(
                    Event.Visibility
                    .PRIVADA
                ),
                created_by=self.creator,
            )
        )

    def visible_ids(
        self,
        user,
        active_team_id="all",
    ):
        return set(
            visible_events_for_user(
                user,
                active_team_id=(
                    active_team_id
                ),
            )
            .values_list(
                "pk",
                flat=True,
            )
        )

    def editable_ids(
        self,
        user,
        active_team_id="all",
    ):
        return set(
            editable_events_for_user(
                user,
                active_team_id=(
                    active_team_id
                ),
            )
            .values_list(
                "pk",
                flat=True,
            )
        )

    def test_private_and_team_visibility(
        self,
    ):
        self.assertEqual(
            self.visible_ids(
                self.creator
            ),
            {
                self.private_a.pk,
                self.shared_a.pk,
                self.legacy_private.pk,
            },
        )

        self.assertEqual(
            self.visible_ids(
                self.member
            ),
            {
                self.shared_a.pk,
            },
        )

        self.assertEqual(
            self.visible_ids(
                self.other
            ),
            {
                self.shared_b.pk,
            },
        )

    def test_global_does_not_cross_teams(
        self,
    ):
        self.assertNotIn(
            self.shared_b.pk,
            self.visible_ids(
                self.creator
            ),
        )

        self.assertNotIn(
            self.shared_a.pk,
            self.visible_ids(
                self.other
            ),
        )

    def test_invalid_selector_preserves_only_legacy(
        self,
    ):
        self.assertEqual(
            self.visible_ids(
                self.creator,
                "999999",
            ),
            {
                self.legacy_private.pk,
            },
        )

        self.assertEqual(
            self.visible_ids(
                self.member,
                "999999",
            ),
            set(),
        )

    def test_manager_edit_is_same_team_only(
        self,
    ):
        self.assertEqual(
            self.editable_ids(
                self.manager
            ),
            {
                self.shared_a.pk,
            },
        )

        self.assertNotIn(
            self.private_a.pk,
            self.editable_ids(
                self.manager
            ),
        )

        self.assertNotIn(
            self.shared_b.pk,
            self.editable_ids(
                self.manager
            ),
        )

    def test_staff_without_functional_permission_cannot_manage_events(self):
        staff = User.objects.create_user(
            username="agenda_staff_without_functional_permission",
            password="x",
            is_staff=True,
        )
        staff.teams.add(self.team_a)

        self.assertEqual(self.editable_ids(staff), set())
        self.assertEqual(self.visible_ids(staff), {self.shared_a.pk})

    def test_creator_edits_private_and_shared(
        self,
    ):
        self.assertEqual(
            self.editable_ids(
                self.creator
            ),
            {
                self.private_a.pk,
                self.shared_a.pk,
                self.legacy_private.pk,
            },
        )

    def test_selected_team_ids(
        self,
    ):
        self.assertEqual(
            selected_agenda_team_ids(
                self.creator,
                "all",
            ),
            {
                self.team_a.pk,
            },
        )

        self.assertEqual(
            selected_agenda_team_ids(
                self.creator,
                str(self.team_a.pk),
            ),
            {
                self.team_a.pk,
            },
        )

        self.assertEqual(
            selected_agenda_team_ids(
                self.creator,
                str(self.team_b.pk),
            ),
            set(),
        )

    def test_strict_team_resolver(
        self,
    ):
        factory = RequestFactory()

        def resolve(value):
            request = factory.get(
                "/app/agenda/"
            )

            request.user = self.creator

            request.session = {
                "active_team_id": value,
            }

            return (
                resolve_active_agenda_team(
                    request
                )
            )

        self.assertIsNone(
            resolve("all")
        )

        self.assertIsNone(
            resolve(None)
        )

        self.assertIsNone(
            resolve(
                self.team_b.pk
            )
        )

        self.assertEqual(
            resolve(
                self.team_a.pk
            ),
            self.team_a,
        )

    def test_temporal_service_uses_team_scope(
        self,
    ):
        start = (
            timezone.now()
            - timezone.timedelta(
                days=1
            )
        )

        end = (
            timezone.now()
            + timezone.timedelta(
                days=1
            )
        )

        ids = set(
            events_between_for_user(
                self.member,
                start,
                end,
                Event.objects.all(),
                active_team_id=(
                    self.team_a.pk
                ),
            )
            .values_list(
                "pk",
                flat=True,
            )
        )

        self.assertEqual(
            ids,
            {
                self.shared_a.pk,
            },
        )


class AgendaFormScopeTests(
    TestCase
):
    def setUp(self):
        self.team_a = Team.objects.create(
            name="Agenda Form Team A",
        )

        self.team_b = Team.objects.create(
            name="Agenda Form Team B",
        )

        self.user_a = (
            User.objects.create_user(
                username="form_user_a",
                password="x",
            )
        )

        self.member_a = (
            User.objects.create_user(
                username="form_member_a",
                password="x",
            )
        )

        self.user_b = (
            User.objects.create_user(
                username="form_user_b",
                password="x",
            )
        )

        self.user_a.teams.add(
            self.team_a
        )

        self.member_a.teams.add(
            self.team_a
        )

        self.user_b.teams.add(
            self.team_b
        )

        self.private_calendar = (
            Calendar.objects.create(
                nombre="Privado A",
                tipo="PERSONAL",
                owner=self.user_a,
            )
        )

        self.other_private_calendar = (
            Calendar.objects.create(
                nombre="Privado B",
                tipo="PERSONAL",
                owner=self.user_b,
            )
        )

        self.global_calendar = (
            Calendar.objects.create(
                nombre="Global",
                tipo="ORG",
            )
        )

    def payload(
        self,
        *,
        calendar,
        visibility,
        attendees=None,
    ):
        start = (
            timezone.now()
            + timezone.timedelta(
                hours=1
            )
        )

        end = (
            start
            + timezone.timedelta(
                hours=1
            )
        )

        return {
            "title": "Evento form",
            "calendar": calendar.pk,
            "start": start.strftime(
                "%Y-%m-%dT%H:%M"
            ),
            "end": end.strftime(
                "%Y-%m-%dT%H:%M"
            ),
            "all_day": "",
            "rrule": "",
            "who_text": "",
            "who_users": [
                user.pk
                for user in (
                    attendees
                    or []
                )
            ],
            "description": "",
            "status": "PENDIENTE",
            "location": "",
            "visibility": visibility,
        }

    def test_assignees_are_team_scoped(
        self,
    ):
        form = EventoForm(
            user=self.user_a,
            team=self.team_a,
        )

        ids = set(
            form.fields[
                "who_users"
            ]
            .queryset
            .values_list(
                "pk",
                flat=True,
            )
        )

        self.assertEqual(
            ids,
            {
                self.user_a.pk,
                self.member_a.pk,
            },
        )

        self.assertNotIn(
            self.user_b.pk,
            ids,
        )

    def test_other_personal_calendar_hidden(
        self,
    ):
        form = EventoForm(
            user=self.user_a,
            team=self.team_a,
        )

        ids = set(
            form.fields[
                "calendar"
            ]
            .queryset
            .values_list(
                "pk",
                flat=True,
            )
        )

        self.assertIn(
            self.private_calendar.pk,
            ids,
        )

        self.assertIn(
            self.global_calendar.pk,
            ids,
        )

        self.assertNotIn(
            self.other_private_calendar.pk,
            ids,
        )

    def test_calendar_visibility_mismatch(
        self,
    ):
        form = EventoForm(
            data=self.payload(
                calendar=(
                    self.private_calendar
                ),
                visibility="GLOBAL",
                attendees=[
                    self.user_a,
                ],
            ),
            user=self.user_a,
            team=self.team_a,
        )

        self.assertFalse(
            form.is_valid()
        )

        errors = (
            form.errors.as_data()
        )

        self.assertEqual(
            errors["calendar"][0].code,
            (
                "calendar_visibility_mismatch"
            ),
        )

    def test_cross_team_attendee_rejected(
        self,
    ):
        form = EventoForm(
            data=self.payload(
                calendar=(
                    self.private_calendar
                ),
                visibility="PRIVADA",
                attendees=[
                    self.user_b,
                ],
            ),
            user=self.user_a,
            team=self.team_a,
        )

        self.assertFalse(
            form.is_valid()
        )

        self.assertIn(
            "who_users",
            form.errors,
        )

    def test_resolve_legacy_global_calendar(
        self,
    ):
        calendar = (
            resolve_calendar_for_event(
                user=self.user_a,
                visibility="GLOBAL",
            )
        )

        self.assertEqual(
            calendar,
            self.global_calendar,
        )

    def test_contract_creates_no_activity(
        self,
    ):
        EventoForm(
            user=self.user_a,
            team=self.team_a,
        )

        self.assertEqual(
            ActividadPlataforma.objects.count(),
            0,
        )
