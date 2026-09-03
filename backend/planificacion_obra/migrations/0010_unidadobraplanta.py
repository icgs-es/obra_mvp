from django.db import migrations, models
import django.db.models.deletion


PREFERRED_ORDER = {
    "PRINCIPAL": 10,
    "INTERIOR": 20,
    "EXTERIOR": 30,
    "SOLARIUM": 40,
    "GARAJE": 50,
    "OBRA": 60,
    "REFORMA": 70,
}


def normalize(value):
    return " ".join(
        str(value or "")
        .strip()
        .upper()
        .split()
    )


def backfill_unidad_plantas(
    apps,
    schema_editor,
):
    TareaObra = apps.get_model(
        "planificacion_obra",
        "TareaObra",
    )

    UnidadObraPlanta = apps.get_model(
        "planificacion_obra",
        "UnidadObraPlanta",
    )

    seen = set()
    rows = []

    source = (
        TareaObra.objects
        .exclude(
            unidad_obra_id=None
        )
        .exclude(
            legacy_planta=""
        )
        .values_list(
            "unidad_obra_id",
            "team_id",
            "legacy_planta",
        )
        .order_by(
            "unidad_obra_id",
            "legacy_planta",
        )
        .iterator(
            chunk_size=2000
        )
    )

    for (
        unidad_id,
        team_id,
        raw_name,
    ) in source:
        name = normalize(
            raw_name
        )

        if not name or name == "-":
            continue

        key = (
            unidad_id,
            name,
        )

        if key in seen:
            continue

        seen.add(key)

        rows.append(
            UnidadObraPlanta(
                unidad_obra_id=unidad_id,
                team_id=team_id,
                nombre=name,
                orden=(
                    PREFERRED_ORDER
                    .get(
                        name,
                        100,
                    )
                ),
                activa=True,
                raw_data={
                    "origen": (
                        "backfill_tarea_obra"
                    ),
                    "legacy_planta": (
                        raw_name
                    ),
                },
            )
        )

    UnidadObraPlanta.objects.bulk_create(
        rows,
        batch_size=1000,
        ignore_conflicts=True,
    )


class Migration(migrations.Migration):

    dependencies = [
        (
            "planificacion_obra",
            "0009_asignacionobra_"
            "cantidad_ejecutada",
        ),
    ]

    operations = [
        migrations.CreateModel(
            name="UnidadObraPlanta",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "nombre",
                    models.CharField(
                        help_text=(
                            "Nombre operativo: "
                            "PRINCIPAL, INTERIOR, "
                            "EXTERIOR, SOLARIUM, "
                            "GARAJE..."
                        ),
                        max_length=80,
                    ),
                ),
                (
                    "orden",
                    models.PositiveIntegerField(
                        default=0,
                    ),
                ),
                (
                    "activa",
                    models.BooleanField(
                        default=True,
                    ),
                ),
                (
                    "raw_data",
                    models.JSONField(
                        blank=True,
                        default=dict,
                    ),
                ),
                (
                    "creado_en",
                    models.DateTimeField(
                        auto_now_add=True,
                    ),
                ),
                (
                    "actualizado_en",
                    models.DateTimeField(
                        auto_now=True,
                    ),
                ),
                (
                    "team",
                    models.ForeignKey(
                        editable=False,
                        on_delete=(
                            django.db.models
                            .deletion.CASCADE
                        ),
                        related_name=(
                            "plantas_unidad_obra"
                        ),
                        to="usuarios.team",
                    ),
                ),
                (
                    "unidad_obra",
                    models.ForeignKey(
                        on_delete=(
                            django.db.models
                            .deletion.CASCADE
                        ),
                        related_name="plantas",
                        to=(
                            "planificacion_obra."
                            "unidadobra"
                        ),
                    ),
                ),
            ],
            options={
                "verbose_name": (
                    "Planta de unidad de obra"
                ),
                "verbose_name_plural": (
                    "Plantas de unidades de obra"
                ),
                "ordering": [
                    (
                        "unidad_obra__obra__"
                        "legacy_cod_obra"
                    ),
                    "unidad_obra__edificio",
                    "unidad_obra__vivienda",
                    "orden",
                    "nombre",
                ],
            },
        ),
        migrations.AddConstraint(
            model_name=(
                "unidadobraplanta"
            ),
            constraint=(
                models.UniqueConstraint(
                    fields=(
                        "unidad_obra",
                        "nombre",
                    ),
                    name=(
                        "uniq_po_unidad_"
                        "planta_nombre"
                    ),
                )
            ),
        ),
        migrations.AddIndex(
            model_name=(
                "unidadobraplanta"
            ),
            index=models.Index(
                fields=[
                    "unidad_obra",
                    "activa",
                    "orden",
                ],
                name=(
                    "po_uop_unit_active_idx"
                ),
            ),
        ),
        migrations.RunPython(
            backfill_unidad_plantas,
            migrations.RunPython.noop,
        ),
    ]
