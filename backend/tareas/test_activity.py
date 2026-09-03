from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import (
    get_user_model,
)
from django.test import (
    SimpleTestCase,
    TestCase,
    override_settings,
)
from django.urls import reverse

from actividad.models import (
    ActividadPlataforma,
)
from actividad.selectors import (
    actividad_visible_para_usuario,
)
from portal.views import (
    _dashboard_activity_context,
)
from usuarios.models import Team

from .activity import (
    registrar_cambio_tarea,
    registrar_creacion_tarea,
    snapshot_tarea,
)
from .models import Tarea


User = get_user_model()


class TaskActivityAdapterContractTests(
    TestCase
):
    def setUp(self):
        self.actor = User.objects.create_user(
            username="task_activity_actor",
        )

        self.assigned = User.objects.create_user(
            username="task_activity_assigned",
        )

        self.team = Team.objects.create(
            name="Task Activity Team",
        )

        self.actor.teams.add(self.team)
        self.assigned.teams.add(self.team)

    def create_task(
        self,
        *,
        visibility="privada",
        state="pendiente",
    ):
        task = Tarea.objects.create(
            team=self.team,
            titulo="Preparar informe",
            descripcion="Descripción",
            estado=state,
            prioridad="media",
            creador=self.actor,
            visibilidad=visibility,
        )

        task.asignados.add(self.actor)

        return task

    @patch(
        "tareas.activity.registrar_actividad"
    )
    def test_create_private_contract(
        self,
        registrar,
    ):
        task = self.create_task()

        registrar_creacion_tarea(
            tarea=task,
            actor=self.actor,
            diferir_hasta_commit=False,
        )

        kwargs = registrar.call_args.kwargs

        self.assertEqual(
            kwargs["modulo"],
            "tareas",
        )

        self.assertEqual(
            kwargs["accion"],
            "crear_tarea",
        )

        self.assertEqual(
            kwargs["team"],
            self.team,
        )

        self.assertEqual(
            kwargs["visibilidad"],
            (
                ActividadPlataforma
                .Visibilidad
                .ACTOR
            ),
        )

        self.assertEqual(
            kwargs["clave_idempotencia"],
            f"tareas:crear:{task.pk}",
        )

        self.assertIn(
            "Preparar informe",
            kwargs["descripcion"],
        )

    @patch(
        "tareas.activity.registrar_actividad"
    )
    def test_department_is_team_activity(
        self,
        registrar,
    ):
        task = self.create_task(
            visibility="depto"
        )

        registrar_creacion_tarea(
            tarea=task,
            actor=self.actor,
            diferir_hasta_commit=False,
        )

        kwargs = registrar.call_args.kwargs

        self.assertEqual(
            kwargs["visibilidad"],
            (
                ActividadPlataforma
                .Visibilidad
                .EQUIPO
            ),
        )

    @patch(
        "tareas.activity.registrar_actividad"
    )
    def test_completion_has_priority(
        self,
        registrar,
    ):
        task = self.create_task()
        previous = snapshot_tarea(task)

        task.estado = "hecha"
        task.descripcion = "También modificada"
        task.save()

        registrar_cambio_tarea(
            tarea=task,
            actor=self.actor,
            anterior=previous,
            diferir_hasta_commit=False,
        )

        kwargs = registrar.call_args.kwargs

        self.assertEqual(
            kwargs["accion"],
            "completar_tarea",
        )

        self.assertIn(
            "estado",
            kwargs["metadata"][
                "campos_cambiados"
            ],
        )

        self.assertIn(
            "descripcion",
            kwargs["metadata"][
                "campos_cambiados"
            ],
        )

    @patch(
        "tareas.activity.registrar_actividad"
    )
    def test_assignment_change_contract(
        self,
        registrar,
    ):
        task = self.create_task()
        previous = snapshot_tarea(task)

        task.asignados.add(
            self.assigned
        )

        task.save()

        registrar_cambio_tarea(
            tarea=task,
            actor=self.actor,
            anterior=previous,
            diferir_hasta_commit=False,
        )

        kwargs = registrar.call_args.kwargs

        self.assertEqual(
            kwargs["accion"],
            "reasignar_tarea",
        )

        self.assertIn(
            self.assigned.pk,
            kwargs["metadata"][
                "asignado_ids"
            ],
        )

    @patch(
        "tareas.activity.registrar_actividad"
    )
    def test_noop_does_not_register(
        self,
        registrar,
    ):
        task = self.create_task()
        previous = snapshot_tarea(task)

        result = registrar_cambio_tarea(
            tarea=task,
            actor=self.actor,
            anterior=previous,
            diferir_hasta_commit=False,
        )

        self.assertIsNone(result)
        registrar.assert_not_called()


