import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('intasa_ia', '0003_purgaadjuntoiapendiente_adjuntoia'),
    ]

    operations = [
        migrations.AddField(
            model_name='adjuntoia',
            name='extracted_text',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='adjuntoia',
            name='extractor_version',
            field=models.CharField(blank=True, default='', max_length=32),
        ),
        migrations.AddField(
            model_name='adjuntoia',
            name='ocr_used',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='adjuntoia',
            name='page_count',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='adjuntoia',
            name='processed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='adjuntoia',
            name='processed_source_sha256',
            field=models.CharField(blank=True, default='', max_length=64),
        ),
        migrations.AddField(
            model_name='adjuntoia',
            name='processing_method',
            field=models.CharField(blank=True, default='', max_length=32),
        ),
        migrations.AddField(
            model_name='adjuntoia',
            name='processing_started_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='adjuntoia',
            name='sheet_count',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='adjuntoia',
            name='technical_summary',
            field=models.CharField(blank=True, default='', max_length=500),
        ),
        migrations.AlterField(
            model_name='adjuntoia',
            name='status',
            field=models.CharField(choices=[('UPLOADED', 'Subiendo'), ('PROCESSING', 'Procesando'), ('READY', 'Disponible para analizar'), ('FAILED', 'No se pudo procesar'), ('DELETED', 'Eliminado')], db_index=True, default='UPLOADED', max_length=16),
        ),
        migrations.CreateModel(
            name='ProcesamientoMensajeIA',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('QUEUED', 'En cola'), ('PROCESSING', 'Procesando'), ('GENERATING', 'Generando respuesta'), ('COMPLETED', 'Completado'), ('FAILED', 'Fallido')], db_index=True, default='QUEUED', max_length=16)),
                ('task_key', models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ('generation_key', models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ('error_code', models.CharField(blank=True, default='', max_length=64)),
                ('attempts', models.PositiveSmallIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('assistant_message', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='generated_from_documents', to='intasa_ia.mensajeia')),
                ('message', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='document_processing', to='intasa_ia.mensajeia')),
            ],
            options={
                'verbose_name': 'Procesamiento documental INTASA IA',
                'verbose_name_plural': 'Procesamientos documentales INTASA IA',
            },
        ),
    ]
