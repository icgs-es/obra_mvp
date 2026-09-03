from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from usuarios.models import Team

from .models import ActividadPlataforma
from .selectors import (
    actividad_visible_para_usuario,
    modulos_visibles_para_usuario,
)


class ActividadVisibilidadTests(TestCase):
    def setUp(self):
        User = get_user_model()

        self.ivan = User.objects.create_user(
            username="ivan_selector",
            password="test",
        )

        self.companero = User.objects.create_user(
            username="companero_selector",
            password="test",
        )

        self.externo = User.objects.create_user(
            username="externo_selector",
            password="test",
        )

        self.admin = User.objects.create_superuser(
            username="admin_selector",
            email="admin@example.com",
            password="test",
        )

        self.team_1 = Team.objects.create(
            name="Empresa uno",
        )

        self.team_2 = Team.objects.create(
            name="Empresa dos",
        )

        self.team_1.members.add(
            self.ivan,
            self.companero,
        )

        self.team_2.members.add(self.externo)

        ahora = timezone.now()

        self.actividad_equipo = (
            ActividadPlataforma.objects.create(
                team=self.team_1,
                actor=self.companero,
                modulo="ARCHIVOS",
                accion="SUBIR",
                objeto_repr="video.mp4",
                visibilidad=(
                    ActividadPlataforma.Visibilidad.EQUIPO
                ),
                ocurrida_en=ahora,
            )
        )

        self.actividad_actor = (
            ActividadPlataforma.objects.create(
                team=self.team_1,
                actor=self.ivan,
                modulo="TAREAS",
                accion="CREAR",
                objeto_repr="Tarea privada",
                visibilidad=(
                    ActividadPlataforma.Visibilidad.ACTOR
                ),
                ocurrida_en=ahora - timedelta(minutes=1),
            )
        )

        self.actividad_objeto_ajeno = (
            ActividadPlataforma.objects.create(
                team=self.team_1,
                actor=self.companero,
                modulo="AGENDA",
                accion="CREAR",
                objeto_repr="Evento privado",
                visibilidad=(
                    ActividadPlataforma.Visibilidad.OBJETO
                ),
                ocurrida_en=ahora - timedelta(minutes=2),
            )
        )

        self.actividad_otro_team = (
            ActividadPlataforma.objects.create(
                team=self.team_2,
                actor=self.externo,
                modulo="GESTION",
                accion="CREAR",
                objeto_repr="Factura externa",
                visibilidad=(
                    ActividadPlataforma.Visibilidad.EQUIPO
                ),
                ocurrida_en=ahora - timedelta(minutes=3),
            )
        )

        self.actividad_oculta = (
            ActividadPlataforma.objects.create(
                team=self.team_1,
                actor=self.ivan,
                modulo="SISTEMA",
                accion="INTERNO",
                visible_en_dashboard=False,
                ocurrida_en=ahora - timedelta(minutes=4),
            )
        )

    def ids_para(self, user, **kwargs):
        return set(
            actividad_visible_para_usuario(
                user=user,
                **kwargs,
            ).values_list("id", flat=True)
        )

    def test_usuario_ve_actividad_de_su_equipo(self):
        ids = self.ids_para(self.ivan)

        self.assertIn(
            self.actividad_equipo.id,
            ids,
        )

        self.assertNotIn(
            self.actividad_otro_team.id,
            ids,
        )

    def test_actividad_actor_es_privada(self):
        ids_companero = self.ids_para(self.companero)
        ids_ivan = self.ids_para(self.ivan)

        self.assertNotIn(
            self.actividad_actor.id,
            ids_companero,
        )

        self.assertIn(
            self.actividad_actor.id,
            ids_ivan,
        )

    def test_visibilidad_objeto_es_conservadora(self):
        ids_ivan = self.ids_para(self.ivan)
        ids_companero = self.ids_para(self.companero)

        self.assertNotIn(
            self.actividad_objeto_ajeno.id,
            ids_ivan,
        )

        self.assertIn(
            self.actividad_objeto_ajeno.id,
            ids_companero,
        )

    def test_filtro_empresa_seleccionada(self):
        ids = self.ids_para(
            self.ivan,
            active_team_id=self.team_1.id,
        )

        self.assertIn(
            self.actividad_equipo.id,
            ids,
        )

        self.assertNotIn(
            self.actividad_otro_team.id,
            ids,
        )

    def test_rechaza_empresa_no_permitida(self):
        ids = self.ids_para(
            self.ivan,
            active_team_id=self.team_2.id,
        )

        self.assertEqual(ids, set())

    def test_alcance_mi_actividad(self):
        ids = self.ids_para(
            self.ivan,
            alcance="mi",
        )

        self.assertIn(
            self.actividad_actor.id,
            ids,
        )

        self.assertNotIn(
            self.actividad_equipo.id,
            ids,
        )

    def test_no_muestra_actividad_oculta(self):
        ids = self.ids_para(self.ivan)

        self.assertNotIn(
            self.actividad_oculta.id,
            ids,
        )

    def test_filtro_por_modulo(self):
        ids = self.ids_para(
            self.ivan,
            modulo="archivos",
        )

        self.assertEqual(
            ids,
            {self.actividad_equipo.id},
        )

    def test_superusuario_puede_ver_todo_visible(self):
        ids = self.ids_para(self.admin)

        self.assertIn(
            self.actividad_equipo.id,
            ids,
        )
        self.assertIn(
            self.actividad_actor.id,
            ids,
        )
        self.assertIn(
            self.actividad_objeto_ajeno.id,
            ids,
        )
        self.assertIn(
            self.actividad_otro_team.id,
            ids,
        )
        self.assertNotIn(
            self.actividad_oculta.id,
            ids,
        )

    def test_lista_modulos_visibles(self):
        modulos = modulos_visibles_para_usuario(
            user=self.ivan,
        )

        self.assertEqual(
            modulos,
            ["ARCHIVOS", "TAREAS"],
        )
