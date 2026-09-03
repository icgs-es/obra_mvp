# Generated for PORTAL INTASA · RRHH_SELECCION_PERSONAL_V1

import django.core.validators
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models

import rrhh.models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("archivos", "0001_initial"),
        ("rrhh", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Candidato",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nombre_completo", models.CharField(max_length=220)),
                ("telefono", models.CharField(blank=True, max_length=60)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("ciudad", models.CharField(blank=True, max_length=120)),
                ("perfil_profesional", models.CharField(blank=True, max_length=220)),
                ("linkedin_url", models.URLField(blank=True, max_length=500)),
                ("observaciones", models.TextField(blank=True)),
                ("activo", models.BooleanField(default=True)),
                ("creado_en", models.DateTimeField(auto_now_add=True)),
                ("actualizado_en", models.DateTimeField(auto_now=True)),
                ("creado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="candidatos_creados", to=settings.AUTH_USER_MODEL)),
                ("team", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="rrhh_candidatos", to="usuarios.team")),
            ],
            options={"ordering": ["nombre_completo", "id"]},
        ),
        migrations.CreateModel(
            name="ProcesoSeleccion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("titulo", models.CharField(max_length=180)),
                ("area", models.CharField(choices=[("OBRA", "Obra"), ("ADMINISTRACION", "Administración"), ("COMERCIAL", "Comercial"), ("GERENCIA", "Gerencia"), ("ARQUITECTURA", "Arquitectura"), ("SERVICIOS", "Servicios"), ("OTRO", "Otro")], default="OTRO", max_length=30)),
                ("descripcion", models.TextField(blank=True)),
                ("requisitos", models.TextField(blank=True)),
                ("estado", models.CharField(choices=[("ABIERTO", "Abierto"), ("PAUSADO", "Pausado"), ("CERRADO", "Cerrado")], default="ABIERTO", max_length=20)),
                ("fecha_apertura", models.DateField(default=django.utils.timezone.localdate)),
                ("fecha_cierre", models.DateField(blank=True, null=True)),
                ("creado_en", models.DateTimeField(auto_now_add=True)),
                ("actualizado_en", models.DateTimeField(auto_now=True)),
                ("creado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="procesos_seleccion_creados", to=settings.AUTH_USER_MODEL)),
                ("modificado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="procesos_seleccion_modificados", to=settings.AUTH_USER_MODEL)),
                ("responsable", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="procesos_seleccion_responsable", to=settings.AUTH_USER_MODEL)),
                ("team", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="rrhh_procesos_seleccion", to="usuarios.team")),
            ],
            options={
                "ordering": ["-fecha_apertura", "-id"],
                "permissions": [("access_recruitment", "Puede acceder a selección de personal")],
            },
        ),
        migrations.CreateModel(
            name="Candidatura",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("cv_fichero", models.FileField(blank=True, upload_to=rrhh.models.candidatura_cv_upload_to)),
                ("cv_nombre_original", models.CharField(blank=True, max_length=255)),
                ("origen", models.CharField(choices=[("LINKEDIN", "LinkedIn"), ("INDEED", "Indeed"), ("CORREO", "Correo"), ("RECOMENDACION", "Recomendación"), ("WEB", "Web"), ("OTRO", "Otro")], default="OTRO", max_length=30)),
                ("fecha_solicitud", models.DateField(default=django.utils.timezone.localdate)),
                ("puntuacion", models.PositiveSmallIntegerField(blank=True, null=True, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(5)])),
                ("estado", models.CharField(choices=[("RECIBIDO", "Recibido"), ("REVISADO", "Revisado"), ("PRESELECCIONADO", "Preseleccionado"), ("PENDIENTE_LLAMADA", "Pendiente de llamada"), ("ENTREVISTA_PROGRAMADA", "Entrevista programada"), ("ENTREVISTADO", "Entrevistado"), ("DESCARTADO", "Descartado"), ("SELECCIONADO", "Seleccionado"), ("CONTRATADO", "Contratado")], default="RECIBIDO", max_length=30)),
                ("fecha_proximo_contacto", models.DateTimeField(blank=True, null=True)),
                ("fecha_entrevista", models.DateTimeField(blank=True, null=True)),
                ("observaciones_revision", models.TextField(blank=True)),
                ("observaciones_entrevista", models.TextField(blank=True)),
                ("creado_en", models.DateTimeField(auto_now_add=True)),
                ("actualizado_en", models.DateTimeField(auto_now=True)),
                ("candidato", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="candidaturas", to="rrhh.candidato")),
                ("creado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="candidaturas_creadas", to=settings.AUTH_USER_MODEL)),
                ("cv_archivo", models.ForeignKey(blank=True, help_text="Currículo ya existente en el módulo Archivos.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="rrhh_candidaturas", to="archivos.archivo")),
                ("modificado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="candidaturas_modificadas", to=settings.AUTH_USER_MODEL)),
                ("proceso", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="candidaturas", to="rrhh.procesoseleccion")),
                ("responsable", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="candidaturas_responsable", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-fecha_solicitud", "-id"]},
        ),
        migrations.CreateModel(
            name="CandidaturaSeguimiento",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tipo", models.CharField(choices=[("ALTA", "Alta"), ("NOTA", "Nota"), ("LLAMADA", "Llamada"), ("ENTREVISTA", "Entrevista"), ("CAMBIO_ESTADO", "Cambio de estado")], default="NOTA", max_length=30)),
                ("fecha", models.DateTimeField(default=django.utils.timezone.now)),
                ("completado", models.BooleanField(default=False)),
                ("notas", models.TextField(blank=True)),
                ("resultado", models.TextField(blank=True)),
                ("estado_anterior", models.CharField(blank=True, max_length=30)),
                ("estado_nuevo", models.CharField(blank=True, max_length=30)),
                ("creado_en", models.DateTimeField(auto_now_add=True)),
                ("candidatura", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="seguimientos", to="rrhh.candidatura")),
                ("usuario", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="seguimientos_candidatura", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-fecha", "-id"]},
        ),
        migrations.AddConstraint(
            model_name="procesoseleccion",
            constraint=models.UniqueConstraint(fields=("team", "titulo", "fecha_apertura"), name="uniq_rrhh_proceso_team_titulo_fecha"),
        ),
        migrations.AddConstraint(
            model_name="candidatura",
            constraint=models.UniqueConstraint(fields=("proceso", "candidato"), name="uniq_rrhh_candidatura_proceso_candidato"),
        ),
        migrations.AddIndex(model_name="candidato", index=models.Index(fields=["team", "nombre_completo"], name="idx_rrhh_cand_team_nombre")),
        migrations.AddIndex(model_name="candidato", index=models.Index(fields=["team", "email"], name="idx_rrhh_cand_team_email")),
        migrations.AddIndex(model_name="procesoseleccion", index=models.Index(fields=["team", "estado"], name="idx_rrhh_proc_team_estado")),
        migrations.AddIndex(model_name="procesoseleccion", index=models.Index(fields=["responsable", "estado"], name="idx_rrhh_proc_resp_estado")),
        migrations.AddIndex(model_name="candidatura", index=models.Index(fields=["proceso", "estado"], name="idx_rrhh_appl_proc_estado")),
        migrations.AddIndex(model_name="candidatura", index=models.Index(fields=["responsable", "estado"], name="idx_rrhh_appl_resp_estado")),
        migrations.AddIndex(model_name="candidatura", index=models.Index(fields=["fecha_proximo_contacto"], name="idx_rrhh_appl_contacto")),
        migrations.AddIndex(model_name="candidatura", index=models.Index(fields=["fecha_entrevista"], name="idx_rrhh_appl_entrevista")),
        migrations.AddIndex(model_name="candidaturaseguimiento", index=models.Index(fields=["candidatura", "-fecha"], name="idx_rrhh_seg_cand_fecha")),
        migrations.AddIndex(model_name="candidaturaseguimiento", index=models.Index(fields=["tipo", "completado"], name="idx_rrhh_seg_tipo_comp")),
    ]
