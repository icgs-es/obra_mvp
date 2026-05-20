from django.conf import settings
from django.db import models


class ObraPlanificacion(models.Model):
    team = models.ForeignKey("usuarios.Team", on_delete=models.CASCADE, related_name="obras_planificacion")

    legacy_cod_obra = models.IntegerField(db_index=True)
    codigo = models.CharField(max_length=50)
    nombre = models.CharField(max_length=255)

    descripcion = models.TextField(blank=True)
    direccion = models.CharField(max_length=255, blank=True)
    poblacion = models.CharField(max_length=120, blank=True)
    provincia = models.CharField(max_length=120, blank=True)

    aparejador = models.CharField(max_length=160, blank=True)
    jefe_obra = models.CharField(max_length=160, blank=True)

    fecha_inicio = models.DateField(null=True, blank=True)
    fecha_fin = models.DateField(null=True, blank=True)
    importe_obra = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    total_viviendas = models.IntegerField(null=True, blank=True)

    raw_data = models.JSONField(default=dict, blank=True)

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["legacy_cod_obra", "nombre"]
        verbose_name = "Obra"
        verbose_name_plural = "Obras"
        constraints = [
            models.UniqueConstraint(fields=["team", "legacy_cod_obra"], name="uniq_po_obra_legacy_team"),
            models.UniqueConstraint(fields=["team", "codigo"], name="uniq_po_obra_codigo_team"),
        ]

    def __str__(self):
        return f"{self.codigo} · {self.nombre}"


class FaseObra(models.Model):
    team = models.ForeignKey("usuarios.Team", on_delete=models.CASCADE, related_name="fases_obra")
    obra = models.ForeignKey(ObraPlanificacion, on_delete=models.CASCADE, related_name="fases")

    legacy_cod_fase = models.IntegerField(db_index=True)
    nombre = models.CharField(max_length=160)

    cantidad_viviendas = models.IntegerField(null=True, blank=True)
    num_vivienda_inicial = models.IntegerField(null=True, blank=True)
    num_vivienda_final = models.IntegerField(null=True, blank=True)
    vivienda_lateral = models.BooleanField(default=False)
    cantidad_viviendas_laterales = models.IntegerField(null=True, blank=True)
    zona_comun = models.BooleanField(default=False)
    observaciones = models.TextField(blank=True)

    raw_data = models.JSONField(default=dict, blank=True)

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["obra__legacy_cod_obra", "legacy_cod_fase"]
        verbose_name = "Fase / edificio"
        verbose_name_plural = "Fases / edificios"
        constraints = [
            models.UniqueConstraint(fields=["team", "obra", "legacy_cod_fase"], name="uniq_po_fase_legacy_team"),
        ]

    def __str__(self):
        return f"{self.obra} · {self.nombre}"


class UnidadObra(models.Model):
    team = models.ForeignKey("usuarios.Team", on_delete=models.CASCADE, related_name="unidades_obra")
    obra = models.ForeignKey(ObraPlanificacion, on_delete=models.CASCADE, related_name="unidades")
    fase = models.ForeignKey(FaseObra, on_delete=models.SET_NULL, null=True, blank=True, related_name="unidades")

    legacy_cod_obra = models.IntegerField(db_index=True)
    legacy_cod_fase = models.IntegerField(db_index=True)
    legacy_cod_vivienda = models.CharField(max_length=80, db_index=True)

    edificio = models.CharField(max_length=120)
    vivienda = models.CharField(max_length=80)
    nivel = models.CharField(max_length=80, blank=True)
    tipo = models.CharField(max_length=80, blank=True)

    observaciones = models.TextField(blank=True)
    raw_data = models.JSONField(default=dict, blank=True)

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["obra__legacy_cod_obra", "edificio", "vivienda", "nivel"]
        verbose_name = "Unidad de obra"
        verbose_name_plural = "Unidades de obra"
        constraints = [
            models.UniqueConstraint(
                fields=["team", "obra", "legacy_cod_fase", "legacy_cod_vivienda", "nivel"],
                name="uniq_po_unidad_legacy_team",
            )
        ]

    def __str__(self):
        return f"{self.obra} · {self.edificio} · Viv. {self.vivienda} · {self.nivel or '-'}"


