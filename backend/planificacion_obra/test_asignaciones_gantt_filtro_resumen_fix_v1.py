from django.contrib.auth import get_user_model
from django.test import TestCase


class AsignacionesGanttFiltroResumenFixV1Tests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_superuser(
            username="gantt_filter_summary_fix_test",
            email="gantt-filter-summary@example.com",
            password="test-pass-123",
        )
        self.client.force_login(self.user)

    def test_asignaciones_list_is_healthy(self):
        response = self.client.get(
            "/app/planificacion-obra/asignaciones/",
            secure=True,
        )
        self.assertEqual(response.status_code, 200)

    def test_asignaciones_gantt_is_healthy(self):
        response = self.client.get(
            "/app/planificacion-obra/asignaciones/gantt/",
            secure=True,
        )
        self.assertEqual(response.status_code, 200)

    def test_asignaciones_gantt_with_filters_is_healthy(self):
        response = self.client.get(
            "/app/planificacion-obra/asignaciones/gantt/",
            {
                "desde": "2026-07-24",
                "hasta": "2026-08-14",
                "estado": "PENDIENTE",
                "agrupacion": "asignacion",
            },
            secure=True,
        )
        self.assertEqual(response.status_code, 200)
