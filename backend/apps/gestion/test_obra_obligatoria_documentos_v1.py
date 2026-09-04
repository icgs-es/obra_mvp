from django.test import TestCase

from usuarios.models import Team
from planificacion_obra.models import (
    ObraPlanificacion,
)

from apps.gestion.forms import (
    AlbaranProveedorForm,
    FacturaProveedorForm,
)


class DocumentoObraObligatoriaTests(TestCase):

    def setUp(self):
        self.catalog_team = (
            Team.objects.create(
                name="INVERADRIDE",
            )
        )

        self.document_team = (
            Team.objects.create(
                name="EMPRESA DOCUMENTO TEST",
            )
        )

        self.altoveloo = (
            ObraPlanificacion.objects.create(
                team=self.catalog_team,
                legacy_cod_obra=2,
                codigo="2",
                nombre="ALTOVELOO",
            )
        )

        self.competa = (
            ObraPlanificacion.objects.create(
                team=self.catalog_team,
                legacy_cod_obra=3,
                codigo="3",
                nombre="OBRA COMPETA",
            )
        )

        foreign_team = Team.objects.create(
            name="EMPRESA EXTERNA TEST",
        )

        self.foreign_obra = (
            ObraPlanificacion.objects.create(
                team=foreign_team,
                legacy_cod_obra=99,
                codigo="99",
                nombre="OBRA EXTERNA",
            )
        )

        self.team_scope = (
            Team.objects.all()
        )

    def factura(self, data=None):
        return FacturaProveedorForm(
            data=data,
            team=self.document_team,
            team_scope=self.team_scope,
            ambito_gestion=(
                (data or {}).get(
                    "ambito_gestion",
                    "OBRA",
                )
            ),
            can_manage_retention=True,
        )

    def albaran(self, data=None):
        return AlbaranProveedorForm(
            data=data,
            team=self.document_team,
            team_scope=self.team_scope,
            ambito_gestion=(
                (data or {}).get(
                    "ambito_gestion",
                    "OBRA",
                )
            ),
        )

    def test_altoveloo_default_en_ambos(self):
        for form in (
            self.factura(),
            self.albaran(),
        ):
            field = form.fields[
                "obra_planificacion"
            ]

            self.assertEqual(
                field.initial,
                self.altoveloo.pk,
            )

            self.assertEqual(
                field.label_from_instance(
                    self.altoveloo
                ),
                "2 · ALTOVELOO",
            )

    def test_catalogo_corporativo(self):
        form = self.factura()

        ids = set(
            form.fields[
                "obra_planificacion"
            ]
            .queryset
            .values_list(
                "pk",
                flat=True,
            )
        )

        self.assertIn(
            self.altoveloo.pk,
            ids,
        )

        self.assertIn(
            self.competa.pk,
            ids,
        )

        self.assertNotIn(
            self.foreign_obra.pk,
            ids,
        )

    def test_obra_obligatoria_si_ambito_obra(self):
        for factory in (
            self.factura,
            self.albaran,
        ):
            form = factory({
                "ambito_gestion": "OBRA",
                "obra_planificacion": "",
            })

            form.is_valid()

            self.assertIn(
                "obra_planificacion",
                form.errors,
            )

            self.assertIn(
                "Debes seleccionar la obra",
                str(
                    form.errors[
                        "obra_planificacion"
                    ]
                ),
            )

    def test_obra_seleccionada_es_fuente_verdad(self):
        for factory in (
            self.factura,
            self.albaran,
        ):
            form = factory({
                "ambito_gestion": "OBRA",
                "obra_planificacion": str(
                    self.competa.pk
                ),
            })

            form.is_valid()

            self.assertEqual(
                form.instance.obra_planificacion_id,
                self.competa.pk,
            )

            self.assertEqual(
                str(
                    form.instance.cod_obra_legacy
                ),
                "3",
            )

    def test_obra_fuera_catalogo_rechazada(self):
        for factory in (
            self.factura,
            self.albaran,
        ):
            form = factory({
                "ambito_gestion": "OBRA",
                "obra_planificacion": str(
                    self.foreign_obra.pk
                ),
            })

            form.is_valid()

            self.assertIn(
                "obra_planificacion",
                form.errors,
            )

    def test_ambito_no_obra_limpia_obra(self):
        probe = self.factura()

        non_obra = next(
            str(value)
            for value, _label
            in probe.fields[
                "ambito_gestion"
            ].choices
            if value
            and str(value).upper()
            != "OBRA"
        )

        for factory in (
            self.factura,
            self.albaran,
        ):
            form = factory({
                "ambito_gestion": non_obra,
                "obra_planificacion": str(
                    self.altoveloo.pk
                ),
            })

            form.instance.obra_planificacion = (
                self.altoveloo
            )

            form.is_valid()

            self.assertIsNone(
                form.instance.obra_planificacion_id
            )