class CapituloCatalogo(models.Model):
    team = models.ForeignKey("usuarios.Team", on_delete=models.CASCADE, related_name="capitulos_catalogo_obra")

    codigo = models.CharField(max_length=40)
    nombre = models.CharField(max_length=255)
    orden = models.PositiveIntegerField(default=0)

    raw_data = models.JSONField(default=dict, blank=True)

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["orden", "codigo"]
        verbose_name = "Capítulo catálogo"
        verbose_name_plural = "Capítulos catálogo"
        constraints = [
            models.UniqueConstraint(fields=["team", "codigo"], name="uniq_po_capitulo_catalogo_team"),
        ]

    def __str__(self):
        return f"{self.codigo} · {self.nombre}"


class PartidaCatalogo(models.Model):
    team = models.ForeignKey("usuarios.Team", on_delete=models.CASCADE, related_name="partidas_catalogo_obra")
    capitulo = models.ForeignKey(CapituloCatalogo, on_delete=models.CASCADE, related_name="partidas")

    codigo = models.CharField(max_length=40)
    nombre = models.CharField(max_length=255)
    tipo_partida = models.CharField(max_length=80, blank=True)
    unidad = models.CharField(max_length=40, blank=True)
    dias_material = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)

    raw_data = models.JSONField(default=dict, blank=True)

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["capitulo__codigo", "codigo"]
        verbose_name = "Partida catálogo"
        verbose_name_plural = "Partidas catálogo"
        constraints = [
            models.UniqueConstraint(fields=["team", "capitulo", "codigo"], name="uniq_po_partida_catalogo_team"),
        ]

    def __str__(self):
        return f"{self.capitulo.codigo} · {self.codigo} · {self.nombre}"


class RecursoCatalogo(models.Model):
    team = models.ForeignKey("usuarios.Team", on_delete=models.CASCADE, related_name="recursos_catalogo_obra")

    legacy_id = models.IntegerField(db_index=True)
    nombre = models.CharField(max_length=255)
    tipo = models.CharField(max_length=80, blank=True)
    unidad = models.CharField(max_length=40, blank=True)

    capitulo = models.ForeignKey(CapituloCatalogo, on_delete=models.SET_NULL, null=True, blank=True, related_name="recursos")

    stock = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    ultimo_precio_unidad = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    precio_unidad_uso = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    control_stock = models.BooleanField(default=False)

    observaciones = models.TextField(blank=True)
    raw_data = models.JSONField(default=dict, blank=True)

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["tipo", "nombre"]
        verbose_name = "Recurso catálogo"
        verbose_name_plural = "Recursos catálogo"
        constraints = [
            models.UniqueConstraint(fields=["team", "legacy_id"], name="uniq_po_recurso_catalogo_team"),
        ]

    def __str__(self):
        return f"{self.legacy_id} · {self.nombre}"


class EmpleadoObra(models.Model):
    class Tipo(models.TextChoices):
        ADMINISTRADA = "ADMINISTRADA", "Mano de obra administrada"
        CONTRATADO = "CONTRATADO", "Contratado"

    class Categoria(models.TextChoices):
        PEON = "PEON", "Peón"
        OFICIAL_1 = "OFICIAL_1", "Oficial 1ª"
        OFICIAL_2 = "OFICIAL_2", "Oficial 2ª"
        ENCARGADO = "ENCARGADO", "Encargado"
        JEFE_OBRA = "JEFE_OBRA", "Jefe de obra"
        OTRO = "OTRO", "Otro"

    class Situacion(models.TextChoices):
        ACTIVO = "ACTIVO", "Activo"
        BAJA = "BAJA", "Baja"
        VACACIONES = "VACACIONES", "Vacaciones"

    team = models.ForeignKey("usuarios.Team", on_delete=models.CASCADE, related_name="empleados_obra")
    rrhh_empleado = models.ForeignKey(
        "rrhh.Empleado",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="empleados_obra_legacy",
        help_text="Empleado maestro RRHH asociado a este empleado legacy de obra.",
    )

    legacy_id = models.IntegerField(null=True, blank=True, db_index=True)

    nombre = models.CharField(max_length=160)
    tipo = models.CharField(max_length=20, choices=Tipo.choices, default=Tipo.ADMINISTRADA)
    categoria = models.CharField(max_length=20, choices=Categoria.choices, default=Categoria.OTRO)
    situacion = models.CharField(max_length=20, choices=Situacion.choices, default=Situacion.ACTIVO)

    fecha_alta = models.DateField(null=True, blank=True)
    fecha_baja = models.DateField(null=True, blank=True)
    precio_hora = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)

    empresa_origen = models.CharField(max_length=160, blank=True)
    observaciones = models.CharField(max_length=256, blank=True)

    raw_data = models.JSONField(default=dict, blank=True)

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name = "Empleado de obra"
        verbose_name_plural = "Empleados de obra"
        constraints = [
            models.UniqueConstraint(fields=["team", "legacy_id"], name="uniq_po_empleado_legacy_team"),
        ]

    def __str__(self):
        return self.nombre