class TaskActivityIdempotencyTests(
    TestCase
):
    def setUp(self):
        self.actor = User.objects.create_user(
            username="task_idempotent_actor",
        )

        self.team = Team.objects.create(
            name="Task Idempotent Team",
        )

        self.actor.teams.add(self.team)

        self.task = Tarea.objects.create(
            team=self.team,
            titulo="Tarea idempotente",
            creador=self.actor,
            visibilidad="depto",
        )

        self.task.asignados.add(
            self.actor
        )

    def test_create_is_idempotent(self):
        for _iteration in range(2):
            registrar_creacion_tarea(
                tarea=self.task,
                actor=self.actor,
                diferir_hasta_commit=False,
            )

        self.assertEqual(
            ActividadPlataforma.objects.count(),
            1,
        )

        activity = (
            ActividadPlataforma.objects.get()
        )

        self.assertEqual(
            activity.clave_idempotencia,
            f"tareas:crear:{self.task.pk}",
        )

    def test_direct_orm_create_has_no_signal(
        self,
    ):
        ActividadPlataforma.objects.all().delete()

        Tarea.objects.create(
            team=self.team,
            titulo="Creación ORM sin actividad",
            creador=self.actor,
        )

        self.assertEqual(
            ActividadPlataforma.objects.count(),
            0,
        )


