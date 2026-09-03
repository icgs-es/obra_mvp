from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("agenda", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="event",
            name="team",
            field=models.ForeignKey(
                to="usuarios.team",
                null=True,
                blank=True,
                on_delete=models.SET_NULL,
            ),
        ),
    ]