class AlmacenObra(models.Model):
    team = models.ForeignKey("usuarios.Team", on_delete=models.CASCADE, related_name="almacenes_obra")
    obra = models.ForeignKey(ObraPlanificacion, on_delete=models.CASCADE, related_name="almacenes")

    legacy_id_almacen = models.CharField(max_length=40, db_index=True)
    nombre = models.CharField(max_length=160)
    ubicacion = models.CharField(max_length=255, blank=True)
    descuenta_stock = models.BooleanField(default=False)

    raw_data = models.JSONField(default=dict, blank=True)

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["obra__legacy_cod_obra", "legacy_id_almacen"]
        verbose_name = "Almacén de obra"
        verbose_name_plural = "Almacenes de obra"
        constraints = [
            models.UniqueConstraint(fields=["team", "obra", "legacy_id_almacen"], name="uniq_po_almacen_legacy_team"),
        ]

    def __str__(self):
        return f"{self.obra} · {self.nombre}"


class TareaObra(models.Model):
    team = models.ForeignKey("usuarios.Team", on_delete=models.CASCADE, related_name="tareas_obra")
    legacy_key = models.CharField(max_length=180, db_index=True)

    obra = models.ForeignKey(ObraPlanificacion, on_delete=models.CASCADE, related_name="tareas")
    unidad_obra = models.ForeignKey(UnidadObra, on_delete=models.SET_NULL, null=True, blank=True, related_name="tareas")
    capitulo = models.ForeignKey(CapituloCatalogo, on_delete=models.SET_NULL, null=True, blank=True, related_name="tareas")
    partida = models.ForeignKey(PartidaCatalogo, on_delete=models.SET_NULL, null=True, blank=True, related_name="tareas")

    legacy_cod_obra = models.IntegerField(db_index=True)
    legacy_cod_fase = models.IntegerField(null=True, blank=True, db_index=True)
    legacy_cod_vivienda = models.CharField(max_length=80, blank=True, db_index=True)
    legacy_planta = models.CharField(max_length=80, blank=True)
    legacy_capitulo = models.CharField(max_length=40, blank=True, db_index=True)
    legacy_partida = models.CharField(max_length=40, blank=True, db_index=True)
    legacy_orden = models.IntegerField(null=True, blank=True)

    programacion = models.CharField(max_length=80, blank=True)
    porcentaje_completado = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)

    inicio_tarea = models.DateField(null=True, blank=True)
    fin_tarea = models.DateField(null=True, blank=True)
    dias = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    horas = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    inicio_real = models.DateField(null=True, blank=True)
    fin_real = models.DateField(null=True, blank=True)
    dias_reales = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    horas_reales = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    inicio_estimado = models.DateField(null=True, blank=True)
    fin_estimado = models.DateField(null=True, blank=True)
    dias_estimados = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    horas_estimadas = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    personas_a_utilizar = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    personas_utilizadas = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)

    importe_tarea = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    importe_tarea_real = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    importe_tarea_estimado = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    tipo_partida = models.CharField(max_length=80, blank=True)
    unidad = models.CharField(max_length=40, blank=True)
    cantidad = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    precio_unidad = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    con_incidencias = models.BooleanField(default=False)
    observaciones = models.TextField(blank=True)
    raw_data = models.JSONField(default=dict, blank=True)

    sincronizado_en = models.DateTimeField(auto_now=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["inicio_tarea", "legacy_cod_obra", "legacy_cod_fase", "legacy_cod_vivienda", "legacy_orden"]
        verbose_name = "Tarea de obra"
        verbose_name_plural = "Tareas de obra"
        constraints = [
            models.UniqueConstraint(fields=["team", "legacy_key"], name="uniq_po_tarea_legacy_team"),
        ]

    def __str__(self):
        return f"{self.obra} · {self.legacy_capitulo} · {self.legacy_partida} · {self.legacy_cod_vivienda}"




class TareaRecursoPrevisto(models.Model):
    team = models.ForeignKey(
        "usuarios.Team",
        on_delete=models.CASCADE,
        related_name="tarea_recursos_previstos",
    )

    # No existe ID propio en tblTareasRecursosInicial.
    # Usamos la fila Excel como identificador legacy estable de importación.
    legacy_row_number = models.IntegerField(db_index=True)

    tarea_obra = models.ForeignKey(
        "TareaObra",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recursos_previstos",
    )
    unidad_obra = models.ForeignKey(
        "UnidadObra",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recursos_previstos",
    )
    partida = models.ForeignKey(
        "PartidaCatalogo",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recursos_previstos",
    )
    recurso = models.ForeignKey(
        "RecursoCatalogo",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="previstos_en_tareas",
    )

    legacy_cod_obra = models.IntegerField(null=True, blank=True, db_index=True)
    legacy_cod_fase = models.IntegerField(null=True, blank=True, db_index=True)
    legacy_cod_vivienda = models.CharField(max_length=80, blank=True, db_index=True)
    legacy_planta = models.CharField(max_length=80, blank=True)
    legacy_cod_partida = models.CharField(max_length=40, blank=True, db_index=True)
    legacy_id_recurso = models.IntegerField(null=True, blank=True, db_index=True)
    legacy_id_recurso_old = models.IntegerField(null=True, blank=True)

    # Orden propio del recurso previsto dentro de la planificación.
    # No debe usarse para localizar TareaObra.
    legacy_orden_recurso = models.IntegerField(null=True, blank=True, db_index=True)

    unidad = models.CharField(max_length=40, blank=True)
    precio_unidad = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    cantidad = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    costo_recurso = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)

    control_suministros = models.BooleanField(default=False)
    avisar = models.IntegerField(null=True, blank=True)

    fecha_estimada_entrega = models.DateField(null=True, blank=True)

    raw_data = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Recurso previsto de tarea"
        verbose_name_plural = "Recursos previstos de tareas"
        ordering = ["legacy_cod_obra", "legacy_cod_fase", "legacy_cod_vivienda", "legacy_planta", "legacy_cod_partida", "legacy_orden_recurso", "legacy_row_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["team", "legacy_row_number"],
                name="uniq_po_recurso_previsto_row_team",
            )
        ]
        indexes = [
            models.Index(fields=["team", "legacy_cod_obra"], name="idx_po_recprev_obra"),
            models.Index(fields=["team", "legacy_id_recurso"], name="idx_po_recprev_recurso"),
            models.Index(fields=["team", "legacy_cod_partida"], name="idx_po_recprev_partida"),
        ]

    def __str__(self):
        return f"{self.legacy_row_number} · {self.legacy_cod_partida} · {self.legacy_id_recurso}"


