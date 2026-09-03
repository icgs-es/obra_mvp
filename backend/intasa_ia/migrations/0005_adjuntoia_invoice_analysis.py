from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('intasa_ia', '0004_adjuntoia_extracted_text_adjuntoia_extractor_version_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='adjuntoia',
            name='invoice_analysis',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
