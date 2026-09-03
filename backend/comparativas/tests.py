import tempfile
import uuid

from django.contrib.auth.models import (
    Permission,
    User,
)
from django.core.files.uploadedfile import (
    SimpleUploadedFile,
)
from django.db import models
from django.test import (
    TestCase,
    override_settings,
)
from django.urls import reverse

from usuarios.models import Team

from .models import (
    Comparativa,
    DocumentoComparativa,
    Ofertante,
)
from .services import (
    crear_oferta,
    guardar_documento,
)


def create_team(name):
    payload = {}

    for field in Team._meta.fields:
        if (
            field.primary_key
            or field.auto_created
        ):
            continue

        if field.name == "name":
            payload[field.name] = name
            continue

        if (
            field.has_default()
            or field.null
            or field.blank
        ):
            continue

        if isinstance(
            field,
            (
                models.CharField,
                models.TextField,
                models.SlugField,
            ),
        ):
            payload[field.name] = (
                f"{field.name}-"
                f"{uuid.uuid4().hex[:10]}"
            )
            continue

        if isinstance(
            field,
            models.BooleanField,
        ):
            payload[field.name] = False
            continue

        if isinstance(
            field,
            models.IntegerField,
        ):
            payload[field.name] = 1
            continue

        raise AssertionError(
            "Campo obligatorio Team "
            f"no soportado en test: {field.name}"
        )

    return Team.objects.create(**payload)