class TareaRecursoReal(models.Model):
    team = models.ForeignKey(
        "usuarios.Team",
        on_delete=models.CASCADE,
        related_name="tarea_recursos_reales",
    )

    legacy_id_recurso_tarea = models.IntegerField(db_index=True)

    tarea_obra = models.ForeignKey(
        "TareaObra",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recursos_reales",
    )
    unidad_obra = models.ForeignKey(
        "UnidadObra",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recursos_reales",
    )
    partida = models.ForeignKey(
        "PartidaCatalogo",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recursos_reales",
    )

    recurso = models.ForeignKey(
        "RecursoCatalogo",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reales_en_tareas",
    )
    empleado = models.ForeignKey(
        "EmpleadoObra",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recursos_reales",
    )

    movimiento_almacen = models.ForeignKey(
        "RecursoAlmacenMovimiento",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recursos_reales_tarea",
    )

    legacy_cod_obra = models.IntegerField(null=True, blank=True, db_index=True)
    legacy_cod_fase = models.IntegerField(null=True, blank=True, db_index=True)
    legacy_cod_vivienda = models.CharField(max_length=80, blank=True, db_index=True)
    legacy_planta = models.CharField(max_length=80, blank=True)

    legacy_capitulo = models.CharField(max_length=40, blank=True, db_index=True)
    legacy_partida = models.CharField(max_length=40, blank=True, db_index=True)

    legacy_id_recurso = models.IntegerField(null=True, blank=True, db_index=True)
    legacy_tipo_recurso = models.CharField(max_length=80, blank=True, db_index=True)
    legacy_personal = models.IntegerField(null=True, blank=True)
    legacy_id_movimiento_almacen = models.IntegerField(null=True, blank=True, db_index=True)

    # Orden propio de la línea real. No se usa para localizar TareaObra.
    legacy_orden_recurso = models.IntegerField(null=True, blank=True, db_index=True)

    unidad = models.CharField(max_length=40, blank=True)
    cantidad = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    precio_unidad = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)

    dias = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    dias_reales = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    horas = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    horas_reales = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)

    inicio_recurso_real = models.DateField(null=True, blank=True)
    fin_recurso_real = models.DateField(null=True, blank=True)

    costo_recurso = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    costo_recurso_real = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)

    control_suministros = models.BooleanField(default=False)
    avisar = models.IntegerField(null=True, blank=True)

    id_proveedor = models.CharField(max_length=80, blank=True)
    cod_albaran = models.CharField(max_length=80, blank=True)
    num_linea_albaran = models.IntegerField(null=True, blank=True)
    cod_factura = models.CharField(max_length=80, blank=True)
    num_linea_factura = models.IntegerField(null=True, blank=True)

    observaciones = models.TextField(blank=True)

    raw_data = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Recurso real de tarea"
        verbose_name_plural = "Recursos reales de tareas"
        ordering = [
            "legacy_cod_obra",
            "legacy_cod_fase",
            "legacy_cod_vivienda",
            "legacy_planta",
            "legacy_partida",
            "legacy_orden_recurso",
            "legacy_id_recurso_tarea",
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["team", "legacy_id_recurso_tarea"],
                name="uniq_po_recurso_real_legacy_team",
            )
        ]
        indexes = [
            models.Index(fields=["team", "legacy_cod_obra"], name="idx_po_recreal_obra"),
            models.Index(fields=["team", "legacy_id_recurso"], name="idx_po_recreal_idrec"),
            models.Index(fields=["team", "legacy_tipo_recurso"], name="idx_po_recreal_tipo"),
            models.Index(fields=["team", "legacy_partida"], name="idx_po_recreal_partida"),
        ]

    def __str__(self):
        return f"{self.legacy_id_recurso_tarea} · {self.legacy_tipo_recurso} · {self.legacy_id_recurso}"

