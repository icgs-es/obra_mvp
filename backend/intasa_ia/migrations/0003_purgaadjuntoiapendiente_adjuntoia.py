import django.db.models.deletion
import intasa_ia.models
import intasa_ia.private_storage
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('intasa_ia', '0002_private_conversations_and_sharing'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='PurgaAdjuntoIAPendiente',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('attachment_id', models.UUIDField(unique=True)),
                ('storage_name', models.CharField(max_length=255)),
                ('error_code', models.CharField(default='storage_delete_failed', max_length=64)),
                ('attempts', models.PositiveIntegerField(default=1)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Purga pendiente de adjunto INTASA IA',
                'verbose_name_plural': 'Purgas pendientes de adjuntos INTASA IA',
            },
        ),
        migrations.CreateModel(
            name='AdjuntoIA',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('file', models.FileField(max_length=255, storage=intasa_ia.private_storage.PrivateIAStorage(), upload_to=intasa_ia.models.adjunto_ia_upload_to)),
                ('original_name', models.CharField(max_length=255)),
                ('safe_display_name', models.CharField(max_length=255)),
                ('declared_mime', models.CharField(max_length=127)),
                ('detected_mime', models.CharField(max_length=127)),
                ('extension', models.CharField(max_length=10)),
                ('size_bytes', models.PositiveBigIntegerField()),
                ('sha256', models.CharField(db_index=True, max_length=64)),
                ('status', models.CharField(choices=[('UPLOADED', 'Subido'), ('READY', 'Disponible'), ('FAILED', 'Fallido'), ('DELETED', 'Eliminado')], db_index=True, default='UPLOADED', max_length=16)),
                ('error_code', models.CharField(blank=True, default='', max_length=64)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('conversation', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='adjuntos', to='intasa_ia.conversacionia')),
                ('message', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='adjuntos', to='intasa_ia.mensajeia')),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='adjuntos_intasa_ia', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ('created_at', 'id'),
                'indexes': [models.Index(fields=['conversation', 'created_at'], name='ia_att_conv_created'), models.Index(fields=['message', 'created_at'], name='ia_att_msg_created')],
            },
        ),
    ]
