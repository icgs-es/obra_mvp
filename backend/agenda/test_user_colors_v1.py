from pathlib import Path
from types import SimpleNamespace

from django.test import SimpleTestCase

from agenda.user_colors import (
    FALLBACK_COLOR,
    contrast_text_color,
    event_color_payload,
    event_identity_payload,
    normalize_color,
)


class AgendaUserColorsPresentationTests(SimpleTestCase):
    def test_color_normalization_and_fallback(self):
        self.assertEqual(normalize_color("#a32e19"), "#A32E19")
        self.assertEqual(normalize_color("incorrecto"), FALLBACK_COLOR)

    def test_automatic_contrast(self):
        self.assertEqual(contrast_text_color("#FFFFFF"), "#111827")
        self.assertEqual(contrast_text_color("#000000"), "#FFFFFF")

    def test_owner_color_and_visibility_are_independent(self):
        event = SimpleNamespace(created_by_id=7, visibility="GLOBAL")
        user_map = {7: {"name": "Ivan", "color": "#a32e19"}}
        visual = event_color_payload(event, user_map)
        identity = event_identity_payload(event, user_map)

        self.assertEqual(visual["backgroundColor"], "#A32E19")
        self.assertEqual(visual["borderColor"], "#A32E19")
        self.assertIn(visual["textColor"], {"#FFFFFF", "#111827"})
        self.assertEqual(identity["owner_name"], "Ivan")
        self.assertEqual(identity["visibility_label"], "Global")
        self.assertEqual(identity["visibility_icon"], "🌐")

    def test_fullcalendar_behaviour_is_preserved(self):
        template = (
            Path(__file__).resolve().parent
            / "templates"
            / "agenda"
            / "calendar.html"
        ).read_text(encoding="utf-8")

        self.assertIn("AGENDA_USER_COLORS_V1_3", template)
        self.assertIn("editable: true", template)
        self.assertIn("eventClick:", template)
        self.assertIn("eventDrop: patchEventTime", template)
        self.assertIn("eventResize: patchEventTime", template)
        self.assertIn("eventsSet:", template)
        self.assertNotIn("background-color: #2563eb", template)
        self.assertNotIn("background-color: #16a34a", template)
        self.assertNotIn("background-color: #f97316", template)

    def test_event_card_visual_contract_is_clean_and_accessible(self):
        template = (
            Path(__file__).resolve().parent
            / "templates"
            / "agenda"
            / "calendar.html"
        ).read_text(encoding="utf-8")

        self.assertIn('font-family: Inter, "Segoe UI", system-ui', template)
        self.assertIn("font-weight: 500", template)
        self.assertIn("font-weight: 400", template)
        self.assertIn("-webkit-line-clamp: 2", template)
        self.assertIn("agenda-state-completed", template)
        self.assertIn("agenda-state-overdue", template)
        self.assertIn("agenda-state-cancelled", template)
        self.assertIn('right: "dayGridMonth,timeGridWeek,timeGridDay,listWeek"', template)
        self.assertIn("@media (max-width: 640px)", template)
        self.assertIn("border-left: 3px solid #dc3545", template)
        self.assertIn("text-decoration: line-through", template)
        self.assertIn('aria-label="Visibilidad:', template)
        self.assertIn('data-agenda-item-type', template)
        self.assertIn("escapeHtml(title)", template)
        self.assertNotIn("agenda-pill", template)
        self.assertNotIn('return "Priv."', template)
        self.assertNotIn("font-weight: 800;\n    overflow", template)