class RecursoAlmacenMovimiento(models.Model):
    class TipoMovimiento(models.TextChoices):
        ENTRADA = "ENTRADA", "Entrada"
        SALIDA = "SALIDA", "Salida"
        CONTROL_STOCK = "CONTROL_STOCK", "Control stock"
        ROTURA = "ROTURA", "Rotura"
        OTRO = "OTRO", "Otro"

    team = models.ForeignKey(
        "usuarios.Team",
        on_delete=models.CASCADE,
        related_name="recurso_almacen_movimientos",
    )

    legacy_id_movimiento = models.IntegerField(db_index=True)

    almacen = models.ForeignKey(
        "AlmacenObra",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movimientos",
    )
    recurso = models.ForeignKey(
        "RecursoCatalogo",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movimientos_almacen",
    )
    obra = models.ForeignKey(
        "ObraPlanificacion",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movimientos_almacen",
    )
    unidad_obra = models.ForeignKey(
        "UnidadObra",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movimientos_almacen",
    )
    empleado = models.ForeignKey(
        "EmpleadoObra",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movimientos_almacen",
    )
    partida = models.ForeignKey(
        "PartidaCatalogo",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movimientos_almacen",
    )

    legacy_id_almacen = models.CharField(max_length=40, blank=True, db_index=True)
    legacy_cod_recurso = models.IntegerField(null=True, blank=True, db_index=True)
    legacy_cod_obra = models.IntegerField(null=True, blank=True, db_index=True)
    legacy_cod_fase = models.IntegerField(null=True, blank=True, db_index=True)
    legacy_cod_vivienda = models.CharField(max_length=80, blank=True, db_index=True)
    legacy_planta = models.CharField(max_length=80, blank=True)
    legacy_capitulo = models.CharField(max_length=40, blank=True, db_index=True)
    legacy_partida = models.CharField(max_length=40, blank=True, db_index=True)
    legacy_cod_personal = models.IntegerField(null=True, blank=True, db_index=True)

    unidad = models.CharField(max_length=40, blank=True)
    cantidad = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    quedan = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)

    fecha_movimiento = models.DateField(null=True, blank=True, db_index=True)
    hora_movimiento = models.TimeField(null=True, blank=True)

    tipo_movimiento = models.CharField(
        max_length=30,
        choices=TipoMovimiento.choices,
        default=TipoMovimiento.OTRO,
        db_index=True,
    )
    tipo_movimiento_raw = models.CharField(max_length=80, blank=True)

    cod_proveedor = models.CharField(max_length=80, blank=True)
    cod_albaran = models.CharField(max_length=80, blank=True, db_index=True)
    linea = models.IntegerField(null=True, blank=True)
    cod_factura = models.CharField(max_length=80, blank=True, db_index=True)

    en_partida = models.BooleanField(default=False)
    vehiculo = models.CharField(max_length=120, blank=True)
    kilometraje = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)

    observaciones = models.TextField(blank=True)
    raw_data = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Movimiento de almacén"
        verbose_name_plural = "Movimientos de almacén"
        ordering = ["-fecha_movimiento", "-legacy_id_movimiento"]
        constraints = [
            models.UniqueConstraint(
                fields=["team", "legacy_id_movimiento"],
                name="uniq_po_movalm_legacy_team",
            )
        ]
        indexes = [
            models.Index(fields=["team", "fecha_movimiento"], name="idx_po_movalm_fecha"),
            models.Index(fields=["team", "tipo_movimiento"], name="idx_po_movalm_tipo"),
            models.Index(fields=["team", "legacy_id_almacen"], name="idx_po_movalm_alm"),
            models.Index(fields=["team", "legacy_cod_recurso"], name="idx_po_movalm_rec"),
        ]

    def __str__(self):
        return f"{self.legacy_id_movimiento} · {self.tipo_movimiento} · {self.legacy_id_almacen}"

