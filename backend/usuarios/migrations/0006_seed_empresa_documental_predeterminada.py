from django.db import migrations


def seed_document_default_teams(
    apps,
    schema_editor,
):
    User = apps.get_model("auth", "User")
    Team = apps.get_model("usuarios", "Team")
    UserProfile = apps.get_model(
        "usuarios",
        "UserProfile",
    )

    inveradride = (
        Team.objects
        .filter(name__iexact="INVERADRIDE")
        .order_by("id")
        .first()
    )

    for user in User.objects.all().order_by("id"):
        profile, _created = (
            UserProfile.objects.get_or_create(
                user_id=user.pk,
                defaults={
                    "color": "#3498DB",
                },
            )
        )

        if (
            profile
            .empresa_documental_predeterminada_id
        ):
            continue

        team_ids = list(
            Team.objects
            .filter(members__id=user.pk)
            .order_by("id")
            .values_list("id", flat=True)
            .distinct()
        )

        selected_team_id = None

        if (
            inveradride is not None
            and inveradride.pk in team_ids
        ):
            selected_team_id = inveradride.pk

        elif len(team_ids) == 1:
            selected_team_id = team_ids[0]

        if selected_team_id is not None:
            (
                UserProfile.objects
                .filter(pk=profile.pk)
                .update(
                    empresa_documental_predeterminada_id=(
                        selected_team_id
                    )
                )
            )


class Migration(migrations.Migration):

    dependencies = [
        (
            "usuarios",
            "0005_userprofile_empresa_documental_predeterminada",
        ),
    ]

    operations = [
        migrations.RunPython(
            seed_document_default_teams,
            migrations.RunPython.noop,
        ),
    ]