class ComparativasV1Tests(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.override = override_settings(
            MEDIA_ROOT=self.tmp.name
        )
        self.override.enable()

        self.user = User.objects.create_user(
            username="cmp-user",
            password="secret123",
        )

        self.team = create_team("Empresa A")

        self.user.teams.add(self.team)

        permission = Permission.objects.get(
            codename="access_gestion",
            content_type__app_label="gestion",
        )
        self.user.user_permissions.add(permission)

        self.client.force_login(self.user)

        session = self.client.session
        session["active_team_id"] = str(
            self.team.pk
        )
        session.save()

    def tearDown(self):
        self.override.disable()
        self.tmp.cleanup()

    def test_create_comparativa_http(self):
        response = self.client.post(
            reverse("comparativas:create"),
            {
                "team": self.team.pk,
                "titulo": "Fontanería Los Herreros",
                "categoria": "Fontanería",
                "estado": "BORRADOR",
                "descripcion": (
                    "Comparar alcance completo."
                ),
                "obra_ref": "",
            },
            secure=True,
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.assertTrue(
            Comparativa.objects.filter(
                titulo=(
                    "Fontanería Los Herreros"
                )
            ).exists()
        )

    def test_scope_no_muestra_otro_team(self):
        other_team = create_team("Empresa B")

        visible = Comparativa.objects.create(
            team=self.team,
            titulo="Visible",
            creado_por=self.user,
        )

        Comparativa.objects.create(
            team=other_team,
            titulo="Oculta",
            creado_por=self.user,
        )

        response = self.client.get(
            reverse("comparativas:list"),
            secure=True,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            visible.titulo,
        )

        self.assertNotContains(
            response,
            "Oculta",
        )

    def test_versiones_son_incrementales(self):
        comparativa = Comparativa.objects.create(
            team=self.team,
            titulo="Comparativa",
            creado_por=self.user,
        )

        ofertante = Ofertante.objects.create(
            comparativa=comparativa,
            nombre="Proveedor candidato",
        )

        oferta1 = crear_oferta(
            ofertante=ofertante,
            cleaned_data={},
            user=self.user,
        )

        oferta2 = crear_oferta(
            ofertante=ofertante,
            cleaned_data={},
            user=self.user,
        )

        self.assertEqual(
            oferta1.version,
            1,
        )
        self.assertEqual(
            oferta2.version,
            2,
        )

        comparativa.refresh_from_db()

        self.assertEqual(
            comparativa.estado,
            Comparativa.Estado.EN_COMPARACION,
        )

    def test_documento_jpg_se_guarda_y_hashea(self):
        comparativa = Comparativa.objects.create(
            team=self.team,
            titulo="Comparativa",
            creado_por=self.user,
        )

        ofertante = Ofertante.objects.create(
            comparativa=comparativa,
            nombre="José Fontanería",
        )

        oferta = crear_oferta(
            ofertante=ofertante,
            cleaned_data={},
            user=self.user,
        )

        uploaded = SimpleUploadedFile(
            "presupuesto.jpg",
            b"contenido-imagen-prueba",
            content_type="image/jpeg",
        )

        documento, created = guardar_documento(
            oferta=oferta,
            uploaded_file=uploaded,
            user=self.user,
        )

        self.assertTrue(created)
        self.assertEqual(
            documento.extension,
            ".jpg",
        )
        self.assertEqual(
            len(documento.sha256),
            64,
        )
        self.assertEqual(
            documento.estado_analisis,
            DocumentoComparativa
            .EstadoAnalisis
            .PENDIENTE,
        )

    def test_documento_duplicado_no_duplica(self):
        comparativa = Comparativa.objects.create(
            team=self.team,
            titulo="Comparativa",
            creado_por=self.user,
        )

        ofertante = Ofertante.objects.create(
            comparativa=comparativa,
            nombre="Proveedor",
        )

        oferta = crear_oferta(
            ofertante=ofertante,
            cleaned_data={},
            user=self.user,
        )

        file1 = SimpleUploadedFile(
            "uno.pdf",
            b"mismo-contenido",
            content_type="application/pdf",
        )

        first, created1 = guardar_documento(
            oferta=oferta,
            uploaded_file=file1,
            user=self.user,
        )

        file2 = SimpleUploadedFile(
            "dos.pdf",
            b"mismo-contenido",
            content_type="application/pdf",
        )

        second, created2 = guardar_documento(
            oferta=oferta,
            uploaded_file=file2,
            user=self.user,
        )

        self.assertTrue(created1)
        self.assertFalse(created2)
        self.assertEqual(
            first.pk,
            second.pk,
        )
        self.assertEqual(
            DocumentoComparativa.objects.count(),
            1,
        )


    # COMPARATIVAS_MULTIEMPRESA_OBRA_SELECTOR_V1

    def test_all_mode_does_not_assume_company(self):
        from planificacion_obra.models import (
            ObraPlanificacion,
        )

        other_team = create_team(
            "Empresa secundaria"
        )

        self.user.teams.add(other_team)

        obra_team_a = (
            ObraPlanificacion.objects.create(
                team=self.team,
                legacy_cod_obra=987653,
                codigo="CMP-A",
                nombre="Obra Empresa A",
            )
        )

        obra_team_b = (
            ObraPlanificacion.objects.create(
                team=other_team,
                legacy_cod_obra=987654,
                codigo="CMP-B",
                nombre="Obra Empresa B",
            )
        )

        session = self.client.session
        session["active_team_id"] = "all"
        session.save()

        response = self.client.get(
            reverse("comparativas:create"),
            secure=True,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        form = response.context["form"]

        self.assertEqual(
            form.fields["team"].empty_label,
            "Selecciona empresa",
        )

        self.assertIsNone(
            form["team"].value()
        )

        self.assertContains(
            response,
            "Selecciona primero una empresa",
        )

        self.assertContains(
            response,
            (
                'data-team-id="'
                f'{self.team.pk}'
                '"'
            ),
        )

        self.assertContains(
            response,
            (
                'data-team-id="'
                f'{other_team.pk}'
                '"'
            ),
        )

        self.assertContains(
            response,
            obra_team_a.nombre,
        )

        self.assertContains(
            response,
            obra_team_b.nombre,
        )


    def test_cross_team_obra_is_rejected_server_side(self):
        from planificacion_obra.models import (
            ObraPlanificacion,
        )

        other_team = create_team(
            "Empresa externa"
        )

        self.user.teams.add(other_team)

        foreign_obra = (
            ObraPlanificacion.objects.create(
                team=other_team,
                legacy_cod_obra=987651,
                codigo="CMP-EXT",
                nombre="Obra otra empresa",
            )
        )

        response = self.client.post(
            reverse("comparativas:create"),
            {
                "team": self.team.pk,
                "titulo": "Comparativa inválida",
                "categoria": "Fontanería",
                "estado": "BORRADOR",
                "descripcion": (
                    "Prueba aislamiento."
                ),
                "obra_ref": foreign_obra.pk,
            },
            secure=True,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        form = response.context["form"]

        self.assertIn(
            "obra_ref",
            form.errors,
        )

        self.assertFalse(
            Comparativa.objects.filter(
                titulo="Comparativa inválida"
            ).exists()
        )


    def test_matching_team_obra_is_saved(self):
        from planificacion_obra.models import (
            ObraPlanificacion,
        )

        obra = (
            ObraPlanificacion.objects.create(
                team=self.team,
                legacy_cod_obra=987652,
                codigo="CMP-OK",
                nombre="Obra empresa correcta",
            )
        )

        response = self.client.post(
            reverse("comparativas:create"),
            {
                "team": self.team.pk,
                "titulo": "Comparativa con obra",
                "categoria": "Fontanería",
                "estado": "BORRADOR",
                "descripcion": (
                    "Prueba vinculación."
                ),
                "obra_ref": obra.pk,
            },
            secure=True,
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        comparativa = (
            Comparativa.objects.get(
                titulo="Comparativa con obra"
            )
        )

        self.assertEqual(
            comparativa.team_id,
            self.team.pk,
        )

        self.assertEqual(
            comparativa.referencia_id,
            str(obra.pk),
        )

        self.assertEqual(
            comparativa.referencia_codigo,
            "CMP-OK",
        )

        self.assertEqual(
            comparativa.referencia_nombre,
            "Obra empresa correcta",
        )


    # COMPARATIVAS_EDITAR_EXPEDIENTE_V1

    def test_edit_get_preserves_team_and_obra(self):
        from planificacion_obra.models import (
            ObraPlanificacion,
        )

        obra = ObraPlanificacion.objects.create(
            team=self.team,
            legacy_cod_obra=987655,
            codigo="CMP-EDIT",
            nombre="Obra edición",
        )

        comparativa = Comparativa.objects.create(
            team=self.team,
            titulo="Comparativa editable",
            categoria="Fontanería",
            descripcion="Alcance original.",
            referencia_tipo=(
                "planificacion_obra."
                "ObraPlanificacion"
            ),
            referencia_id=str(obra.pk),
            referencia_codigo=obra.codigo,
            referencia_nombre=obra.nombre,
            creado_por=self.user,
        )

        response = self.client.get(
            reverse(
                "comparativas:update",
                kwargs={
                    "uid": comparativa.uuid,
                },
            ),
            secure=True,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        form = response.context["form"]

        self.assertEqual(
            str(form["team"].value()),
            str(self.team.pk),
        )

        self.assertEqual(
            str(form["obra_ref"].value()),
            str(obra.pk),
        )

        self.assertContains(
            response,
            "Editar comparativa",
        )

        self.assertContains(
            response,
            "Guardar cambios",
        )


    def test_edit_updates_scope_and_reference(self):
        from planificacion_obra.models import (
            ObraPlanificacion,
        )

        obra = ObraPlanificacion.objects.create(
            team=self.team,
            legacy_cod_obra=987656,
            codigo="CMP-NUEVA",
            nombre="Nueva obra vinculada",
        )

        comparativa = Comparativa.objects.create(
            team=self.team,
            titulo="Antes",
            categoria="Inicial",
            descripcion="Antes.",
            creado_por=self.user,
        )

        response = self.client.post(
            reverse(
                "comparativas:update",
                kwargs={
                    "uid": comparativa.uuid,
                },
            ),
            {
                "team": self.team.pk,
                "titulo": "Después",
                "categoria": "Fontanería",
                "estado": "BORRADOR",
                "descripcion": (
                    "Alcance actualizado."
                ),
                "obra_ref": obra.pk,
            },
            secure=True,
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        comparativa.refresh_from_db()

        self.assertEqual(
            comparativa.titulo,
            "Después",
        )

        self.assertEqual(
            comparativa.categoria,
            "Fontanería",
        )

        self.assertEqual(
            comparativa.descripcion,
            "Alcance actualizado.",
        )

        self.assertEqual(
            comparativa.referencia_id,
            str(obra.pk),
        )

        self.assertEqual(
            comparativa.referencia_codigo,
            "CMP-NUEVA",
        )

        self.assertEqual(
            comparativa.referencia_nombre,
            "Nueva obra vinculada",
        )


    def test_edit_rejects_cross_team_obra(self):
        from planificacion_obra.models import (
            ObraPlanificacion,
        )

        other_team = create_team(
            "Empresa edición externa"
        )

        self.user.teams.add(
            other_team
        )

        foreign_obra = (
            ObraPlanificacion.objects.create(
                team=other_team,
                legacy_cod_obra=987657,
                codigo="CMP-EDIT-EXT",
                nombre="Obra externa",
            )
        )

        comparativa = Comparativa.objects.create(
            team=self.team,
            titulo="No modificar",
            descripcion="Original.",
            creado_por=self.user,
        )

        session = self.client.session
        session["active_team_id"] = "all"
        session.save()

        response = self.client.post(
            reverse(
                "comparativas:update",
                kwargs={
                    "uid": comparativa.uuid,
                },
            ),
            {
                "team": self.team.pk,
                "titulo": "Intento inválido",
                "categoria": "Fontanería",
                "estado": "BORRADOR",
                "descripcion": "Intento.",
                "obra_ref": foreign_obra.pk,
            },
            secure=True,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertIn(
            "obra_ref",
            response.context[
                "form"
            ].errors,
        )

        comparativa.refresh_from_db()

        self.assertEqual(
            comparativa.titulo,
            "No modificar",
        )

        self.assertEqual(
            comparativa.descripcion,
            "Original.",
        )


    def test_edit_cannot_change_team_after_bidder(self):
        other_team = create_team(
            "Empresa destino"
        )

        self.user.teams.add(
            other_team
        )

        comparativa = Comparativa.objects.create(
            team=self.team,
            titulo="Expediente estable",
            creado_por=self.user,
        )

        Ofertante.objects.create(
            comparativa=comparativa,
            nombre="Proveedor ya incorporado",
        )

        session = self.client.session
        session["active_team_id"] = "all"
        session.save()

        response = self.client.post(
            reverse(
                "comparativas:update",
                kwargs={
                    "uid": comparativa.uuid,
                },
            ),
            {
                "team": other_team.pk,
                "titulo": "Expediente estable",
                "categoria": "",
                "estado": "BORRADOR",
                "descripcion": "",
                "obra_ref": "",
            },
            secure=True,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertIn(
            "team",
            response.context[
                "form"
            ].errors,
        )

        comparativa.refresh_from_db()

        self.assertEqual(
            comparativa.team_id,
            self.team.pk,
        )


    # COMPARATIVAS_IMPORTACION_BASICA_PRESUPUESTO_V1

    def _create_provider_import_test(
        self,
        *,
        team,
        legacy,
        name,
        fiscal="",
        cif="",
    ):
        from apps.gestion.models import (
            Proveedor,
        )

        return Proveedor.objects.create(
            team=team,
            legacy_id_proveedor=legacy,
            nombre_comercial=name,
            nombre_fiscal=fiscal,
            direccion="",
            cod_postal="",
            poblacion="",
            provincia="",
            pais="",
            cif=cif,
            email="",
            telefono="",
            contacto_comercial="",
            tel_contacto_comercial="",
            contacto_admin="",
            tel_contacto_admin="",
            sp_iva=False,
            observaciones="",
            es_subcontrata=False,
            cod_obra_legacy="",
            fuera_listado=False,
            activo=True,
            raw_data={},
            ambito_gestion="",
        )


    def test_presupuesto_parser_detects_rayma_header(self):
        from .presupuesto_import import (
            analizar_texto_presupuesto,
        )

        text = """
        INSTALACIONES RAYMA, S.L.
        CIF B29707536
        Nº Presupuesto: A/2026/00102
        Fecha: 13/05/2026
        Base imponible 11.281,46 €
        IVA 2.369,11 €
        TOTAL 13.650,57 €
        """

        result = analizar_texto_presupuesto(
            text,
            [
                {
                    "id": 1006,
                    "team_id": self.team.pk,
                    "nombre_comercial": (
                        "INSTALACIONES RAYMA"
                    ),
                    "nombre_fiscal": (
                        "INSTALACIONES RAYMA S.L."
                    ),
                    "cif": "B29707536",
                }
            ],
        )

        detected = result["detected"]

        self.assertEqual(
            detected["numero_documento"],
            "A/2026/00102",
        )

        self.assertEqual(
            detected["fecha"],
            "2026-05-13",
        )

        self.assertEqual(
            detected["base_imponible"],
            "11281.46",
        )

        self.assertEqual(
            detected["iva"],
            "2369.11",
        )

        self.assertEqual(
            detected["total"],
            "13650.57",
        )

        self.assertEqual(
            result[
                "provider_matches"
            ][0]["id"],
            1006,
        )

        self.assertEqual(
            result[
                "provider_matches"
            ][0]["confidence"],
            "MUY_ALTA",
        )


    def test_presupuesto_parser_does_not_match_victor_substring(self):
        from .presupuesto_import import (
            analizar_texto_presupuesto,
        )

        result = analizar_texto_presupuesto(
            """
            CARLOS & VICTOR
            PRESUPUESTO FONTANERIA
            Fecha 14/08/2026
            TOTAL 6.252,40 €
            """,
            [
                {
                    "id": 1482,
                    "team_id": self.team.pk,
                    "nombre_comercial": (
                        "E.S RINCON VICTORIA"
                    ),
                    "nombre_fiscal": (
                        "REPSOL"
                    ),
                    "cif": "A8029883",
                }
            ],
        )

        self.assertEqual(
            result[
                "provider_matches"
            ],
            [],
        )


    def test_presupuesto_import_get(self):
        comparativa = Comparativa.objects.create(
            team=self.team,
            titulo="Importar presupuesto",
            creado_por=self.user,
        )

        response = self.client.get(
            reverse(
                "comparativas:presupuesto_import",
                kwargs={
                    "uid": comparativa.uuid,
                },
            ),
            secure=True,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "Importar presupuesto",
        )

        self.assertContains(
            response,
            "Leer presupuesto",
        )


    def test_presupuesto_upload_rejects_fake_pdf(self):
        from .forms import (
            PresupuestoImportUploadForm,
        )

        fake = SimpleUploadedFile(
            "fake.pdf",
            b"NO-ES-PDF",
            content_type="application/pdf",
        )

        form = PresupuestoImportUploadForm(
            files={
                "archivo": fake,
            }
        )

        self.assertFalse(
            form.is_valid()
        )

        self.assertIn(
            "archivo",
            form.errors,
        )


    def test_presupuesto_confirm_creates_candidate_offer_and_document(self):
        from .presupuesto_import import (
            save_staged_analysis,
            stage_presupuesto,
        )

        comparativa = Comparativa.objects.create(
            team=self.team,
            titulo="Carlos y Victor",
            creado_por=self.user,
        )

        uploaded = SimpleUploadedFile(
            "carlos.pdf",
            b"%PDF-1.4\nfixture",
            content_type="application/pdf",
        )

        staged = stage_presupuesto(
            uploaded_file=uploaded,
            user_id=self.user.pk,
            comparativa_uuid=(
                comparativa.uuid
            ),
        )

        analysis = {
            "ok": True,
            "method": "direct_text",
            "ocr_used": False,
            "error": "",
            "text": (
                "CARLOS & VICTOR "
                "TOTAL 6252,40"
            ),
            "text_len": 30,
            "confidence": "REVISAR",
            "provider_matches": [],
            "detected": {
                "proveedor_nombre": (
                    "CARLOS & VICTOR"
                ),
                "nif_cif_candidates": [],
                "numero_documento": "",
                "fecha": "2026-08-14",
                "base_imponible": "",
                "iva": "",
                "total": "6252.40",
            },
        }

        save_staged_analysis(
            staged,
            analysis,
        )

        response = self.client.post(
            reverse(
                "comparativas:presupuesto_import",
                kwargs={
                    "uid": comparativa.uuid,
                },
            ),
            {
                "action": "confirm",
                "token": staged["token"],
                "proveedor_ref": "",
                "nombre": "Carlos & Victor",
                "nif": "",
                "fecha_documento": (
                    "2026-08-14"
                ),
                "referencia": "",
                "base": "",
                "impuestos": "",
                "total": "6252.40",
                "observaciones": "",
            },
            secure=True,
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        ofertante = (
            Ofertante.objects.get(
                comparativa=comparativa
            )
        )

        self.assertEqual(
            ofertante.tipo,
            Ofertante.Tipo.CANDIDATO,
        )

        self.assertEqual(
            ofertante.nombre,
            "Carlos & Victor",
        )

        oferta = ofertante.ofertas.get()

        self.assertEqual(
            oferta.version,
            1,
        )

        self.assertEqual(
            str(oferta.total),
            "6252.40",
        )

        documento = (
            oferta.documentos.get()
        )

        self.assertEqual(
            documento.nombre_original,
            "carlos.pdf",
        )

        self.assertIn(
            "importacion_basica_presupuesto",
            documento.datos_extraidos,
        )


    def test_presupuesto_confirm_uses_existing_provider_same_team(self):
        from .presupuesto_import import (
            save_staged_analysis,
            stage_presupuesto,
        )

        proveedor = (
            self._create_provider_import_test(
                team=self.team,
                legacy=991001,
                name="INSTALACIONES RAYMA",
                fiscal=(
                    "INSTALACIONES RAYMA S.L."
                ),
                cif="B29707536",
            )
        )

        comparativa = Comparativa.objects.create(
            team=self.team,
            titulo="RAYMA",
            creado_por=self.user,
        )

        uploaded = SimpleUploadedFile(
            "rayma.pdf",
            b"%PDF-1.4\nfixture",
            content_type="application/pdf",
        )

        staged = stage_presupuesto(
            uploaded_file=uploaded,
            user_id=self.user.pk,
            comparativa_uuid=(
                comparativa.uuid
            ),
        )

        save_staged_analysis(
            staged,
            {
                "ok": True,
                "method": "direct_text",
                "ocr_used": False,
                "error": "",
                "text": (
                    "INSTALACIONES RAYMA "
                    "B29707536"
                ),
                "text_len": 30,
                "confidence": "MUY_ALTA",
                "provider_matches": [],
                "detected": {},
            },
        )

        response = self.client.post(
            reverse(
                "comparativas:presupuesto_import",
                kwargs={
                    "uid": comparativa.uuid,
                },
            ),
            {
                "action": "confirm",
                "token": staged["token"],
                "proveedor_ref": (
                    proveedor.pk
                ),
                "nombre": "",
                "nif": "",
                "fecha_documento": "",
                "referencia": (
                    "A/2026/00102"
                ),
                "base": "11281.46",
                "impuestos": "2369.11",
                "total": "13650.57",
                "observaciones": "",
            },
            secure=True,
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        ofertante = (
            Ofertante.objects.get(
                comparativa=comparativa
            )
        )

        self.assertEqual(
            ofertante.tipo,
            Ofertante.Tipo.PROVEEDOR,
        )

        self.assertEqual(
            ofertante.proveedor_ref_id,
            proveedor.pk,
        )

        self.assertEqual(
            ofertante.ofertas.count(),
            1,
        )


    def test_manual_bidder_excludes_foreign_team_provider(self):
        other_team = create_team(
            "Empresa proveedor externa"
        )

        self.user.teams.add(
            other_team
        )

        foreign_provider = (
            self._create_provider_import_test(
                team=other_team,
                legacy=991002,
                name=(
                    "PROVEEDOR SOLO OTRA EMPRESA"
                ),
                cif="B12345678",
            )
        )

        comparativa = Comparativa.objects.create(
            team=self.team,
            titulo="Scope proveedor",
            creado_por=self.user,
        )

        session = self.client.session
        session["active_team_id"] = "all"
        session.save()

        response = self.client.get(
            reverse(
                "comparativas:ofertante_create",
                kwargs={
                    "uid": comparativa.uuid,
                },
            ),
            secure=True,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertNotContains(
            response,
            foreign_provider.nombre_comercial,
        )

        response = self.client.post(
            reverse(
                "comparativas:ofertante_create",
                kwargs={
                    "uid": comparativa.uuid,
                },
            ),
            {
                "proveedor_ref": (
                    foreign_provider.pk
                ),
                "nombre": "",
                "nif": "",
                "email": "",
                "telefono": "",
            },
            secure=True,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertFalse(
            Ofertante.objects.filter(
                comparativa=comparativa
            ).exists()
        )


    # COMPARATIVAS_PRESUPUESTO_HEADER_GENERIC_R3

    def test_presupuesto_parser_detects_carlos_victor_real_header(self):
        from .presupuesto_import import (
            analizar_texto_presupuesto,
        )

        text = """
        ESTUDIO
        Victor Calvo Juan
        D.N.I:11972603E
        C/ HUERTA Nº6
        Cp:49150 -MORALEJA DEL VINO-
        -ZAMORA-
        Tlf: 617 476 655 666 562 583
        Nº ESTUDIO Fecha Página
        INTASA
        LOS HERREROS 2
        AV PORTUGAL 20
        49015 ZAMORA
        ZAMORA
        2026-ES.60 5 de agosto de 2026 1 / 1

        Base imponible % IVA Importe IVA % Rec Importe Rec
        Total:
        6.252,40
        6.252,40 €
        """

        result = analizar_texto_presupuesto(
            text,
            [],
        )

        detected = result["detected"]

        self.assertEqual(
            detected["proveedor_nombre"],
            "Victor Calvo Juan",
        )

        self.assertIn(
            "11972603E",
            detected[
                "nif_cif_candidates"
            ],
        )

        self.assertEqual(
            detected["numero_documento"],
            "2026-ES.60",
        )

        self.assertEqual(
            detected["fecha"],
            "2026-08-05",
        )

        self.assertEqual(
            detected["base_imponible"],
            "6252.40",
        )

        self.assertEqual(
            detected["iva"],
            "",
        )

        self.assertEqual(
            detected["total"],
            "6252.40",
        )


    # COMPARATIVAS_PRESUPUESTO_DOCUMENT_PREVIEW_V1

    def test_presupuesto_staged_document_view_is_inline(self):
        from .presupuesto_import import (
            delete_staged_presupuesto,
            stage_presupuesto,
        )

        comparativa = Comparativa.objects.create(
            team=self.team,
            titulo="Visor presupuesto",
            creado_por=self.user,
        )

        content = (
            b"%PDF-1.4\n"
            b"TEST DOCUMENT PREVIEW\n"
        )

        uploaded = SimpleUploadedFile(
            "presupuesto-test.pdf",
            content,
            content_type="application/pdf",
        )

        staged = stage_presupuesto(
            uploaded_file=uploaded,
            user_id=self.user.pk,
            comparativa_uuid=(
                comparativa.uuid
            ),
        )

        try:
            response = self.client.get(
                reverse(
                    "comparativas:"
                    "presupuesto_import_document",
                    kwargs={
                        "uid": (
                            comparativa.uuid
                        ),
                    },
                ),
                {
                    "token": (
                        staged["token"]
                    ),
                },
                secure=True,
            )

            self.assertEqual(
                response.status_code,
                200,
            )

            self.assertEqual(
                response[
                    "Content-Type"
                ],
                "application/pdf",
            )

            self.assertIn(
                "inline",
                response[
                    "Content-Disposition"
                ],
            )

            self.assertIn(
                "presupuesto-test.pdf",
                response[
                    "Content-Disposition"
                ],
            )

            self.assertEqual(
                response[
                    "X-Content-Type-Options"
                ],
                "nosniff",
            )

            streamed = b"".join(
                response.streaming_content
            )

            self.assertEqual(
                streamed,
                content,
            )

        finally:
            delete_staged_presupuesto(
                staged
            )


    def test_presupuesto_staged_document_rejects_invalid_token(self):
        comparativa = Comparativa.objects.create(
            team=self.team,
            titulo="Token inválido",
            creado_por=self.user,
        )

        response = self.client.get(
            reverse(
                "comparativas:"
                "presupuesto_import_document",
                kwargs={
                    "uid": (
                        comparativa.uuid
                    ),
                },
            ),
            {
                "token": (
                    "token-invalido"
                ),
            },
            secure=True,
        )

        self.assertEqual(
            response.status_code,
            404,
        )


    # COMPARATIVAS_PRESUPUESTO_SUPPLIER_CLEAN_R6

    def test_presupuesto_parser_ignores_page_marker_and_detects_emilio_name(self):
        from .presupuesto_import import (
            analizar_texto_presupuesto,
        )

        text = """
        --- PAGE 1 ---
        EMILIO PEREZ FONSECA FECHA: 13/08/2026
        NIF: 51076158-N
        CALLE BAMBA ,15-B TEL: 649597039
        MADRIDANOS
        49157 ZAMORA
        PRESUPUESTO PARA:
        Calle Herreros 31. ZAMORA
        PROMOTOR OBRA INMOBILIARIA INTASA.
        DESCRIPCIONES: IMPORTES:
        REALIZAR TRABAJOS DE FONTANERIA
        SUBTOTAL: 6500,00 €
        21 % DE IVA: 1365,00 €
        TOTAL: 7865,00 €
        HOJA 1/2
        """

        result = analizar_texto_presupuesto(
            text,
            [],
        )

        detected = result["detected"]

        self.assertEqual(
            detected[
                "proveedor_nombre"
            ],
            "EMILIO PEREZ FONSECA",
        )

        self.assertNotEqual(
            detected[
                "proveedor_nombre"
            ],
            "--- PAGE 1 ---",
        )

        self.assertIn(
            "51076158N",
            detected[
                "nif_cif_candidates"
            ],
        )

        self.assertEqual(
            detected["fecha"],
            "2026-08-13",
        )

        self.assertEqual(
            detected[
                "numero_documento"
            ],
            "",
        )

        self.assertEqual(
            detected[
                "base_imponible"
            ],
            "6500.00",
        )

        self.assertEqual(
            detected["iva"],
            "1365.00",
        )

        self.assertEqual(
            detected["total"],
            "7865.00",
        )


    # COMPARATIVAS_PRESUPUESTO_IMAGE_MULTIPASS_R7

    def test_presupuesto_date_accepts_ocr_spaces(self):
        from .presupuesto_import import (
            analizar_texto_presupuesto,
        )

        result = analizar_texto_presupuesto(
            """
            PRESUPUESTO
            FECHA
            14 - 08 - 2026
            """,
            [],
        )

        self.assertEqual(
            result["detected"]["fecha"],
            "2026-08-14",
        )


    def test_presupuesto_footer_totals_require_math_consistency(self):
        from .presupuesto_import import (
            _find_footer_totals,
        )

        good = _find_footer_totals(
            """
            BASE IMPONIBLE IVA CUOTA IVA TOTAL
            6890,00 21 1446,90 8.336,90 €
            """
        )

        self.assertEqual(
            good["base"],
            "6890.00",
        )

        self.assertEqual(
            good["iva"],
            "1446.90",
        )

        self.assertEqual(
            good["total"],
            "8336.90",
        )

        degraded = _find_footer_totals(
            """
            BASE IMPONIBLE IVA CUOTA IVA TOTAL
            6890,00 146,90 8.336,90 €
            """
        )

        self.assertEqual(
            degraded["base"],
            "6890.00",
        )

        self.assertEqual(
            degraded["iva"],
            "",
        )

        self.assertEqual(
            degraded["total"],
            "8336.90",
        )


    def test_presupuesto_supplier_near_tax_id_beats_section_heading(self):
        from .presupuesto_import import (
            analizar_texto_presupuesto,
        )

        result = analizar_texto_presupuesto(
            """
            FONTANERIA - CALEFACCION - GAS
            JOSE ALFONSO LOZANO VICENTE
            N.I.F. 11943051-W
            FECHA 14-08-2026
            PRESUPUESTO
            """,
            [],
        )

        detected = result["detected"]

        self.assertEqual(
            detected[
                "proveedor_nombre"
            ],
            "JOSE ALFONSO LOZANO VICENTE",
        )

        self.assertIn(
            "11943051W",
            detected[
                "nif_cif_candidates"
            ],
        )

        self.assertEqual(
            detected["fecha"],
            "2026-08-14",
        )


    # COMPARATIVAS_PRESUPUESTO_OCR_IDENTITY_QUALITY_R8

    def test_ocr_quality_prefers_more_complete_supplier_identity(self):
        from .presupuesto_import import (
            _ocr_text_quality,
        )

        fragmented = """
        PRESUPUESTO
        LOZANO VICENTE
        JOSE ALFONSO
        N.I.F. 11943051-W
        FECHA 14 - 08 - 2026
        BASE IMPONIBLE
        CUOTA IVA
        TOTAL
        """

        complete = """
        PRESUPUESTO
        JOSE ALFONSO LOZANO VICENTE
        N.I.F. 11943051-W
        FECHA 14-08-2026
        BASE IMPONIBLE
        CUOTA IVA
        TOTAL
        """

        fragmented_quality = (
            _ocr_text_quality(
                fragmented
            )
        )

        complete_quality = (
            _ocr_text_quality(
                complete
            )
        )

        self.assertGreater(
            complete_quality,
            fragmented_quality,
        )


    # COMPARATIVAS_PRESUPUESTO_GENERIC_IDENTITY_TOTALS_R9

    def test_presupuesto_tax_id_accepts_common_separators(self):
        from .presupuesto_import import (
            _find_tax_ids,
        )

        self.assertEqual(
            _find_tax_ids(
                "CIF: B-29.707.536"
            ),
            ["B29707536"],
        )

        self.assertEqual(
            _find_tax_ids(
                "N.I.F. 11.943.051-W"
            ),
            ["11943051W"],
        )


    def test_presupuesto_contact_line_is_not_supplier_name(self):
        from .presupuesto_import import (
            _plausible_name_line,
        )

        self.assertFalse(
            _plausible_name_line(
                "E-mail: info@empresa.es"
            )
        )

        self.assertFalse(
            _plausible_name_line(
                "Internet: www.empresa.es"
            )
        )

        self.assertFalse(
            _plausible_name_line(
                "Telfs.: 952978250"
            )
        )


    def test_presupuesto_summary_totals_are_math_validated(self):
        from .presupuesto_import import (
            _find_totals,
        )

        result = _find_totals(
            """
            Resumen de importes:
            2.369,11 €
            Total Importe
            13.650,57 €
            IVA: 21%Base Imponible
            11.281,46 €
            """
        )

        self.assertEqual(
            result["base"],
            "11281.46",
        )

        self.assertEqual(
            result["iva"],
            "2369.11",
        )

        self.assertEqual(
            result["total"],
            "13650.57",
        )


    def test_presupuesto_exact_tax_match_canonicalizes_master_identity(self):
        from .presupuesto_import import (
            analizar_texto_presupuesto,
        )

        providers = [
            {
                "id": 1006,
                "team_id": 1,
                "nombre_comercial": (
                    "INSTALACIONES RAYMA"
                ),
                "nombre_fiscal": (
                    "INSTALACIONES RAYMA S.L."
                ),
                "cif": "B29707536",
            }
        ]

        result = analizar_texto_presupuesto(
            """
            Fecha:5/5/2026
            Nº Presupuesto:A/2026/00102
            CIF: B-29.707.536
            E-mail: info@instalacionesrayma.es

            Resumen de importes:
            2.369,11 €
            Total Importe
            13.650,57 €
            IVA: 21%Base Imponible
            11.281,46 €
            """,
            providers,
        )

        detected = result[
            "detected"
        ]

        matches = result[
            "provider_matches"
        ]

        self.assertEqual(
            detected[
                "proveedor_nombre"
            ],
            "INSTALACIONES RAYMA",
        )

        self.assertEqual(
            detected[
                "nif_cif_candidates"
            ],
            ["B29707536"],
        )

        self.assertEqual(
            detected[
                "numero_documento"
            ],
            "A/2026/00102",
        )

        self.assertEqual(
            detected["fecha"],
            "2026-05-05",
        )

        self.assertEqual(
            detected[
                "base_imponible"
            ],
            "11281.46",
        )

        self.assertEqual(
            detected["iva"],
            "2369.11",
        )

        self.assertEqual(
            detected["total"],
            "13650.57",
        )

        self.assertEqual(
            len(matches),
            1,
        )

        self.assertEqual(
            matches[0]["id"],
            1006,
        )

        self.assertEqual(
            matches[0]["confidence"],
            "MUY_ALTA",
        )

        self.assertEqual(
            matches[0]["reason"],
            "CIF/NIF exacto",
        )


    # COMPARATIVAS_V2A_PERSISTENT_CONCEPT_MODEL

    def test_v2a_concepto_preserves_source_evidence(self):
        from decimal import Decimal

        from comparativas.models import (
            Comparativa,
            ConceptoOferta,
            Ofertante,
            Oferta,
        )

        comparativa = Comparativa.objects.create(
            team=self.team,
            titulo="Comparativa V2A",
            creado_por=self.user,
        )

        ofertante = Ofertante.objects.create(
            comparativa=comparativa,
            nombre="Proveedor V2A",
        )

        oferta = Oferta.objects.create(
            ofertante=ofertante,
            version=1,
            creado_por=self.user,
        )

        concepto = ConceptoOferta.objects.create(
            oferta=oferta,
            orden=1,
            codigo_original="ABC-01",
            titulo_original=(
                "INSTALACION FONTANERIA BAÑO"
            ),
            descripcion_original=(
                "Instalación completa según "
                "documento original."
            ),
            texto_normalizado=(
                "instalacion fontaneria baño"
            ),
            cantidad=Decimal("2.0000"),
            unidad="Ud",
            precio_unitario=Decimal(
                "714.4200"
            ),
            importe=Decimal("1428.84"),
            alcance=(
                ConceptoOferta
                .Alcance
                .INCLUIDO
            ),
            pagina=2,
            linea_inicio=40,
            linea_fin=44,
            evidencia=(
                "Texto fuente conservado."
            ),
            origen=(
                ConceptoOferta
                .Origen
                .DETERMINISTA
            ),
            confianza_extraccion=(
                ConceptoOferta
                .Confianza
                .ALTA
            ),
        )

        concepto.refresh_from_db()

        self.assertEqual(
            concepto.oferta_id,
            oferta.pk,
        )

        self.assertEqual(
            concepto.cantidad,
            Decimal("2.0000"),
        )

        self.assertEqual(
            concepto.precio_unitario,
            Decimal("714.4200"),
        )

        self.assertEqual(
            concepto.importe,
            Decimal("1428.84"),
        )

        self.assertEqual(
            concepto.evidencia,
            "Texto fuente conservado.",
        )

        self.assertEqual(
            oferta.conceptos.count(),
            1,
        )


    def test_v2a_concepto_rejects_document_from_other_offer(self):
        from django.core.exceptions import (
            ValidationError,
        )
        from django.core.files.uploadedfile import (
            SimpleUploadedFile,
        )

        from comparativas.models import (
            Comparativa,
            ConceptoOferta,
            Ofertante,
            Oferta,
        )
        from comparativas.services import (
            guardar_documento,
        )

        comparativa = Comparativa.objects.create(
            team=self.team,
            titulo="Comparativa documentos V2A",
            creado_por=self.user,
        )

        ofertante_a = Ofertante.objects.create(
            comparativa=comparativa,
            nombre="Proveedor A",
        )

        ofertante_b = Ofertante.objects.create(
            comparativa=comparativa,
            nombre="Proveedor B",
        )

        oferta_a = Oferta.objects.create(
            ofertante=ofertante_a,
            version=1,
            creado_por=self.user,
        )

        oferta_b = Oferta.objects.create(
            ofertante=ofertante_b,
            version=1,
            creado_por=self.user,
        )

        documento_b, created = guardar_documento(
            oferta=oferta_b,
            uploaded_file=SimpleUploadedFile(
                "otro.pdf",
                b"%PDF-1.4 documento",
                content_type="application/pdf",
            ),
            user=self.user,
        )

        self.assertTrue(created)

        with self.assertRaises(
            ValidationError
        ):
            ConceptoOferta.objects.create(
                oferta=oferta_a,
                documento=documento_b,
                titulo_original=(
                    "Concepto inválido"
                ),
            )


    def test_v2a_relation_supports_n_to_m(self):
        from django.core.exceptions import (
            ValidationError,
        )

        from comparativas.models import (
            Comparativa,
            ConceptoOferta,
            GrupoComparacion,
            Ofertante,
            Oferta,
            RelacionConcepto,
        )

        comparativa = Comparativa.objects.create(
            team=self.team,
            titulo="Comparativa N M",
            creado_por=self.user,
        )

        ofertante_a = Ofertante.objects.create(
            comparativa=comparativa,
            nombre="Proveedor A",
        )

        ofertante_b = Ofertante.objects.create(
            comparativa=comparativa,
            nombre="Proveedor B",
        )

        oferta_a = Oferta.objects.create(
            ofertante=ofertante_a,
            version=1,
            creado_por=self.user,
        )

        oferta_b = Oferta.objects.create(
            ofertante=ofertante_b,
            version=1,
            creado_por=self.user,
        )

        concepto_a = ConceptoOferta.objects.create(
            oferta=oferta_a,
            orden=1,
            titulo_original=(
                "Aseo y cocina agrupados"
            ),
        )

        concepto_b = ConceptoOferta.objects.create(
            oferta=oferta_b,
            orden=1,
            titulo_original=(
                "Fontanería cocina"
            ),
        )

        grupo_aseo = GrupoComparacion.objects.create(
            comparativa=comparativa,
            orden=1,
            nombre="Fontanería aseo",
        )

        grupo_cocina = (
            GrupoComparacion.objects.create(
                comparativa=comparativa,
                orden=2,
                nombre="Fontanería cocina",
            )
        )

        RelacionConcepto.objects.create(
            grupo=grupo_aseo,
            concepto=concepto_a,
        )

        RelacionConcepto.objects.create(
            grupo=grupo_cocina,
            concepto=concepto_a,
        )

        RelacionConcepto.objects.create(
            grupo=grupo_cocina,
            concepto=concepto_b,
        )

        self.assertEqual(
            concepto_a
            .relaciones_comparacion
            .count(),
            2,
        )

        self.assertEqual(
            grupo_cocina
            .relaciones
            .count(),
            2,
        )

        with self.assertRaises(
            ValidationError
        ):
            RelacionConcepto.objects.create(
                grupo=grupo_cocina,
                concepto=concepto_a,
            )


    def test_v2a_relation_rejects_cross_comparativa(self):
        from django.core.exceptions import (
            ValidationError,
        )

        from comparativas.models import (
            Comparativa,
            ConceptoOferta,
            GrupoComparacion,
            Ofertante,
            Oferta,
            RelacionConcepto,
        )

        comparativa_a = Comparativa.objects.create(
            team=self.team,
            titulo="Comparativa A",
            creado_por=self.user,
        )

        comparativa_b = Comparativa.objects.create(
            team=self.team,
            titulo="Comparativa B",
            creado_por=self.user,
        )

        ofertante_b = Ofertante.objects.create(
            comparativa=comparativa_b,
            nombre="Proveedor B",
        )

        oferta_b = Oferta.objects.create(
            ofertante=ofertante_b,
            version=1,
            creado_por=self.user,
        )

        concepto_b = ConceptoOferta.objects.create(
            oferta=oferta_b,
            titulo_original=(
                "Concepto comparativa B"
            ),
        )

        grupo_a = GrupoComparacion.objects.create(
            comparativa=comparativa_a,
            nombre="Grupo comparativa A",
        )

        with self.assertRaises(
            ValidationError
        ):
            RelacionConcepto.objects.create(
                grupo=grupo_a,
                concepto=concepto_b,
            )


    # COMPARATIVAS_V2B_GENERIC_EXTRACTION_SERVICE_R1

    def test_v2b_arithmetic_table_requires_math_consistency(self):
        from decimal import Decimal

        from comparativas.concept_extraction import (
            extract_text_concepts,
        )

        result = extract_text_concepts(
            (
                "714,42 "
                "1.428,842,000Ud "
                "INSTALACION DE FONTANERIA BAÑO. "
                "0,00"
            )
        )

        self.assertEqual(
            len(result),
            1,
        )

        item = result[0]

        self.assertEqual(
            item["strategy"],
            "TABLA_ARITMETICA",
        )

        self.assertEqual(
            item["cantidad"],
            Decimal("2.000"),
        )

        self.assertEqual(
            item["precio_unitario"],
            Decimal("714.42"),
        )

        self.assertEqual(
            item["importe"],
            Decimal("1428.84"),
        )


    def test_v2b_zero_value_section_is_context_not_concept(self):
        from comparativas.concept_extraction import (
            extract_text_concepts,
        )

        result = extract_text_concepts(
            "\n".join(
                [
                    "0,000VIVIENDA 76 0,00",
                    (
                        "14,48 144,8010,000ML "
                        "TUBERIA DISTRIBUCION. 0,00"
                    ),
                ]
            )
        )

        self.assertEqual(
            len(result),
            1,
        )

        self.assertEqual(
            result[0]["contexto"],
            "VIVIENDA 76",
        )


    def test_v2b_multiline_exclusion_is_joined(self):
        from comparativas.concept_extraction import (
            extract_text_concepts,
        )

        result = extract_text_concepts(
            "\n".join(
                [
                    (
                        "NOTA; EN ESTE PRESUPUESTO "
                        "NO ENTRA ALBANILERIA, "
                        "NI MONTAJE DE"
                    ),
                    "COCINAS",
                    "BASE IMPONIBLE IVA TOTAL",
                ]
            )
        )

        self.assertEqual(
            len(result),
            1,
        )

        self.assertEqual(
            result[0]["alcance"],
            "EXCLUIDO",
        )

        self.assertIn(
            "COCINAS",
            result[0]["titulo"],
        )


    def test_v2b_amount_block_recovers_previous_quantity_line(self):
        from decimal import Decimal

        from comparativas.concept_extraction import (
            extract_text_concepts,
        )

        result = extract_text_concepts(
            "\n".join(
                [
                    (
                        "3 COCINAS CON TOMAS PARA "
                        "FREGADEROS,LAVADORAS,"
                    ),
                    (
                        "LAVAVAJILLAS Y TERMOS "
                        "AGUA CALIENTE. "
                        "1950,00 €"
                    ),
                ]
            )
        )

        self.assertEqual(
            len(result),
            1,
        )

        self.assertEqual(
            result[0]["importe"],
            Decimal("1950.00"),
        )

        self.assertIn(
            "3 COCINAS",
            result[0]["titulo"],
        )


    def test_v2b_amount_block_recovers_action_heading(self):
        from decimal import Decimal

        from comparativas.concept_extraction import (
            extract_text_concepts,
        )

        result = extract_text_concepts(
            "\n".join(
                [
                    (
                        "REALIZAR TRABAJOS DE "
                        "FONTANERIA PARA INSTALACION"
                    ),
                    (
                        "DE TUBERIAS GENERALES "
                        "DE AGUA FRIA"
                    ),
                    (
                        "Y SUBIDAS HASTA LLAVE "
                        "GENERAL 450,00 €"
                    ),
                ]
            )
        )

        self.assertEqual(
            len(result),
            1,
        )

        self.assertEqual(
            result[0]["importe"],
            Decimal("450.00"),
        )

        self.assertTrue(
            result[0]["titulo"].startswith(
                "REALIZAR TRABAJOS"
            )
        )


    def test_v2b_layout_header_recovers_quantity_without_inventing_price(self):
        from decimal import Decimal

        from comparativas.concept_extraction import (
            extract_layout_table,
        )

        layout = (
            "Concepto"
            + (" " * 30)
            + "Unidades"
            + (" " * 8)
            + "Precio"
            + (" " * 8)
            + "Importe\n"
            + "FONTANERIA BAÑO"
            + (" " * 29)
            + "3\n"
            + "Descripcion de la partida\n"
            + "Base imponible"
        )

        result = extract_layout_table(
            layout
        )

        self.assertEqual(
            len(result),
            1,
        )

        self.assertEqual(
            result[0]["cantidad"],
            Decimal("3"),
        )

        self.assertIsNone(
            result[0]["precio_unitario"]
        )

        self.assertIsNone(
            result[0]["importe"]
        )


    def test_v2b_reconciliation_complete(self):
        from decimal import Decimal

        from comparativas.concept_extraction import (
            reconcile_concepts,
        )

        concepts = [
            {
                "alcance": "INCLUIDO",
                "importe": Decimal(
                    "1950.00"
                ),
            },
            {
                "alcance": "INCLUIDO",
                "importe": Decimal(
                    "3150.00"
                ),
            },
            {
                "alcance": "INCLUIDO",
                "importe": Decimal(
                    "950.00"
                ),
            },
            {
                "alcance": "INCLUIDO",
                "importe": Decimal(
                    "450.00"
                ),
            },
        ]

        result = reconcile_concepts(
            concepts,
            Decimal("6500.00"),
        )

        self.assertEqual(
            result["estado"],
            "COMPLETA",
        )

        self.assertEqual(
            result[
                "suma_conceptos"
            ],
            Decimal("6500.00"),
        )

        self.assertEqual(
            result["diferencia"],
            Decimal("0.00"),
        )


    def test_v2b_reconciliation_without_line_amounts_is_not_verifiable(self):
        from decimal import Decimal

        from comparativas.concept_extraction import (
            reconcile_concepts,
        )

        result = reconcile_concepts(
            [
                {
                    "alcance": "INCLUIDO",
                    "importe": None,
                }
            ],
            Decimal("6252.40"),
        )

        self.assertEqual(
            result["estado"],
            "NO_VERIFICABLE",
        )

        self.assertIsNone(
            result["diferencia"]
        )


    # COMPARATIVAS_V2C_PREVIEW_CONFIRM_R2

    def _v2c_create_document(
        self,
        *,
        text=None,
        base="6500.00",
    ):
        from django.core.files.uploadedfile import (
            SimpleUploadedFile,
        )

        from comparativas.models import (
            Comparativa,
            Ofertante,
            Oferta,
        )
        from comparativas.services import (
            guardar_documento,
        )

        self.user.is_superuser = True
        self.user.save(
            update_fields=[
                "is_superuser",
            ]
        )

        comparativa = (
            Comparativa.objects.create(
                team=self.team,
                titulo="Comparativa V2C",
                creado_por=self.user,
            )
        )

        ofertante = (
            Ofertante.objects.create(
                comparativa=comparativa,
                nombre="Proveedor V2C",
            )
        )

        oferta = Oferta.objects.create(
            ofertante=ofertante,
            version=1,
            base=base,
            creado_por=self.user,
        )

        documento, created = (
            guardar_documento(
                oferta=oferta,
                uploaded_file=(
                    SimpleUploadedFile(
                        "presupuesto.txt",
                        b"documento-v2c",
                        content_type="text/plain",
                    )
                ),
                user=self.user,
            )
        )

        self.assertTrue(created)

        documento.texto_extraido = (
            text
            or (
                "3 COCINAS CON TOMAS PARA "
                "FREGADEROS,LAVADORAS, "
                "1950,00 €"
            )
        )

        documento.save(
            update_fields=[
                "texto_extraido",
            ]
        )

        return (
            comparativa,
            ofertante,
            oferta,
            documento,
        )


    def _v2c_form_data(
        self,
        rows,
    ):
        data = {
            "concepts-TOTAL_FORMS": (
                str(len(rows))
            ),
            "concepts-INITIAL_FORMS": "0",
            "concepts-MIN_NUM_FORMS": "0",
            "concepts-MAX_NUM_FORMS": "200",
        }

        for index, row in enumerate(rows):
            prefix = (
                f"concepts-{index}-"
            )

            if row.get(
                "selected",
                True,
            ):
                data[
                    prefix + "selected"
                ] = "on"

            data[
                prefix + "source_index"
            ] = str(
                row.get(
                    "source_index",
                    index,
                )
            )

            data[
                prefix + "titulo"
            ] = row["titulo"]

            data[
                prefix + "descripcion"
            ] = row.get(
                "descripcion",
                "",
            )

            data[
                prefix + "cantidad"
            ] = row.get(
                "cantidad",
                "",
            )

            data[
                prefix + "unidad"
            ] = row.get(
                "unidad",
                "",
            )

            data[
                prefix + "precio_unitario"
            ] = row.get(
                "precio_unitario",
                "",
            )

            data[
                prefix + "importe"
            ] = row.get(
                "importe",
                "",
            )

            data[
                prefix + "alcance"
            ] = row.get(
                "alcance",
                "INCLUIDO",
            )

        return data


    def test_v2c_detail_and_preview_are_read_only(self):
        from django.urls import reverse

        from comparativas.models import (
            ConceptoOferta,
        )

        (
            comparativa,
            ofertante,
            oferta,
            documento,
        ) = self._v2c_create_document()

        self.client.force_login(
            self.user
        )

        detail = self.client.get(
            reverse(
                "comparativas:detail",
                args=[
                    comparativa.uuid,
                ],
            ),
            secure=True,
        )

        self.assertEqual(
            detail.status_code,
            200,
        )

        self.assertContains(
            detail,
            "Analizar conceptos",
        )

        preview = self.client.get(
            reverse(
                "comparativas:documento_conceptos",
                args=[
                    documento.pk,
                ],
            ),
            secure=True,
        )

        self.assertEqual(
            preview.status_code,
            200,
        )

        self.assertContains(
            preview,
            "Previsualización",
        )

        self.assertEqual(
            ConceptoOferta.objects.count(),
            0,
        )


    def test_v2c_confirm_creates_concept_and_completes_document(self):
        from decimal import Decimal

        from django.urls import reverse

        from comparativas.models import (
            ConceptoOferta,
        )

        (
            comparativa,
            ofertante,
            oferta,
            documento,
        ) = self._v2c_create_document()

        self.client.force_login(
            self.user
        )

        data = self._v2c_form_data(
            [
                {
                    "source_index": 0,
                    "titulo": (
                        "3 COCINAS CON TOMAS PARA "
                        "FREGADEROS,LAVADORAS, "
                        "1950,00 €"
                    ),
                    "importe": "1950.00",
                },
            ]
        )

        response = self.client.post(
            reverse(
                "comparativas:documento_conceptos",
                args=[
                    documento.pk,
                ],
            ),
            data,
            secure=True,
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        concepto = (
            ConceptoOferta.objects.get(
                documento=documento
            )
        )

        self.assertEqual(
            concepto.importe,
            Decimal("1950.00"),
        )

        self.assertEqual(
            concepto.origen,
            ConceptoOferta
            .Origen
            .DETERMINISTA,
        )

        documento.refresh_from_db()

        self.assertEqual(
            documento.estado_analisis,
            "COMPLETADO",
        )

        self.assertTrue(
            documento.datos_extraidos[
                "conceptos_v2c"
            ]["confirmed"]
        )


    def test_v2c_human_edit_and_deselect_recalculate_reconciliation(self):
        from decimal import Decimal

        from django.urls import reverse

        from comparativas.models import (
            ConceptoOferta,
        )

        text = "\n".join(
            [
                (
                    "3 COCINAS "
                    "1950,00 €"
                ),
                (
                    "RED GENERAL DE FONTANERIA "
                    "4550,00 €"
                ),
            ]
        )

        (
            comparativa,
            ofertante,
            oferta,
            documento,
        ) = self._v2c_create_document(
            text=text,
            base="6500.00",
        )

        self.client.force_login(
            self.user
        )

        data = self._v2c_form_data(
            [
                {
                    "source_index": 0,
                    "titulo": (
                        "Instalación de "
                        "fontanería 3 cocinas"
                    ),
                    "importe": "1950.00",
                    "selected": True,
                },
                {
                    "source_index": 1,
                    "titulo": (
                        "RED GENERAL DE "
                        "FONTANERIA 4550,00 €"
                    ),
                    "importe": "4550.00",
                    "selected": False,
                },
            ]
        )

        response = self.client.post(
            reverse(
                "comparativas:documento_conceptos",
                args=[
                    documento.pk,
                ],
            ),
            data,
            secure=True,
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        concepts = (
            ConceptoOferta.objects
            .filter(
                documento=documento
            )
        )

        self.assertEqual(
            concepts.count(),
            1,
        )

        concepto = concepts.get()

        self.assertEqual(
            concepto.origen,
            ConceptoOferta
            .Origen
            .HUMANO,
        )

        self.assertTrue(
            concepto.raw_data[
                "v2c"
            ]["human_edited"]
        )

        documento.refresh_from_db()

        summary = (
            documento
            .datos_extraidos[
                "conceptos_v2c"
            ]
        )

        self.assertEqual(
            summary[
                "source_reconciliation"
            ]["estado"],
            "COMPLETA",
        )

        self.assertEqual(
            summary[
                "reconciliation"
            ]["estado"],
            "PARCIAL",
        )

        self.assertEqual(
            Decimal(
                summary[
                    "reconciliation"
                ]["suma_conceptos"]
            ),
            Decimal("1950.00"),
        )

        self.assertEqual(
            Decimal(
                summary[
                    "reconciliation"
                ]["diferencia"]
            ),
            Decimal("-4550.00"),
        )


    def test_v2c_rejects_tampered_source_index(self):
        from django.urls import reverse

        from comparativas.models import (
            ConceptoOferta,
        )

        (
            comparativa,
            ofertante,
            oferta,
            documento,
        ) = self._v2c_create_document()

        self.client.force_login(
            self.user
        )

        data = self._v2c_form_data(
            [
                {
                    "source_index": 99,
                    "titulo": (
                        "Concepto manipulado"
                    ),
                    "importe": "1950.00",
                },
            ]
        )

        response = self.client.post(
            reverse(
                "comparativas:documento_conceptos",
                args=[
                    documento.pk,
                ],
            ),
            data,
            secure=True,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "La previsualización ha cambiado",
        )

        self.assertEqual(
            ConceptoOferta.objects.count(),
            0,
        )


    def test_v2c_existing_confirmation_is_read_only(self):
        from django.urls import reverse

        from comparativas.models import (
            ConceptoOferta,
        )

        (
            comparativa,
            ofertante,
            oferta,
            documento,
        ) = self._v2c_create_document()

        ConceptoOferta.objects.create(
            oferta=oferta,
            documento=documento,
            orden=1,
            titulo_original=(
                "Concepto existente"
            ),
        )

        self.client.force_login(
            self.user
        )

        response = self.client.get(
            reverse(
                "comparativas:documento_conceptos",
                args=[
                    documento.pk,
                ],
            ),
            secure=True,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "Conceptos confirmados",
        )

        self.assertEqual(
            ConceptoOferta.objects.filter(
                documento=documento
            ).count(),
            1,
        )


    # COMPARATIVAS_V2C_EXCLUSION_BOUNDARY_FIX_R1

    def test_v2c_exclusion_stops_before_payment_clause(self):
        from comparativas.concept_extraction import (
            extract_text_concepts,
        )

        text = "\n".join(
            [
                (
                    "No incluye: contadores de agua, "
                    "loza sanitaria, griferias, "
                    "ni su instalación."
                ),
                (
                    "SE ABONARÁN 2000€ "
                    "A LA ACEPTACION DEL "
                    "PRESUPUESTO EN CONCEPTO "
                    "DE FIANZA."
                ),
                (
                    "RESTO, A LA FINALIZACIÓN "
                    "DE CADA PARTIDA DETALLADA"
                ),
                "CONFORME",
                "NOMBRE Y APELLIDOS DNI:",
            ]
        )

        concepts = extract_text_concepts(
            text
        )

        exclusions = [
            item
            for item in concepts
            if item["alcance"]
            == "EXCLUIDO"
        ]

        self.assertEqual(
            len(exclusions),
            1,
        )

        self.assertEqual(
            exclusions[0]["titulo"],
            (
                "No incluye: contadores de agua, "
                "loza sanitaria, griferias, "
                "ni su instalación."
            ),
        )

        self.assertNotIn(
            "SE ABONAR",
            exclusions[0]["titulo"],
        )

        self.assertNotIn(
            "RESTO",
            exclusions[0]["titulo"],
        )

        self.assertNotIn(
            "DNI",
            exclusions[0]["titulo"],
        )


    # COMPARATIVAS_V2C_EDIT_CONFIRMED_CONCEPTS_R1

    def _v2c_edit_form_data(
        self,
        concepts,
        *,
        overrides=None,
    ):
        overrides = (
            overrides
            or {}
        )

        data = {
            "edit-TOTAL_FORMS": (
                str(len(concepts))
            ),
            "edit-INITIAL_FORMS": "0",
            "edit-MIN_NUM_FORMS": "0",
            "edit-MAX_NUM_FORMS": "200",
        }

        for index, concept in enumerate(
            concepts
        ):
            values = {
                "titulo": (
                    concept.titulo_original
                ),
                "descripcion": (
                    concept.descripcion_original
                ),
                "cantidad": (
                    ""
                    if concept.cantidad is None
                    else str(concept.cantidad)
                ),
                "unidad": (
                    concept.unidad
                ),
                "precio_unitario": (
                    ""
                    if concept.precio_unitario is None
                    else str(
                        concept.precio_unitario
                    )
                ),
                "importe": (
                    ""
                    if concept.importe is None
                    else str(concept.importe)
                ),
                "alcance": (
                    concept.alcance
                ),
            }

            values.update(
                overrides.get(
                    concept.pk,
                    {},
                )
            )

            prefix = (
                f"edit-{index}-"
            )

            data[
                prefix + "concept_id"
            ] = str(
                concept.pk
            )

            for key, value in (
                values.items()
            ):
                data[
                    prefix + key
                ] = value

        return data


    def test_v2c_edit_confirmed_get_shows_form(self):
        from django.urls import reverse

        from comparativas.models import (
            ConceptoOferta,
        )

        (
            comparativa,
            ofertante,
            oferta,
            documento,
        ) = self._v2c_create_document()

        concepto = (
            ConceptoOferta.objects.create(
                oferta=oferta,
                documento=documento,
                orden=1,
                titulo_original=(
                    "Concepto confirmado"
                ),
                importe="1950.00",
                evidencia=(
                    "Evidencia original"
                ),
            )
        )

        self.client.force_login(
            self.user
        )

        response = self.client.get(
            reverse(
                "comparativas:documento_conceptos_editar",
                args=[documento.pk],
            ),
            secure=True,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "Editar conceptos confirmados",
        )

        self.assertContains(
            response,
            "Evidencia original",
        )

        concepto.refresh_from_db()

        self.assertEqual(
            concepto.titulo_original,
            "Concepto confirmado",
        )


    def test_v2c_edit_preserves_evidence_and_audits_before_after(self):
        from django.urls import reverse

        from comparativas.models import (
            ConceptoOferta,
        )

        (
            comparativa,
            ofertante,
            oferta,
            documento,
        ) = self._v2c_create_document()

        concepto = (
            ConceptoOferta.objects.create(
                oferta=oferta,
                documento=documento,
                orden=1,
                titulo_original=(
                    "Texto OCR imperfecto"
                ),
                importe="1950.00",
                evidencia=(
                    "OCR FUENTE INALTERABLE"
                ),
                origen=(
                    ConceptoOferta
                    .Origen
                    .DETERMINISTA
                ),
            )
        )

        concepts = [concepto]

        data = self._v2c_edit_form_data(
            concepts,
            overrides={
                concepto.pk: {
                    "titulo": (
                        "Concepto corregido"
                    ),
                }
            },
        )

        self.client.force_login(
            self.user
        )

        response = self.client.post(
            reverse(
                "comparativas:documento_conceptos_editar",
                args=[documento.pk],
            ),
            data,
            secure=True,
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        concepto.refresh_from_db()

        self.assertEqual(
            concepto.titulo_original,
            "Concepto corregido",
        )

        self.assertEqual(
            concepto.evidencia,
            "OCR FUENTE INALTERABLE",
        )

        self.assertEqual(
            concepto.origen,
            ConceptoOferta
            .Origen
            .HUMANO,
        )

        history = (
            concepto.raw_data[
                "v2c"
            ][
                "edit_history"
            ]
        )

        self.assertEqual(
            len(history),
            1,
        )

        self.assertEqual(
            history[0][
                "before"
            ][
                "titulo"
            ],
            "Texto OCR imperfecto",
        )

        self.assertEqual(
            history[0][
                "after"
            ][
                "titulo"
            ],
            "Concepto corregido",
        )

        self.assertEqual(
            history[0][
                "edited_by_user_id"
            ],
            self.user.pk,
        )


    def test_v2c_edit_recalculates_saved_reconciliation(self):
        from django.urls import reverse

        from comparativas.models import (
            ConceptoOferta,
        )

        (
            comparativa,
            ofertante,
            oferta,
            documento,
        ) = self._v2c_create_document(
            base="6500.00"
        )

        first = (
            ConceptoOferta.objects.create(
                oferta=oferta,
                documento=documento,
                orden=1,
                titulo_original="Partida A",
                importe="1950.00",
                alcance="INCLUIDO",
            )
        )

        second = (
            ConceptoOferta.objects.create(
                oferta=oferta,
                documento=documento,
                orden=2,
                titulo_original="Partida B",
                importe="4550.00",
                alcance="INCLUIDO",
            )
        )

        documento.datos_extraidos = {
            "conceptos_v2c": {
                "confirmed": True,
                "count": 2,
                "reconciliation": {
                    "estado": "COMPLETA",
                },
            }
        }

        documento.save(
            update_fields=[
                "datos_extraidos",
            ]
        )

        data = self._v2c_edit_form_data(
            [first, second],
            overrides={
                second.pk: {
                    "importe": "4500.00",
                }
            },
        )

        self.client.force_login(
            self.user
        )

        response = self.client.post(
            reverse(
                "comparativas:documento_conceptos_editar",
                args=[documento.pk],
            ),
            data,
            secure=True,
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        documento.refresh_from_db()

        reconciliation = (
            documento
            .datos_extraidos[
                "conceptos_v2c"
            ][
                "reconciliation"
            ]
        )

        self.assertEqual(
            reconciliation[
                "estado"
            ],
            "PARCIAL",
        )

        self.assertEqual(
            reconciliation[
                "suma_conceptos"
            ],
            "6450.00",
        )

        self.assertEqual(
            reconciliation[
                "diferencia"
            ],
            "-50.00",
        )


    def test_v2c_edit_without_changes_keeps_original_origin(self):
        from django.urls import reverse

        from comparativas.models import (
            ConceptoOferta,
        )

        (
            comparativa,
            ofertante,
            oferta,
            documento,
        ) = self._v2c_create_document()

        concepto = (
            ConceptoOferta.objects.create(
                oferta=oferta,
                documento=documento,
                orden=1,
                titulo_original=(
                    "Concepto sin cambios"
                ),
                importe="1950.00",
                origen=(
                    ConceptoOferta
                    .Origen
                    .DETERMINISTA
                ),
            )
        )

        data = self._v2c_edit_form_data(
            [concepto]
        )

        self.client.force_login(
            self.user
        )

        response = self.client.post(
            reverse(
                "comparativas:documento_conceptos_editar",
                args=[documento.pk],
            ),
            data,
            secure=True,
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        concepto.refresh_from_db()

        self.assertEqual(
            concepto.origen,
            ConceptoOferta
            .Origen
            .DETERMINISTA,
        )

        self.assertNotIn(
            "edit_history",
            (
                concepto.raw_data.get(
                    "v2c",
                    {}
                )
            ),
        )


    def test_v2c_edit_rejects_tampered_concept_set(self):
        from django.urls import reverse

        from comparativas.models import (
            ConceptoOferta,
        )

        (
            comparativa,
            ofertante,
            oferta,
            documento,
        ) = self._v2c_create_document()

        first = (
            ConceptoOferta.objects.create(
                oferta=oferta,
                documento=documento,
                orden=1,
                titulo_original="Partida 1",
            )
        )

        second = (
            ConceptoOferta.objects.create(
                oferta=oferta,
                documento=documento,
                orden=2,
                titulo_original="Partida 2",
            )
        )

        data = self._v2c_edit_form_data(
            [first]
        )

        self.client.force_login(
            self.user
        )

        response = self.client.post(
            reverse(
                "comparativas:documento_conceptos_editar",
                args=[documento.pk],
            ),
            data,
            secure=True,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            (
                "El conjunto de conceptos "
                "ha cambiado"
            ),
        )

        first.refresh_from_db()
        second.refresh_from_db()

        self.assertEqual(
            first.titulo_original,
            "Partida 1",
        )

        self.assertEqual(
            second.titulo_original,
            "Partida 2",
        )


    def test_v2c_edit_blocks_concepts_with_comparison_relations(self):
        from django.urls import reverse

        from comparativas.models import (
            ConceptoOferta,
            GrupoComparacion,
            RelacionConcepto,
        )

        (
            comparativa,
            ofertante,
            oferta,
            documento,
        ) = self._v2c_create_document()

        concepto = (
            ConceptoOferta.objects.create(
                oferta=oferta,
                documento=documento,
                orden=1,
                titulo_original=(
                    "Concepto relacionado"
                ),
            )
        )

        grupo = (
            GrupoComparacion.objects.create(
                comparativa=comparativa,
                nombre=(
                    "Grupo relacionado"
                ),
            )
        )

        RelacionConcepto.objects.create(
            grupo=grupo,
            concepto=concepto,
        )

        self.client.force_login(
            self.user
        )

        response = self.client.get(
            reverse(
                "comparativas:documento_conceptos_editar",
                args=[documento.pk],
            ),
            secure=True,
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        concepto.refresh_from_db()

        self.assertEqual(
            concepto.titulo_original,
            "Concepto relacionado",
        )


    # COMPARATIVAS_V2C_COMPACT_CONCEPT_TABLE_V1

    def test_v2c_preview_uses_compact_table_and_hides_internal_strategy(self):
        from django.urls import reverse

        (
            comparativa,
            ofertante,
            oferta,
            documento,
        ) = self._v2c_create_document()

        self.client.force_login(
            self.user
        )

        response = self.client.get(
            reverse(
                "comparativas:documento_conceptos",
                args=[documento.pk],
            ),
            secure=True,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "concept-review-compact",
        )

        self.assertContains(
            response,
            "concept-context-line",
        )

        self.assertNotContains(
            response,
            "IMPORTE_EN_BLOQUE",
        )


    def test_v2c_confirmed_edit_uses_compact_table(self):
        from django.urls import reverse

        from comparativas.models import (
            ConceptoOferta,
        )

        (
            comparativa,
            ofertante,
            oferta,
            documento,
        ) = self._v2c_create_document()

        ConceptoOferta.objects.create(
            oferta=oferta,
            documento=documento,
            orden=1,
            titulo_original=(
                "Concepto confirmado"
            ),
            evidencia=(
                "Evidencia original"
            ),
        )

        self.client.force_login(
            self.user
        )

        response = self.client.get(
            reverse(
                "comparativas:documento_conceptos_editar",
                args=[documento.pk],
            ),
            secure=True,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "concept-edit-compact",
        )

        self.assertContains(
            response,
            "original-evidence",
        )


    # COMPARATIVAS_V2D_SOURCE_UNITS_A1_R2

    def _v2d_fake_concept(
        self,
        *,
        pk,
        oferta_id,
        supplier_id,
        title,
        order,
        alcance="INCLUIDO",
        unit="Ud",
        price=None,
        quantity=None,
        amount=None,
        context="",
    ):
        from types import SimpleNamespace

        supplier = SimpleNamespace(
            pk=supplier_id,
            nombre=(
                f"Proveedor {supplier_id}"
            ),
        )

        offer = SimpleNamespace(
            ofertante=supplier,
        )

        return SimpleNamespace(
            pk=pk,
            oferta_id=oferta_id,
            oferta=offer,
            orden=order,
            alcance=alcance,
            titulo_original=title,
            unidad=unit,
            precio_unitario=price,
            cantidad=quantity,
            importe=amount,
            pagina=1,
            raw_data={
                "v2c": {
                    "contexto": context,
                }
            },
        )


    def test_v2d_source_units_aggregate_exact_repetitions(self):
        from decimal import Decimal

        from comparativas.matching_prepare import (
            build_source_units,
        )

        concepts = [
            self._v2d_fake_concept(
                pk=1,
                oferta_id=10,
                supplier_id=20,
                title="Instalación baño",
                order=1,
                unit="Ud",
                price=Decimal("100.00"),
                quantity=Decimal("1"),
                amount=Decimal("100.00"),
                context="Zona A",
            ),
            self._v2d_fake_concept(
                pk=2,
                oferta_id=10,
                supplier_id=20,
                title="INSTALACION BAÑO.",
                order=2,
                unit="ud",
                price=Decimal("100.00"),
                quantity=Decimal("2"),
                amount=Decimal("200.00"),
                context="Zona B",
            ),
        ]

        units = build_source_units(
            concepts
        )

        self.assertEqual(
            len(units),
            1,
        )

        unit = units[0]

        self.assertEqual(
            unit["member_ids"],
            [1, 2],
        )

        self.assertEqual(
            unit["cantidad_total"],
            Decimal("3"),
        )

        self.assertEqual(
            unit["importe_total"],
            Decimal("300.00"),
        )

        self.assertEqual(
            unit["contexts"],
            [
                "Zona A",
                "Zona B",
            ],
        )


    def test_v2d_source_units_never_merge_different_offers(self):
        from comparativas.matching_prepare import (
            build_source_units,
        )

        concepts = [
            self._v2d_fake_concept(
                pk=1,
                oferta_id=10,
                supplier_id=20,
                title="Partida idéntica",
                order=1,
            ),
            self._v2d_fake_concept(
                pk=2,
                oferta_id=11,
                supplier_id=21,
                title="Partida idéntica",
                order=1,
            ),
        ]

        self.assertEqual(
            len(
                build_source_units(
                    concepts
                )
            ),
            2,
        )


    def test_v2d_source_units_keep_different_prices_separate(self):
        from decimal import Decimal

        from comparativas.matching_prepare import (
            build_source_units,
        )

        concepts = [
            self._v2d_fake_concept(
                pk=1,
                oferta_id=10,
                supplier_id=20,
                title="Misma partida",
                order=1,
                price=Decimal("10.00"),
            ),
            self._v2d_fake_concept(
                pk=2,
                oferta_id=10,
                supplier_id=20,
                title="Misma partida",
                order=2,
                price=Decimal("11.00"),
            ),
        ]

        self.assertEqual(
            len(
                build_source_units(
                    concepts
                )
            ),
            2,
        )


    def test_v2d_source_units_keep_scope_separate(self):
        from comparativas.matching_prepare import (
            build_source_units,
        )

        concepts = [
            self._v2d_fake_concept(
                pk=1,
                oferta_id=10,
                supplier_id=20,
                title="Contadores",
                order=1,
                alcance="INCLUIDO",
            ),
            self._v2d_fake_concept(
                pk=2,
                oferta_id=10,
                supplier_id=20,
                title="Contadores",
                order=2,
                alcance="EXCLUIDO",
            ),
        ]

        self.assertEqual(
            len(
                build_source_units(
                    concepts
                )
            ),
            2,
        )


    def test_v2d_source_units_payload_preserves_members(self):
        import json

        from comparativas.matching_prepare import (
            build_source_units,
            serialize_source_units,
        )

        concept = self._v2d_fake_concept(
            pk=7,
            oferta_id=10,
            supplier_id=20,
            title="Partida",
            order=1,
            quantity=None,
            amount=None,
            context="Sector A",
        )

        payload = serialize_source_units(
            build_source_units(
                [concept]
            )
        )

        encoded = json.dumps(
            payload,
            ensure_ascii=False,
        )

        self.assertIn(
            '"member_ids": [7]',
            encoded,
        )

        self.assertEqual(
            payload[0]["contexts"],
            ["Sector A"],
        )

        self.assertFalse(
            payload[0][
                "cantidad_completa"
            ],
        )

        self.assertFalse(
            payload[0][
                "importe_completo"
            ],
        )


    # COMPARATIVAS_V2D_MATCHING_SCHEMA_A3_R1

    def test_v2d_matching_schema_is_strict_and_versioned(self):
        from comparativas.matching_semantic import (
            MATCHING_SCHEMA_NAME,
            MATCHING_SCHEMA_V1,
        )

        self.assertEqual(
            MATCHING_SCHEMA_NAME,
            "comparativas_matching_v1",
        )

        self.assertFalse(
            MATCHING_SCHEMA_V1[
                "additionalProperties"
            ]
        )

        self.assertEqual(
            MATCHING_SCHEMA_V1[
                "properties"
            ][
                "schema_version"
            ][
                "enum"
            ],
            ["v1"],
        )

        group_schema = (
            MATCHING_SCHEMA_V1[
                "properties"
            ][
                "groups"
            ][
                "items"
            ]
        )

        self.assertFalse(
            group_schema[
                "additionalProperties"
            ]
        )

        member_schema = (
            group_schema[
                "properties"
            ][
                "members"
            ][
                "items"
            ]
        )

        self.assertFalse(
            member_schema[
                "additionalProperties"
            ]
        )


    def test_v2d_matching_validator_accepts_n_to_m(self):
        from comparativas.matching_semantic import (
            validate_matching_proposal,
        )

        fp_a = "a" * 64
        fp_b = "b" * 64

        source_units = [
            {
                "fingerprint": fp_a,
            },
            {
                "fingerprint": fp_b,
            },
        ]

        proposal = {
            "schema_version": "v1",
            "groups": [
                {
                    "key": "BANO",
                    "name": "Baño",
                    "description": "",
                    "confidence": "ALTA",
                    "explanation": (
                        "Alcance relacionado."
                    ),
                    "members": [
                        {
                            "source_fingerprint": fp_a,
                            "confidence": "ALTA",
                            "explanation": (
                                "Incluye baño."
                            ),
                        },
                        {
                            "source_fingerprint": fp_b,
                            "confidence": "ALTA",
                            "explanation": (
                                "Incluye baño."
                            ),
                        },
                    ],
                },
                {
                    "key": "MONTAJE",
                    "name": (
                        "Montaje sanitario"
                    ),
                    "description": "",
                    "confidence": "REVISAR",
                    "explanation": (
                        "Concepto agregado."
                    ),
                    "members": [
                        {
                            "source_fingerprint": fp_a,
                            "confidence": "REVISAR",
                            "explanation": (
                                "Puede cubrir montaje."
                            ),
                        }
                    ],
                },
            ],
            "unmatched": [],
        }

        result = (
            validate_matching_proposal(
                proposal,
                source_units=source_units,
            )
        )

        self.assertIs(
            result,
            proposal,
        )


    def test_v2d_matching_validator_rejects_unknown_source(self):
        from comparativas.matching_semantic import (
            MatchingProposalError,
            validate_matching_proposal,
        )

        source_units = [
            {
                "fingerprint": (
                    "a" * 64
                ),
            }
        ]

        proposal = {
            "schema_version": "v1",
            "groups": [
                {
                    "key": "X",
                    "name": "X",
                    "description": "",
                    "confidence": "ALTA",
                    "explanation": "X",
                    "members": [
                        {
                            "source_fingerprint": (
                                "b" * 64
                            ),
                            "confidence": "ALTA",
                            "explanation": "X",
                        }
                    ],
                }
            ],
            "unmatched": [],
        }

        with self.assertRaises(
            MatchingProposalError
        ) as context:
            validate_matching_proposal(
                proposal,
                source_units=source_units,
            )

        self.assertEqual(
            context.exception.code,
            "proposal_unknown_fingerprint",
        )


    def test_v2d_matching_validator_requires_full_coverage(self):
        from comparativas.matching_semantic import (
            MatchingProposalError,
            validate_matching_proposal,
        )

        source_units = [
            {
                "fingerprint": (
                    "a" * 64
                ),
            },
            {
                "fingerprint": (
                    "b" * 64
                ),
            },
        ]

        proposal = {
            "schema_version": "v1",
            "groups": [
                {
                    "key": "A",
                    "name": "A",
                    "description": "",
                    "confidence": "ALTA",
                    "explanation": "A",
                    "members": [
                        {
                            "source_fingerprint": (
                                "a" * 64
                            ),
                            "confidence": "ALTA",
                            "explanation": "A",
                        }
                    ],
                }
            ],
            "unmatched": [],
        }

        with self.assertRaises(
            MatchingProposalError
        ) as context:
            validate_matching_proposal(
                proposal,
                source_units=source_units,
            )

        self.assertEqual(
            context.exception.code,
            "proposal_incomplete_coverage",
        )


    def test_v2d_matching_adapter_uses_neutral_structured_service(self):
        from types import (
            SimpleNamespace,
        )

        from comparativas.matching_semantic import (
            proponer_matching_semantico,
        )

        fp = "a" * 64

        source_units = [
            {
                "fingerprint": fp,
                "ofertante_nombre": (
                    "Proveedor de prueba"
                ),
                "alcance": "INCLUIDO",
                "titulo": (
                    "Concepto de prueba"
                ),
                "contexts": [],
            }
        ]

        captured = {}

        def fake_requester(
            **kwargs,
        ):
            captured.update(
                kwargs
            )

            return {
                "datos": {
                    "schema_version": "v1",
                    "groups": [],
                    "unmatched": [
                        {
                            "source_fingerprint": fp,
                            "reason": (
                                "Dry run."
                            ),
                        }
                    ],
                },
                "proveedor": "mock",
            }

        result = (
            proponer_matching_semantico(
                case_title=(
                    "Comparativa"
                ),
                case_scope=(
                    "Alcance"
                ),
                source_units=source_units,
                user=SimpleNamespace(
                    pk=1
                ),
                team=SimpleNamespace(
                    pk=2
                ),
                metadata={
                    "case_id": "test",
                },
                requester=(
                    fake_requester
                ),
            )
        )

        self.assertEqual(
            result[
                "proveedor"
            ],
            "mock",
        )

        self.assertEqual(
            captured[
                "schema_name"
            ],
            "comparativas_matching_v1",
        )

        self.assertEqual(
            captured[
                "payload"
            ][
                "source_units"
            ],
            source_units,
        )

        self.assertIn(
            "N:M",
            captured[
                "instructions"
            ],
        )


# COMPARATIVAS_V2D_A5A_COMPACT_MATCHING_SCHEMA_V1

from django.test import TestCase as CompactMatchingTestCase


class CompactMatchingV1Tests(
    CompactMatchingTestCase
):
    def _sources(self):
        return [
            {
                "fingerprint": "a" * 64,
                "ofertante_nombre": "Proveedor A",
                "alcance": "INCLUIDO",
                "titulo": "Instalación baño",
                "unidad": "Ud",
                "cantidad_total": "1",
                "importe_total": "100",
                "contexts": ["Vivienda 1"],
                "source_count": 1,
            },
            {
                "fingerprint": "b" * 64,
                "ofertante_nombre": "Proveedor B",
                "alcance": "EXCLUIDO",
                "titulo": "Montaje sanitarios",
                "unidad": "",
                "cantidad_total": None,
                "importe_total": None,
                "contexts": [],
                "source_count": 1,
            },
        ]


    def test_compact_source_ids_are_deterministic(self):
        from comparativas.matching_compact import (
            build_compact_source_units,
        )

        result = build_compact_source_units(
            self._sources()
        )

        self.assertEqual(
            [
                item["source_id"]
                for item in result
            ],
            ["S01", "S02"],
        )

        self.assertNotIn(
            "fingerprint",
            result[0],
        )


    def test_compact_schema_removes_narrative_explanations(self):
        from comparativas.matching_compact import (
            COMPACT_SCHEMA_V1,
        )

        group = (
            COMPACT_SCHEMA_V1[
                "properties"
            ][
                "groups"
            ][
                "items"
            ]
        )

        self.assertNotIn(
            "description",
            group["properties"],
        )

        self.assertNotIn(
            "explanation",
            group["properties"],
        )

        member = (
            group[
                "properties"
            ][
                "members"
            ][
                "items"
            ]
        )

        self.assertNotIn(
            "explanation",
            member["properties"],
        )


    def test_compact_validator_accepts_n_to_m_when_bundled(self):
        from comparativas.matching_compact import (
            validate_compact_proposal,
        )

        proposal = {
            "version": "v1",
            "groups": [
                {
                    "key": "BANO",
                    "name": "Baño",
                    "confidence": "ALTA",
                    "members": [
                        {
                            "source_id": "S01",
                            "confidence": "ALTA",
                            "relation": "BUNDLED",
                        }
                    ],
                },
                {
                    "key": "MONTAJE",
                    "name": "Montaje",
                    "confidence": "REVISAR",
                    "members": [
                        {
                            "source_id": "S01",
                            "confidence": "REVISAR",
                            "relation": "BUNDLED",
                        }
                    ],
                },
            ],
            "unmatched": [
                "S02",
            ],
        }

        self.assertIs(
            validate_compact_proposal(
                proposal,
                source_units=self._sources(),
            ),
            proposal,
        )


    def test_compact_validator_rejects_n_to_m_without_bundled(self):
        from comparativas.matching_semantic import (
            MatchingProposalError,
        )
        from comparativas.matching_compact import (
            validate_compact_proposal,
        )

        proposal = {
            "version": "v1",
            "groups": [
                {
                    "key": "A",
                    "name": "A",
                    "confidence": "ALTA",
                    "members": [
                        {
                            "source_id": "S01",
                            "confidence": "ALTA",
                            "relation": "DIRECT",
                        }
                    ],
                },
                {
                    "key": "B",
                    "name": "B",
                    "confidence": "ALTA",
                    "members": [
                        {
                            "source_id": "S01",
                            "confidence": "ALTA",
                            "relation": "PARTIAL",
                        }
                    ],
                },
            ],
            "unmatched": [
                "S02",
            ],
        }

        with self.assertRaises(
            MatchingProposalError
        ) as context:
            validate_compact_proposal(
                proposal,
                source_units=self._sources(),
            )

        self.assertEqual(
            context.exception.code,
            "compact_n_to_m_requires_bundled",
        )


    def test_compact_validator_requires_full_coverage(self):
        from comparativas.matching_semantic import (
            MatchingProposalError,
        )
        from comparativas.matching_compact import (
            validate_compact_proposal,
        )

        proposal = {
            "version": "v1",
            "groups": [
                {
                    "key": "A",
                    "name": "A",
                    "confidence": "ALTA",
                    "members": [
                        {
                            "source_id": "S01",
                            "confidence": "ALTA",
                            "relation": "DIRECT",
                        }
                    ],
                }
            ],
            "unmatched": [],
        }

        with self.assertRaises(
            MatchingProposalError
        ) as context:
            validate_compact_proposal(
                proposal,
                source_units=self._sources(),
            )

        self.assertEqual(
            context.exception.code,
            "compact_incomplete_coverage",
        )


    def test_compact_expansion_restores_fingerprints(self):
        from comparativas.matching_compact import (
            expand_compact_proposal,
        )

        proposal = {
            "version": "v1",
            "groups": [
                {
                    "key": "BANO",
                    "name": "Baño",
                    "confidence": "ALTA",
                    "members": [
                        {
                            "source_id": "S01",
                            "confidence": "ALTA",
                            "relation": "DIRECT",
                        }
                    ],
                }
            ],
            "unmatched": [
                "S02",
            ],
        }

        expanded = (
            expand_compact_proposal(
                proposal,
                source_units=self._sources(),
            )
        )

        self.assertEqual(
            expanded[
                "groups"
            ][0][
                "members"
            ][0][
                "source_fingerprint"
            ],
            "a" * 64,
        )

        self.assertEqual(
            expanded[
                "unmatched"
            ][0][
                "source_fingerprint"
            ],
            "b" * 64,
        )


# COMPARATIVAS_V2D_A5C_ATOMIC_MATRIX_SCHEMA_V2

from django.test import TestCase as AtomicMatrixTestCase


class AtomicMatrixV2Tests(
    AtomicMatrixTestCase
):
    def _sources(self):
        return [
            {
                "fingerprint": "a" * 64,
                "ofertante_nombre": "Proveedor A",
                "alcance": "INCLUIDO",
                "titulo": "Partida A",
                "unidad": "Ud",
                "cantidad_total": "1",
                "importe_total": "100",
                "contexts": [],
                "source_count": 1,
            },
            {
                "fingerprint": "b" * 64,
                "ofertante_nombre": "Proveedor B",
                "alcance": "EXCLUIDO",
                "titulo": "Partida B",
                "unidad": "",
                "cantidad_total": None,
                "importe_total": None,
                "contexts": [],
                "source_count": 1,
            },
        ]


    def _groups(self):
        return [
            {
                "key": "grupo_a",
                "name": "Grupo A",
                "confidence": "ALTA",
            }
        ]


    def test_atomic_schema_requires_every_source_id(self):
        from comparativas.matching_atomic import (
            build_atomic_schema,
        )

        schema = build_atomic_schema(
            ["S01", "S02"]
        )

        assignments = (
            schema[
                "properties"
            ][
                "assignments"
            ]
        )

        self.assertEqual(
            assignments["required"],
            ["S01", "S02"],
        )

        self.assertFalse(
            assignments[
                "additionalProperties"
            ]
        )


    def test_atomic_validator_accepts_explicit_unmatched_empty_array(self):
        from comparativas.matching_atomic import (
            validate_atomic_proposal,
        )

        proposal = {
            "version": "v2",
            "groups": self._groups(),
            "assignments": {
                "S01": [
                    {
                        "group_key": "grupo_a",
                        "confidence": "ALTA",
                        "relation": "DIRECT",
                    }
                ],
                "S02": [],
            },
        }

        self.assertIs(
            validate_atomic_proposal(
                proposal,
                source_units=self._sources(),
            ),
            proposal,
        )


    def test_atomic_validator_rejects_missing_source_property(self):
        from comparativas.matching_atomic import (
            validate_atomic_proposal,
        )
        from comparativas.matching_semantic import (
            MatchingProposalError,
        )

        proposal = {
            "version": "v2",
            "groups": self._groups(),
            "assignments": {
                "S01": [
                    {
                        "group_key": "grupo_a",
                        "confidence": "ALTA",
                        "relation": "DIRECT",
                    }
                ],
            },
        }

        with self.assertRaises(
            MatchingProposalError
        ) as context:
            validate_atomic_proposal(
                proposal,
                source_units=self._sources(),
            )

        self.assertEqual(
            context.exception.code,
            "atomic_source_missing",
        )


    def test_atomic_validator_rejects_extra_source_property(self):
        from comparativas.matching_atomic import (
            validate_atomic_proposal,
        )
        from comparativas.matching_semantic import (
            MatchingProposalError,
        )

        proposal = {
            "version": "v2",
            "groups": self._groups(),
            "assignments": {
                "S01": [
                    {
                        "group_key": "grupo_a",
                        "confidence": "ALTA",
                        "relation": "DIRECT",
                    }
                ],
                "S02": [],
                "S99": [],
            },
        }

        with self.assertRaises(
            MatchingProposalError
        ) as context:
            validate_atomic_proposal(
                proposal,
                source_units=self._sources(),
            )

        self.assertEqual(
            context.exception.code,
            "atomic_source_extra",
        )


    def test_atomic_validator_rejects_unknown_group_reference(self):
        from comparativas.matching_atomic import (
            validate_atomic_proposal,
        )
        from comparativas.matching_semantic import (
            MatchingProposalError,
        )

        proposal = {
            "version": "v2",
            "groups": self._groups(),
            "assignments": {
                "S01": [
                    {
                        "group_key": "inexistente",
                        "confidence": "ALTA",
                        "relation": "DIRECT",
                    }
                ],
                "S02": [],
            },
        }

        with self.assertRaises(
            MatchingProposalError
        ) as context:
            validate_atomic_proposal(
                proposal,
                source_units=self._sources(),
            )

        self.assertEqual(
            context.exception.code,
            "atomic_unknown_group",
        )


    def test_atomic_validator_rejects_duplicate_group_keys(self):
        from comparativas.matching_atomic import (
            validate_atomic_proposal,
        )
        from comparativas.matching_semantic import (
            MatchingProposalError,
        )

        proposal = {
            "version": "v2",
            "groups": [
                {
                    "key": "x",
                    "name": "X",
                    "confidence": "ALTA",
                },
                {
                    "key": "x",
                    "name": "X2",
                    "confidence": "REVISAR",
                },
            ],
            "assignments": {
                "S01": [
                    {
                        "group_key": "x",
                        "confidence": "ALTA",
                        "relation": "DIRECT",
                    }
                ],
                "S02": [],
            },
        }

        with self.assertRaises(
            MatchingProposalError
        ) as context:
            validate_atomic_proposal(
                proposal,
                source_units=self._sources(),
            )

        self.assertEqual(
            context.exception.code,
            "atomic_group_key_duplicate",
        )


    def test_atomic_validator_rejects_n_to_m_without_bundled(self):
        from comparativas.matching_atomic import (
            validate_atomic_proposal,
        )
        from comparativas.matching_semantic import (
            MatchingProposalError,
        )

        proposal = {
            "version": "v2",
            "groups": [
                {
                    "key": "a",
                    "name": "A",
                    "confidence": "ALTA",
                },
                {
                    "key": "b",
                    "name": "B",
                    "confidence": "ALTA",
                },
            ],
            "assignments": {
                "S01": [
                    {
                        "group_key": "a",
                        "confidence": "ALTA",
                        "relation": "DIRECT",
                    },
                    {
                        "group_key": "b",
                        "confidence": "ALTA",
                        "relation": "PARTIAL",
                    },
                ],
                "S02": [],
            },
        }

        with self.assertRaises(
            MatchingProposalError
        ) as context:
            validate_atomic_proposal(
                proposal,
                source_units=self._sources(),
            )

        self.assertEqual(
            context.exception.code,
            "atomic_n_to_m_requires_bundled",
        )


    def test_atomic_validator_rejects_single_bundled(self):
        from comparativas.matching_atomic import (
            validate_atomic_proposal,
        )
        from comparativas.matching_semantic import (
            MatchingProposalError,
        )

        proposal = {
            "version": "v2",
            "groups": self._groups(),
            "assignments": {
                "S01": [
                    {
                        "group_key": "grupo_a",
                        "confidence": "ALTA",
                        "relation": "BUNDLED",
                    }
                ],
                "S02": [],
            },
        }

        with self.assertRaises(
            MatchingProposalError
        ) as context:
            validate_atomic_proposal(
                proposal,
                source_units=self._sources(),
            )

        self.assertEqual(
            context.exception.code,
            "atomic_single_cannot_be_bundled",
        )


    def test_atomic_expansion_restores_fingerprints(self):
        from comparativas.matching_atomic import (
            expand_atomic_proposal,
        )

        proposal = {
            "version": "v2",
            "groups": self._groups(),
            "assignments": {
                "S01": [
                    {
                        "group_key": "grupo_a",
                        "confidence": "ALTA",
                        "relation": "DIRECT",
                    }
                ],
                "S02": [],
            },
        }

        result = expand_atomic_proposal(
            proposal,
            source_units=self._sources(),
        )

        self.assertEqual(
            result[
                "assignments"
            ][0][
                "source_fingerprint"
            ],
            "a" * 64,
        )

        self.assertEqual(
            result[
                "assignments"
            ][1][
                "source_fingerprint"
            ],
            "b" * 64,
        )


# COMPARATIVAS_V2D_EXECUTIVE_IA_V1

from django.test import (
    SimpleTestCase
    as ExecutiveIASimpleTestCase,
)


class ExecutiveIAV1Tests(
    ExecutiveIASimpleTestCase
):
    def _report(self):
        return {
            "version": "v1",
            "resumen": (
                "Las ofertas requieren "
                "comparar alcance además "
                "del precio."
            ),
            "por_oferta": [
                {
                    "oferta_id": 10,
                    "comparabilidad": "ALTA",
                    "comentario": (
                        "Alcance suficientemente "
                        "definido."
                    ),
                },
                {
                    "oferta_id": 20,
                    "comparabilidad": "MEDIA",
                    "comentario": (
                        "Requiere aclaraciones."
                    ),
                },
            ],
            "diferencias_clave": [
                "Existen diferencias de alcance."
            ],
            "riesgos_y_aclaraciones": [
                "Confirmar exclusiones."
            ],
            "opcion_orientativa_oferta_id": 10,
            "recomendacion": (
                "Revisar alcance antes "
                "de contratar."
            ),
        }


    def test_executive_schema_is_strict_and_bounded(
        self,
    ):
        from comparativas.executive_ia import (
            build_executive_schema,
        )

        schema = build_executive_schema(
            [10, 20]
        )

        self.assertFalse(
            schema[
                "additionalProperties"
            ]
        )

        offers = (
            schema[
                "properties"
            ][
                "por_oferta"
            ]
        )

        self.assertEqual(
            offers["minItems"],
            2,
        )

        self.assertEqual(
            offers["maxItems"],
            2,
        )

        self.assertEqual(
            offers[
                "items"
            ][
                "properties"
            ][
                "oferta_id"
            ][
                "enum"
            ],
            [10, 20],
        )


    def test_executive_validator_requires_exact_offer_coverage(
        self,
    ):
        from comparativas.executive_ia import (
            ExecutiveIAError,
            validate_executive_report,
        )

        report = self._report()

        report["por_oferta"] = [
            report["por_oferta"][0],
            dict(
                report["por_oferta"][0]
            ),
        ]

        with self.assertRaises(
            ExecutiveIAError
        ):
            validate_executive_report(
                report,
                offer_ids=[10, 20],
            )


    def test_executive_validator_accepts_valid_report(
        self,
    ):
        from comparativas.executive_ia import (
            validate_executive_report,
        )

        report = self._report()

        self.assertIs(
            validate_executive_report(
                report,
                offer_ids=[10, 20],
            ),
            report,
        )


    def test_executive_request_uses_neutral_structured_service_contract(
        self,
    ):
        from comparativas.executive_ia import (
            request_executive_report,
        )

        calls = []

        report = self._report()

        def fake_requester(
            **kwargs,
        ):
            calls.append(kwargs)

            return {
                "datos": report,
                "proveedor": "fake",
            }

        prepared = {
            "can_generate": True,
            "offer_ids": [10, 20],
            "source_units_count": 7,
            "payload": {
                "expediente": {
                    "titulo": "Prueba",
                },
                "ofertas": [],
            },
        }

        result = (
            request_executive_report(
                prepared=prepared,
                user=object(),
                team=None,
                requester=fake_requester,
            )
        )

        self.assertEqual(
            len(calls),
            1,
        )

        self.assertEqual(
            calls[0][
                "schema_name"
            ],
            (
                "comparativas_"
                "executive_v1"
            ),
        )

        self.assertIn(
            "instructions",
            calls[0],
        )

        self.assertIn(
            "payload",
            calls[0],
        )

        self.assertIs(
            result["datos"],
            report,
        )


# COMPARATIVAS_V2D_EXECUTIVE_IA_V1_1_SHORT_PRINT

from django.test import (
    SimpleTestCase
    as ExecutiveIAV11SimpleTestCase,
)


class ExecutiveIAV11Tests(
    ExecutiveIAV11SimpleTestCase
):

    def test_executive_schema_is_short_for_one_page_report(
        self,
    ):
        from comparativas.executive_ia import (
            build_executive_schema,
        )

        schema = build_executive_schema(
            [1, 2, 3, 4, 5]
        )

        props = schema[
            "properties"
        ]

        self.assertEqual(
            props["resumen"]["maxLength"],
            300,
        )

        self.assertEqual(
            props[
                "diferencias_clave"
            ]["maxItems"],
            2,
        )

        self.assertEqual(
            props[
                "riesgos_y_aclaraciones"
            ]["maxItems"],
            2,
        )

        self.assertEqual(
            props[
                "recomendacion"
            ]["maxLength"],
            280,
        )


    def test_executive_instructions_define_real_comparability(
        self,
    ):
        from comparativas.executive_ia import (
            build_executive_instructions,
        )

        text = (
            build_executive_instructions()
        )

        self.assertIn(
            "NO significa que el presupuesto esté",
            text,
        )

        self.assertIn(
            "mayor detalle documental",
            text,
        )

        self.assertIn(
            "opcion_orientativa_oferta_id = 0",
            text,
        )

        self.assertIn(
            'Nunca escribas "oferta 1"',
            text,
        )


    def test_executive_schema_supports_fifth_offer_dynamically(
        self,
    ):
        from comparativas.executive_ia import (
            build_executive_schema,
        )

        ids = [
            10,
            20,
            30,
            40,
            50,
        ]

        schema = build_executive_schema(
            ids
        )

        per_offer = (
            schema[
                "properties"
            ][
                "por_oferta"
            ]
        )

        self.assertEqual(
            per_offer["minItems"],
            5,
        )

        self.assertEqual(
            per_offer["maxItems"],
            5,
        )

        self.assertEqual(
            per_offer[
                "items"
            ][
                "properties"
            ][
                "oferta_id"
            ][
                "enum"
            ],
            ids,
        )


# COMPARATIVAS_V2D_EXECUTIVE_IA_V1_2_CALL_HEADROOM

from django.test import (
    SimpleTestCase
    as ExecutiveIAV12SimpleTestCase,
)


class ExecutiveIAV12Tests(
    ExecutiveIAV12SimpleTestCase
):

    def test_executive_call_requests_specific_headroom(
        self,
    ):
        from comparativas.executive_ia import (
            request_executive_report,
        )

        calls = []

        report = {
            "version": "v1",
            "resumen": "Resumen.",
            "por_oferta": [
                {
                    "oferta_id": 10,
                    "comparabilidad": "MEDIA",
                    "comentario": "Revisar.",
                },
                {
                    "oferta_id": 20,
                    "comparabilidad": "MEDIA",
                    "comentario": "Revisar.",
                },
            ],
            "diferencias_clave": [
                "Diferencia."
            ],
            "riesgos_y_aclaraciones": [],
            "opcion_orientativa_oferta_id": 0,
            "recomendacion": "Revisar.",
        }

        def fake_requester(**kwargs):
            calls.append(kwargs)
            return {
                "datos": report,
            }

        prepared = {
            "can_generate": True,
            "offer_ids": [10, 20],
            "source_units_count": 2,
            "payload": {
                "expediente": {},
                "ofertas": [],
            },
        }

        request_executive_report(
            prepared=prepared,
            user=object(),
            requester=fake_requester,
        )

        self.assertEqual(
            calls[0][
                "max_output_tokens"
            ],
            2000,
        )

        self.assertEqual(
            calls[0][
                "timeout_seconds"
            ],
            90,
        )


# COMPARATIVAS_V2D_EXECUTIVE_IA_V1_3_COMPLETE_SENTENCES_R2

from django.test import (
    SimpleTestCase
    as ExecutiveIAV13SimpleTestCase,
)


class ExecutiveIAV13Tests(
    ExecutiveIAV13SimpleTestCase
):

    def test_executive_schema_allows_complete_short_sentences(
        self,
    ):
        from comparativas.executive_ia import (
            build_executive_schema,
        )

        schema = build_executive_schema(
            [1, 2, 3, 4]
        )

        props = schema["properties"]

        self.assertEqual(
            props["resumen"]["maxLength"],
            300,
        )

        self.assertEqual(
            props[
                "por_oferta"
            ][
                "items"
            ][
                "properties"
            ][
                "comentario"
            ][
                "maxLength"
            ],
            180,
        )

        self.assertEqual(
            props[
                "diferencias_clave"
            ][
                "maxItems"
            ],
            2,
        )

        self.assertEqual(
            props[
                "diferencias_clave"
            ][
                "items"
            ][
                "maxLength"
            ],
            180,
        )

        self.assertEqual(
            props[
                "riesgos_y_aclaraciones"
            ][
                "maxItems"
            ],
            2,
        )

        self.assertEqual(
            props[
                "riesgos_y_aclaraciones"
            ][
                "items"
            ][
                "maxLength"
            ],
            180,
        )

        self.assertEqual(
            props[
                "recomendacion"
            ][
                "maxLength"
            ],
            280,
        )


    def test_executive_instructions_require_complete_sentences(
        self,
    ):
        from comparativas.executive_ia import (
            build_executive_instructions,
        )

        text = build_executive_instructions()

        self.assertIn(
            "Nunca cortes una",
            text,
        )

        self.assertIn(
            "resúmela antes de alcanzar",
            text,
        )


# COMPARATIVAS_V2C_UNVALUED_SCOPE_BLOCKS_V1

from django.test import (
    SimpleTestCase
    as UnvaluedScopeSimpleTestCase,
)


class UnvaluedScopeExtractionTests(
    UnvaluedScopeSimpleTestCase
):

    SAMPLE = "\n".join(
        [
            "PRESUPUESTO 094/2026",
            "EMPRESA DE INSTALACIONES",
            "NIF: 12345678Z",
            "CLIENTE: EMPRESA CLIENTE SL",
            "Descripción:",
            (
                "Instalacion de 18 puntos "
                "de agua. Sistema multicapa."
            ),
            (
                "Llaves de corte "
                "independizando las zonas "
                "de las viviendas."
            ),
            (
                "Generales con llaves de "
                "corte en zonas comunes."
            ),
            (
                "Desembarco de aguas "
                "sucias en pvc."
            ),
            "TOTAL........4140/EUROS",
            (
                "Perforacion de forjados "
                "para instalacion de tubos "
                "de pvc......1800/Euros"
            ),
            (
                "TOTAL DEL BRUTO"
                "........5940/EUROS"
            ),
            (
                "21% IVA"
                "........1247,4/EUROS"
            ),
            (
                "TOTAL DEL PAGO"
                "........7187,4/EUROS"
            ),
            (
                "Se abonara el 50% "
                "a la contratacion."
            ),
        ]
    )


    def test_description_section_preserves_unvalued_scope(
        self,
    ):
        from decimal import Decimal

        from comparativas.concept_extraction import (
            extract_text_concepts,
        )

        concepts = (
            extract_text_concepts(
                self.SAMPLE
            )
        )

        included = [
            item
            for item in concepts
            if item["alcance"]
            == "INCLUIDO"
        ]

        self.assertEqual(
            len(included),
            5,
        )

        self.assertEqual(
            [
                item["importe"]
                for item in included[:4]
            ],
            [
                None,
                None,
                None,
                None,
            ],
        )

        self.assertEqual(
            included[4]["importe"],
            Decimal("1800"),
        )

        for item in included[:4]:
            self.assertEqual(
                item["contexto"],
                (
                    "TOTAL DE BLOQUE "
                    "DOCUMENTAL: "
                    "4140.00 EUR"
                ),
            )


    def test_totals_tax_and_payment_are_not_concepts(
        self,
    ):
        from comparativas.concept_extraction import (
            extract_text_concepts,
        )

        concepts = (
            extract_text_concepts(
                self.SAMPLE
            )
        )

        titles = " | ".join(
            item["titulo"].upper()
            for item in concepts
        )

        self.assertNotIn(
            "TOTAL DEL BRUTO",
            titles,
        )

        self.assertNotIn(
            "TOTAL DEL PAGO",
            titles,
        )

        self.assertNotIn(
            "21% IVA",
            titles,
        )

        self.assertNotIn(
            "SE ABONARA",
            titles,
        )

        self.assertNotIn(
            "EMPRESA CLIENTE",
            titles,
        )


    def test_known_amount_remains_partial_without_inventing_distribution(
        self,
    ):
        from decimal import Decimal

        from comparativas.concept_extraction import (
            extract_concepts_preview,
        )

        preview = (
            extract_concepts_preview(
                text=self.SAMPLE,
                base=Decimal(
                    "5940.00"
                ),
            )
        )

        reconciliation = (
            preview[
                "reconciliacion"
            ]
        )

        self.assertEqual(
            reconciliation["estado"],
            "PARCIAL",
        )

        self.assertEqual(
            reconciliation[
                "suma_conceptos"
            ],
            Decimal("1800"),
        )

        self.assertEqual(
            reconciliation[
                "diferencia"
            ],
            Decimal("-4140.00"),
        )


# COMPARATIVAS_EXECUTIVE_IA_V1_5_GOVERNED

from django.test import (
    SimpleTestCase
    as ExecutiveIAV15SimpleTestCase,
)


class ExecutiveIAV15Tests(
    ExecutiveIAV15SimpleTestCase
):

    def _report(
        self,
        per_offer,
        option_id=0,
    ):
        return {
            "version": "v1",
            "resumen": (
                "Comparativa ejecutiva."
            ),
            "por_oferta": per_offer,
            "diferencias_clave": [
                "Diferencia principal."
            ],
            "riesgos_y_aclaraciones": [
                "Aclaración principal."
            ],
            "opcion_orientativa_oferta_id": (
                option_id
            ),
            "recomendacion": (
                "Texto IA."
            ),
        }


    def test_governance_ignores_ai_option(
        self,
    ):
        from decimal import Decimal

        from comparativas.executive_ia import (
            govern_executive_report,
        )

        prepared = {
            "rows": [
                {
                    "oferta_id": 10,
                    "nombre": "Proveedor A",
                    "base": Decimal(
                        "6252.40"
                    ),
                    "moneda": "EUR",
                },
                {
                    "oferta_id": 20,
                    "nombre": "Proveedor B",
                    "base": Decimal(
                        "6500.00"
                    ),
                    "moneda": "EUR",
                },
                {
                    "oferta_id": 30,
                    "nombre": (
                        "Proveedor detallado"
                    ),
                    "base": Decimal(
                        "11281.46"
                    ),
                    "moneda": "EUR",
                },
                {
                    "oferta_id": 50,
                    "nombre": "Proveedor barato",
                    "base": Decimal(
                        "5940.00"
                    ),
                    "moneda": "EUR",
                },
            ],
        }

        report = self._report(
            [
                {
                    "oferta_id": 10,
                    "comparabilidad": "ALTA",
                    "comentario": "Alta.",
                },
                {
                    "oferta_id": 20,
                    "comparabilidad": "ALTA",
                    "comentario": "Alta.",
                },
                {
                    "oferta_id": 30,
                    "comparabilidad": "ALTA",
                    "comentario": (
                        "Muy detallada."
                    ),
                },
                {
                    "oferta_id": 50,
                    "comparabilidad": "BAJA",
                    "comentario": (
                        "Alcance insuficiente."
                    ),
                },
            ],
            option_id=30,
        )

        governed = (
            govern_executive_report(
                prepared=prepared,
                report=report,
            )
        )

        self.assertEqual(
            governed[
                "opcion_orientativa_oferta_id"
            ],
            10,
        )

        self.assertIn(
            "Proveedor A",
            governed[
                "recomendacion"
            ],
        )


    def test_cheaper_medium_does_not_block_high_option(
        self,
    ):
        from decimal import Decimal

        from comparativas.executive_ia import (
            govern_executive_report,
        )

        prepared = {
            "rows": [
                {
                    "oferta_id": 10,
                    "nombre": "Alta",
                    "base": Decimal(
                        "7000.00"
                    ),
                    "impuestos": Decimal(
                        "1470.00"
                    ),
                    "moneda": "EUR",
                },
                {
                    "oferta_id": 20,
                    "nombre": "Media",
                    "base": Decimal(
                        "6000.00"
                    ),
                    "impuestos": Decimal(
                        "1260.00"
                    ),
                    "moneda": "EUR",
                },
            ],
        }

        report = self._report(
            [
                {
                    "oferta_id": 10,
                    "comparabilidad": "ALTA",
                    "comentario": "Alta.",
                },
                {
                    "oferta_id": 20,
                    "comparabilidad": "MEDIA",
                    "comentario": "Media.",
                },
            ]
        )

        governed = (
            govern_executive_report(
                prepared=prepared,
                report=report,
            )
        )

        self.assertEqual(
            governed[
                "opcion_orientativa_oferta_id"
            ],
            10,
        )

        self.assertIn(
            "Media",
            governed[
                "recomendacion"
            ],
        )

        self.assertIn(
            "1.000,00 €",
            governed[
                "recomendacion"
            ],
        )


    def test_mixed_currency_has_no_option(
        self,
    ):
        from decimal import Decimal

        from comparativas.executive_ia import (
            govern_executive_report,
        )

        prepared = {
            "rows": [
                {
                    "oferta_id": 10,
                    "nombre": "EUR",
                    "base": Decimal(
                        "6000.00"
                    ),
                    "moneda": "EUR",
                },
                {
                    "oferta_id": 20,
                    "nombre": "USD",
                    "base": Decimal(
                        "5000.00"
                    ),
                    "moneda": "USD",
                },
            ],
        }

        report = self._report(
            [
                {
                    "oferta_id": 10,
                    "comparabilidad": "ALTA",
                    "comentario": "Alta.",
                },
                {
                    "oferta_id": 20,
                    "comparabilidad": "ALTA",
                    "comentario": "Alta.",
                },
            ]
        )

        governed = (
            govern_executive_report(
                prepared=prepared,
                report=report,
            )
        )

        self.assertEqual(
            governed[
                "opcion_orientativa_oferta_id"
            ],
            0,
        )


    def test_truncated_text_returns_complete_sentence(
        self,
    ):
        from comparativas.executive_ia import (
            _complete_fragment,
        )

        value = (
            "Primera frase completa. "
            "Segunda frase queda cortada "
            "en una pala"
        )

        result = _complete_fragment(
            value,
            limit=len(value),
        )

        self.assertEqual(
            result,
            "Primera frase completa.",
        )


    def test_ai_contract_forbids_supplier_choice(
        self,
    ):
        from comparativas.executive_ia import (
            build_executive_instructions,
        )

        text = (
            build_executive_instructions()
        )

        self.assertIn(
            "NO eliges proveedor",
            text,
        )

        self.assertIn(
            "opcion_orientativa_oferta_id = 0",
            text,
        )

        self.assertIn(
            "regla local y determinista",
            text,
        )


# COMPARATIVAS_EXECUTIVE_IA_V1_6_EXECUTIVE_CONCLUSION

from django.test import (
    SimpleTestCase
    as ExecutiveIAV16SimpleTestCase,
)


class ExecutiveIAV16Tests(
    ExecutiveIAV16SimpleTestCase
):

    def _report(
        self,
        items,
    ):
        return {
            "version": "v1",
            "resumen": "Resumen.",
            "por_oferta": items,
            "diferencias_clave": [
                "Diferencia."
            ],
            "riesgos_y_aclaraciones": [
                "Riesgo."
            ],
            "opcion_orientativa_oferta_id": 0,
            "recomendacion": (
                "La IA no decide."
            ),
        }


    def test_selects_lowest_base_among_high(
        self,
    ):
        from decimal import Decimal

        from comparativas.executive_ia import (
            govern_executive_report,
        )

        prepared = {
            "rows": [
                {
                    "oferta_id": 1,
                    "nombre": "Alta barata",
                    "base": Decimal(
                        "6252.40"
                    ),
                    "impuestos": None,
                    "moneda": "EUR",
                },
                {
                    "oferta_id": 2,
                    "nombre": "Alta segunda",
                    "base": Decimal(
                        "6890.00"
                    ),
                    "impuestos": Decimal(
                        "1446.90"
                    ),
                    "moneda": "EUR",
                },
                {
                    "oferta_id": 3,
                    "nombre": "Media barata",
                    "base": Decimal(
                        "5940.00"
                    ),
                    "impuestos": Decimal(
                        "1247.40"
                    ),
                    "moneda": "EUR",
                },
            ],
        }

        report = self._report(
            [
                {
                    "oferta_id": 1,
                    "comparabilidad": "ALTA",
                    "comentario": "Alta.",
                },
                {
                    "oferta_id": 2,
                    "comparabilidad": "ALTA",
                    "comentario": "Alta.",
                },
                {
                    "oferta_id": 3,
                    "comparabilidad": "MEDIA",
                    "comentario": "Media.",
                },
            ]
        )

        result = govern_executive_report(
            prepared=prepared,
            report=report,
        )

        self.assertEqual(
            result[
                "opcion_orientativa_oferta_id"
            ],
            1,
        )

        text = result[
            "recomendacion"
        ]

        self.assertIn(
            "Alta barata",
            text,
        )

        self.assertIn(
            "6.252,40 €",
            text,
        )

        self.assertIn(
            "Alta segunda",
            text,
        )

        self.assertIn(
            "637,60 € más",
            text,
        )

        self.assertIn(
            "Media barata",
            text,
        )

        self.assertIn(
            "312,40 €",
            text,
        )

        self.assertIn(
            "impuestos",
            text,
        )


    def test_medium_never_becomes_option_without_high(
        self,
    ):
        from decimal import Decimal

        from comparativas.executive_ia import (
            govern_executive_report,
        )

        prepared = {
            "rows": [
                {
                    "oferta_id": 1,
                    "nombre": "Media uno",
                    "base": Decimal(
                        "5000.00"
                    ),
                    "impuestos": None,
                    "moneda": "EUR",
                },
                {
                    "oferta_id": 2,
                    "nombre": "Media dos",
                    "base": Decimal(
                        "6000.00"
                    ),
                    "impuestos": None,
                    "moneda": "EUR",
                },
            ],
        }

        report = self._report(
            [
                {
                    "oferta_id": 1,
                    "comparabilidad": "MEDIA",
                    "comentario": "Media.",
                },
                {
                    "oferta_id": 2,
                    "comparabilidad": "MEDIA",
                    "comentario": "Media.",
                },
            ]
        )

        result = govern_executive_report(
            prepared=prepared,
            report=report,
        )

        self.assertEqual(
            result[
                "opcion_orientativa_oferta_id"
            ],
            0,
        )


    def test_prompt_defines_comparability_levels(
        self,
    ):
        from comparativas.executive_ia import (
            build_executive_instructions,
        )

        text = (
            build_executive_instructions()
        )

        self.assertIn(
            "ALTA =",
            text,
        )

        self.assertIn(
            "MEDIA =",
            text,
        )

        self.assertIn(
            "BAJA =",
            text,
        )

        self.assertIn(
            "NO_DETERMINABLE =",
            text,
        )


# COMPARATIVAS_PRESUPUESTO_HEADER_RELIABILITY_V1_R2C

from django.test import (
    SimpleTestCase
    as HeaderReliabilityR2CSimpleTestCase,
)


class PresupuestoHeaderReliabilityR2CTests(
    HeaderReliabilityR2CSimpleTestCase
):

    def test_inline_base_iva_total_reconciles(
        self,
    ):
        from comparativas.presupuesto_import import (
            _find_totals,
        )

        result = _find_totals(
            (
                "Importe 4.800,00 €"
                "IVA 21% 1.008,00 €"
                "Importe total 5.808,00 €"
            )
        )

        self.assertEqual(
            result,
            {
                "base": "4800.00",
                "iva": "1008.00",
                "total": "5808.00",
            },
        )


    def test_derivacion_is_not_iva(
        self,
    ):
        from comparativas.presupuesto_import import (
            _find_totals,
        )

        result = _find_totals(
            (
                "Derivación individual "
                "3x10mm2 3 185,00 555,00"
            )
        )

        self.assertEqual(
            result["iva"],
            "",
        )


    def test_degraded_economic_block_fails_closed(
        self,
    ):
        from comparativas.presupuesto_import import (
            _find_totals,
        )

        result = _find_totals(
            (
                "BASE LVA. 7.552,00 "
                "CUOTA VAG 585,92 "
                "TOTAL PREV'G*4 37,92 Euros"
            )
        )

        self.assertEqual(
            result,
            {
                "base": "",
                "iva": "",
                "total": "",
            },
        )


    def test_fecha_validez_uses_first_date(
        self,
    ):
        from comparativas.presupuesto_import import (
            _find_document_date,
        )

        self.assertEqual(
            _find_document_date(
                (
                    "Fecha Valido hasta"
                    "16/8/2026 16/9/2026"
                )
            ),
            "2026-08-16",
        )


    def test_budget_reference_with_noisy_marker(
        self,
    ):
        from comparativas.presupuesto_import import (
            _find_reference,
        )

        self.assertEqual(
            _find_reference(
                (
                    "PRESUPUESTO N* 26-047 "
                    "FECHA 04/08/2026"
                )
            ),
            "26-047",
        )


    def test_budget_reference_beats_electrical_specification(
        self,
    ):
        from comparativas.presupuesto_import import (
            _find_reference,
        )

        result = _find_reference(
            (
                "FECHA 05/08/2026 "
                "Ne. PRESUPUESTO) $ 126069 "
                "N.LE CLIENTE\n"
                "DIFERENCIAL 2P/40A/30mA"
            )
        )

        self.assertEqual(
            result,
            "126069",
        )


    def test_phone_and_postal_address_are_not_supplier(
        self,
    ):
        from comparativas.presupuesto_import import (
            _guess_supplier_name,
        )

        text = """
        Electricidad
        Duero, S.L.
        Condes de Alba y Aliste, 14 49007 ZAMORA
        Mv.: 689 14 30 87 + Teléf.: 980 52 58 14
        info@example.test
        C.I.F. B-49.166.598
        """

        result = _guess_supplier_name(
            text,
            ["B49166598"],
        )

        self.assertEqual(
            result,
            "Duero, S.L.",
        )


    def test_client_address_is_not_supplier(
        self,
    ):
        from comparativas.presupuesto_import import (
            _guess_supplier_name,
        )

        result = _guess_supplier_name(
            """
            CLIENTE
            CLIENTE INDUSTRIAL
            electricidad AVD DE PORTUGAL N°20
            Avda. Portugal, n° 13 - Bajo
            electricidad@example.test
            """,
            [],
        )

        self.assertNotIn(
            "AVD DE PORTUGAL",
            result.upper(),
        )


    def test_degraded_footer_is_not_concept(
        self,
    ):
        from comparativas.concept_extraction import (
            extract_text_concepts,
        )

        result = extract_text_concepts(
            """
            3 CERTIFICADO DE INSTALACION
            ELECTRICA 150,00 450,00
            2 INCREMENTARIA EN UN 20% :
            BASE LVA. 7.552,00 CUOTA VAG
            585,92 TOTAL PREV'G*4 37,92 Euros
            """
        )

        self.assertFalse(
            any(
                item.get("importe")
                == 37.92
                for item in result
            )
        )

        self.assertFalse(
            any(
                "TOTAL PREV"
                in (
                    item.get("titulo")
                    or ""
                ).upper()
                for item in result
            )
        )


# COMPARATIVAS_PRESUPUESTO_HEADER_RELIABILITY_V1_R2D

from django.test import (
    SimpleTestCase
    as HeaderReliabilityR2DSimpleTestCase,
)


class PresupuestoHeaderReliabilityR2DTests(
    HeaderReliabilityR2DSimpleTestCase
):

    def test_multiline_economic_footer_is_fully_excluded(
        self,
    ):
        from comparativas.concept_extraction import (
            extract_text_concepts,
        )

        result = extract_text_concepts(
            """
            3 CERTIFICADO DE INSTALACION
            ELECTRICA 150,00 450,00
            2 INCREMENTARIA EN UN 20% :
            BASE LVA. 7.552,00 CUOTA VAG
            585,92 TOTAL PREV'G*4 37,92 Euros
            """
        )

        titles = [
            (
                item.get("titulo")
                or ""
            ).upper()
            for item in result
        ]

        amounts = [
            str(
                item.get("importe")
            )
            for item in result
            if (
                item.get("importe")
                is not None
            )
        ]

        self.assertNotIn(
            "7552.00",
            amounts,
        )

        self.assertNotIn(
            "37.92",
            amounts,
        )

        self.assertFalse(
            any(
                "BASE LVA"
                in title
                for title in titles
            )
        )

        self.assertFalse(
            any(
                "TOTAL PREV"
                in title
                for title in titles
            )
        )


    def test_multiline_footer_preserves_previous_real_concept(
        self,
    ):
        from comparativas.concept_extraction import (
            extract_text_concepts,
        )

        result = extract_text_concepts(
            """
            CERTIFICADO DE INSTALACION
            ELECTRICA 3 150,00 450,00
            BASE LVA. 7.552,00 CUOTA VAG
            585,92 TOTAL PREV 37,92 Euros
            """
        )

        amounts = {
            str(
                item.get("importe")
            )
            for item in result
            if (
                item.get("importe")
                is not None
            )
        }

        self.assertIn(
            "450.00",
            amounts,
        )

        self.assertNotIn(
            "7552.00",
            amounts,
        )

        self.assertNotIn(
            "37.92",
            amounts,
        )


    def test_normal_scope_line_after_base_word_is_not_swallowed(
        self,
    ):
        from comparativas.concept_extraction import (
            extract_text_concepts,
        )

        result = extract_text_concepts(
            """
            BASE SOPORTE EQUIPO 2 100,00 200,00
            INSTALACION AUXILIAR 1 50,00 50,00
            """
        )

        amounts = {
            str(
                item.get("importe")
            )
            for item in result
            if (
                item.get("importe")
                is not None
            )
        }

        self.assertIn(
            "200.00",
            amounts,
        )

        self.assertIn(
            "50.00",
            amounts,
        )


    def test_domain_like_ocr_fragment_is_not_supplier(
        self,
    ):
        from comparativas.presupuesto_import import (
            _guess_supplier_name,
        )

        result = _guess_supplier_name(
            """
            CLIENTE
            CLIENTE INDUSTRIAL
            electricidadOmarca94.com
            Avenida Central 20
            """,
            [],
        )

        self.assertEqual(
            result,
            "",
        )