class AsignacionObra(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente"
        REALIZADO = "REALIZADO", "Realizado"

    team = models.ForeignKey("usuarios.Team", on_delete=models.CASCADE, related_name="asignaciones_obra")
    empleado = models.ForeignKey(
        "rrhh.Empleado",
        on_delete=models.CASCADE,
        related_name="asignaciones_obra",
    )

    tarea_obra = models.ForeignKey(TareaObra, on_delete=models.SET_NULL, null=True, blank=True, related_name="asignaciones_previstas")
    unidad_obra = models.ForeignKey(UnidadObra, on_delete=models.SET_NULL, null=True, blank=True, related_name="asignaciones")
    capitulo = models.ForeignKey(CapituloCatalogo, on_delete=models.PROTECT, related_name="asignaciones")
    partida = models.ForeignKey(PartidaCatalogo, on_delete=models.PROTECT, null=True, blank=True, related_name="asignaciones")

    fecha_inicio = models.DateField()
    hora_inicio = models.TimeField()
    fecha_fin = models.DateField()
    hora_fin = models.TimeField()

    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.PENDIENTE)
    observaciones = models.TextField(blank=True)

    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="asignaciones_obra_creadas",
    )

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["fecha_inicio", "hora_inicio", "empleado__nombre_completo"]
        verbose_name = "Asignación de obra"
        verbose_name_plural = "Asignaciones de obra"

    def __str__(self):
        return f"{self.empleado} · {self.fecha_inicio} · {self.capitulo}"