@override_settings(
    SECURE_SSL_REDIRECT=False
)
class TaskActivityViewTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(
            name="Task View Activity Team",
        )

        self.creator = User.objects.create_user(
            username="task_view_creator",
            password="x",
        )

        self.assigned = User.objects.create_user(
            username="task_view_assigned",
            password="x",
        )

        self.member = User.objects.create_user(
            username="task_view_member",
            password="x",
        )

        self.creator.teams.add(self.team)
        self.assigned.teams.add(self.team)
        self.member.teams.add(self.team)

        self.client.force_login(
            self.creator
        )

        session = self.client.session

        session["active_team_id"] = str(
            self.team.pk
        )

        session[
            "_gestion_default_todas_empresas_user_id"
        ] = str(self.creator.pk)

        session.save()

    def payload(
        self,
        *,
        title="Actividad tarea",
        state="pendiente",
        visibility="privada",
        assigned=None,
        description="Descripción",
    ):
        data = {
            "titulo": title,
            "descripcion": description,
            "estado": state,
            "prioridad": "media",
            "etiquetas": "actividad",
            "visibilidad": visibility,
        }

        if assigned is not None:
            data["asignados"] = [
                user.pk
                for user in assigned
            ]

        return data

    def create_manual_task(
        self,
        *,
        visibility="privada",
    ):
        task = Tarea.objects.create(
            team=self.team,
            titulo="Tarea existente",
            descripcion="Descripción",
            estado="pendiente",
            prioridad="media",
            etiquetas="actividad",
            creador=self.creator,
            visibilidad=visibility,
        )

        task.asignados.add(
            self.creator
        )

        return task

    def test_create_view_registers_activity(
        self,
    ):
        with self.captureOnCommitCallbacks(
            execute=True
        ):
            response = self.client.post(
                reverse("tareas:create"),
                data=self.payload(),
            )

        self.assertEqual(
            response.status_code,
            302,
        )

        activity = (
            ActividadPlataforma
            .objects.get()
        )

        task = Tarea.objects.get(
            titulo="Actividad tarea"
        )

        self.assertEqual(
            activity.accion,
            "crear_tarea",
        )

        self.assertEqual(
            activity.objeto_id,
            task.pk,
        )

        self.assertEqual(
            activity.team,
            self.team,
        )

        self.assertEqual(
            activity.actor,
            self.creator,
        )

        self.assertEqual(
            activity.visibilidad,
            (
                ActividadPlataforma
                .Visibilidad
                .ACTOR
            ),
        )

    def test_department_activity_reaches_dashboard(
        self,
    ):
        with self.captureOnCommitCallbacks(
            execute=True
        ):
            response = self.client.post(
                reverse("tareas:create"),
                data=self.payload(
                    title="Tarea de equipo",
                    visibility="depto",
                ),
            )

        self.assertEqual(
            response.status_code,
            302,
        )

        activity = (
            ActividadPlataforma
            .objects.get()
        )

        self.assertEqual(
            activity.visibilidad,
            (
                ActividadPlataforma
                .Visibilidad
                .EQUIPO
            ),
        )

        request = SimpleNamespace(
            user=self.member,
            session={
                "active_team_id": str(
                    self.team.pk
                ),
            },
            GET={},
        )

        context = (
            _dashboard_activity_context(
                request
            )
        )

        items = [
            item
            for group in context[
                "actividad_grupos"
            ]
            for item in group["items"]
        ]

        self.assertEqual(
            [item.pk for item in items],
            [activity.pk],
        )

        self.assertEqual(
            items[0].modulo_label,
            "Tareas",
        )

        self.assertIn(
            "Tarea de equipo",
            items[0].descripcion,
        )

    def test_private_activity_not_visible_to_member(
        self,
    ):
        with self.captureOnCommitCallbacks(
            execute=True
        ):
            self.client.post(
                reverse("tareas:create"),
                data=self.payload(
                    title="Tarea privada",
                    visibility="privada",
                ),
            )

        visible_ids = set(
            actividad_visible_para_usuario(
                user=self.member,
                active_team_id=self.team.pk,
            )
            .values_list(
                "pk",
                flat=True,
            )
        )

        self.assertEqual(
            visible_ids,
            set(),
        )

    def test_completion_view_registers_one_activity(
        self,
    ):
        task = self.create_manual_task()

        with self.captureOnCommitCallbacks(
            execute=True
        ):
            response = self.client.post(
                reverse(
                    "tareas:update",
                    args=[task.pk],
                ),
                data=self.payload(
                    title=task.titulo,
                    state="hecha",
                    assigned=[
                        self.creator,
                    ],
                ),
            )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.assertEqual(
            ActividadPlataforma.objects.count(),
            1,
        )

        activity = (
            ActividadPlataforma
            .objects.get()
        )

        self.assertEqual(
            activity.accion,
            "completar_tarea",
        )

    def test_assignment_view_registers_one_activity(
        self,
    ):
        task = self.create_manual_task()

        with self.captureOnCommitCallbacks(
            execute=True
        ):
            response = self.client.post(
                reverse(
                    "tareas:update",
                    args=[task.pk],
                ),
                data=self.payload(
                    title=task.titulo,
                    assigned=[
                        self.creator,
                        self.assigned,
                    ],
                ),
            )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.assertEqual(
            ActividadPlataforma.objects.count(),
            1,
        )

        activity = (
            ActividadPlataforma
            .objects.get()
        )

        self.assertEqual(
            activity.accion,
            "reasignar_tarea",
        )

    def test_noop_view_creates_no_activity(
        self,
    ):
        task = self.create_manual_task()

        with self.captureOnCommitCallbacks(
            execute=True
        ):
            response = self.client.post(
                reverse(
                    "tareas:update",
                    args=[task.pk],
                ),
                data=self.payload(
                    title=task.titulo,
                    assigned=[
                        self.creator,
                    ],
                ),
            )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.assertEqual(
            ActividadPlataforma.objects.count(),
            0,
        )