# ---------------------------------------------------------------------
# Display helpers Planificacion Obra
# No cambian BD. Solo ayudan al listado.
# ---------------------------------------------------------------------
def _pi_get_tarea_from_asignacion(obj):
    tarea = getattr(obj, "tarea_obra", None)
    if tarea:
        return tarea

    for f in obj._meta.fields:
        if getattr(f, "remote_field", None) and f.remote_field and f.remote_field.model.__name__ == "TareaObra":
            return getattr(obj, f.name, None)

    return None


def _pi_find_display(obj, include_words, exclude_words=None):
    if not obj:
        return ""

    exclude_words = exclude_words or []

    # Primero FK
    for f in obj._meta.fields:
        name = f.name.lower()
        remote = ""
        if getattr(f, "remote_field", None) and f.remote_field:
            remote = f.remote_field.model._meta.model_name.lower()

        full = f"{name} {remote}"

        if any(w in full for w in include_words) and not any(w in full for w in exclude_words):
            val = getattr(obj, f.name, None)
            if val:
                return str(val)

    # Después campos legacy/texto
    for f in obj._meta.fields:
        name = f.name.lower()
        if any(w in name for w in include_words) and not any(w in name for w in exclude_words):
            val = getattr(obj, f.name, None)
            if val:
                return str(val)

    return ""


def _pi_asig_display_obra(self):
    tarea = _pi_get_tarea_from_asignacion(self)
    return (
        _pi_find_display(self, ["obra"], ["unidad", "tarea", "partida", "capitulo"])
        or _pi_find_display(tarea, ["obra"], ["unidad", "tarea", "partida", "capitulo"])
        or "-"
    )


def _pi_asig_display_unidad(self):
    tarea = _pi_get_tarea_from_asignacion(self)
    return (
        _pi_find_display(self, ["unidad", "vivienda"], [])
        or _pi_find_display(tarea, ["unidad", "vivienda"], [])
        or "-"
    )


def _pi_asig_display_planta(self):
    tarea = _pi_get_tarea_from_asignacion(self)
    return (
        getattr(self, "planta_trabajo", None)
        or getattr(tarea, "legacy_planta", None)
        or "-"
    )


def _pi_asig_display_capitulo(self):
    tarea = _pi_get_tarea_from_asignacion(self)
    return (
        _pi_find_display(self, ["capitulo"], [])
        or _pi_find_display(tarea, ["capitulo"], [])
        or "-"
    )


def _pi_asig_display_partida(self):
    tarea = _pi_get_tarea_from_asignacion(self)
    return (
        _pi_find_display(self, ["partida"], [])
        or _pi_find_display(tarea, ["partida"], [])
        or "-"
    )


try:
    AsignacionObra.pi_display_obra = property(_pi_asig_display_obra)
    AsignacionObra.pi_display_unidad = property(_pi_asig_display_unidad)
    AsignacionObra.pi_display_planta = property(_pi_asig_display_planta)
    AsignacionObra.pi_display_capitulo = property(_pi_asig_display_capitulo)
    AsignacionObra.pi_display_partida = property(_pi_asig_display_partida)
except NameError:
    pass



# ---------------------------------------------------------------------
# Helpers visuales para planificación de personal.
# No modifican BD.
# ---------------------------------------------------------------------
def _pi_asignacion_get_unidad(obj):
    unidad = getattr(obj, "unidad_obra", None)
    if unidad:
        return unidad

    tarea = getattr(obj, "tarea_obra", None)
    if tarea:
        return getattr(tarea, "unidad_obra", None)

    return None


def _pi_asignacion_vivienda_corta(self):
    unidad = _pi_asignacion_get_unidad(self)

    if not unidad:
        return "-"

    for name in ("vivienda", "legacy_cod_vivienda", "cod_vivienda", "codigo_vivienda", "numero_vivienda"):
        if hasattr(unidad, name):
            value = getattr(unidad, name)
            if value not in ("", None):
                value = str(value).strip()
                if value.lower().startswith("viv"):
                    return value
                return f"Viv. {value}"

    return f"Viv. {unidad.pk}"


try:
    AsignacionObra.pi_display_vivienda_corta = property(_pi_asignacion_vivienda_corta)
except NameError:
    pass

