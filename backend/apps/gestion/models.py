from django.conf import settings
from django.db import models

# CENTRO_COSTE_GESTION_V1
# GESTION_AMBITO_OBRA_DEFAULT_V1
GESTION_AMBITO_CHOICES = [
    ("SIN_CLASIFICAR", "Sin clasificar"),
    ("OBRA", "Obra"),
    ("ADMINISTRACION", "Administración"),
    ("COMERCIAL", "Comercial"),
    ("GERENCIA", "Gerencia"),
    ("INFORMATICA", "Informática"),
    ("VEHICULOS", "Vehículos"),
    ("ALQUILERES", "Alquileres"),
    ("SERVICIOS_GENERALES", "Servicios generales"),
    ("OTROS", "Otros"),
]




class Proveedor(models.Model):
    team = models.ForeignKey(
        "usuarios.Team",
        on_delete=models.PROTECT,
        related_name="gestion_proveedores",
    )

    legacy_id_proveedor = models.IntegerField()

    nombre_comercial = models.CharField(max_length=255)
    nombre_fiscal = models.CharField(max_length=255, blank=True)

    direccion = models.CharField(max_length=255, blank=True)
    cod_postal = models.CharField(max_length=20, blank=True)
    poblacion = models.CharField(max_length=120, blank=True)
    provincia = models.CharField(max_length=120, blank=True)
    pais = models.CharField(max_length=80, blank=True)

    cif = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    telefono = models.CharField(max_length=80, blank=True)

    contacto_comercial = models.CharField(max_length=160, blank=True)
    tel_contacto_comercial = models.CharField(max_length=80, blank=True)

    contacto_admin = models.CharField(max_length=160, blank=True)
    tel_contacto_admin = models.CharField(max_length=80, blank=True)

    sp_iva = models.BooleanField(default=False)
    aplica_retencion_habitual = models.BooleanField(
        default=False,
        help_text="Propone la retención al crear facturas de este proveedor en este equipo.",
    )
    retencion_habitual_porcentaje = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=0,
        help_text="Porcentaje propuesto; la factura y el PDF pueden establecer otro.",
    )
    observaciones = models.TextField(blank=True)

    es_subcontrata = models.BooleanField(default=False)
    cod_obra_legacy = models.CharField(max_length=50, blank=True)
    fuera_listado = models.BooleanField(default=False)

    activo = models.BooleanField(default=True)

    raw_data = models.JSONField(default=dict, blank=True)

    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gestion_proveedores_creados",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # PROVEEDOR_AMBITO_GESTION_V1
    ambito_gestion = models.CharField(
        max_length=40,
        default="OBRA",
        blank=True,
        db_index=True,
        help_text="Ámbito operativo principal del proveedor para filtrar altas y OCR.",
    )


    class Meta:
        verbose_name = "Proveedor"
        verbose_name_plural = "Proveedores"
        ordering = ["nombre_comercial"]
        constraints = [
            models.UniqueConstraint(
                fields=["team", "legacy_id_proveedor"],
                name="uniq_gestion_proveedor_team_legacy",
            )
        ]
        indexes = [
            models.Index(fields=["team", "nombre_comercial"]),
            models.Index(fields=["team", "cif"]),
            models.Index(fields=["team", "legacy_id_proveedor"]),
        ]
        permissions = [
            (
                "manage_supplier_retention_settings",
                "Puede configurar la retención habitual de proveedores",
            ),
        ]

    def __str__(self):
        return self.nombre_comercial or self.nombre_fiscal or f"Proveedor {self.legacy_id_proveedor}"


class ArticuloCompra(models.Model):
    team = models.ForeignKey(
        "usuarios.Team",
        on_delete=models.PROTECT,
        related_name="gestion_articulos_compra",
    )

    nombre = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True)
    unidad = models.CharField(max_length=40, blank=True)
    tipo = models.CharField(max_length=80, blank=True, default="MATERIAL")

    activo = models.BooleanField(default=True)

    # Puente futuro con planificación, sin FK para no acoplar módulos todavía.
    recurso_catalogo_id = models.IntegerField(null=True, blank=True)

    raw_data = models.JSONField(default=dict, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Artículo de compra"
        verbose_name_plural = "Artículos de compra"
        ordering = ["nombre"]
        indexes = [
            models.Index(fields=["team", "nombre"]),
            models.Index(fields=["team", "activo"]),
            models.Index(fields=["recurso_catalogo_id"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["team", "nombre"],
                name="uniq_gestion_articulo_compra_team_nombre",
            )
        ]

    def __str__(self):
        return self.nombre


class ArticuloProveedorAlias(models.Model):
    ESTADO_PENDIENTE = "PENDIENTE"
    ESTADO_VINCULADO = "VINCULADO"
    ESTADO_IGNORADO = "IGNORADO"

    ESTADO_CHOICES = [
        (ESTADO_PENDIENTE, "Pendiente"),
        (ESTADO_VINCULADO, "Vinculado"),
        (ESTADO_IGNORADO, "Ignorado"),
    ]

    team = models.ForeignKey(
        "usuarios.Team",
        on_delete=models.PROTECT,
        related_name="gestion_articulos_alias",
    )
    proveedor = models.ForeignKey(
        "gestion.Proveedor",
        on_delete=models.PROTECT,
        related_name="articulos_alias",
    )
    articulo = models.ForeignKey(
        "gestion.ArticuloCompra",
        on_delete=models.PROTECT,
        related_name="alias_proveedor",
    )

    codigo_proveedor = models.CharField(max_length=120)
    descripcion_proveedor = models.CharField(max_length=500, blank=True)
    unidad_proveedor = models.CharField(max_length=40, blank=True)

    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default=ESTADO_VINCULADO)

    ultimo_precio = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    ultima_fecha = models.DateField(null=True, blank=True)

    raw_data = models.JSONField(default=dict, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Alias de artículo por proveedor"
        verbose_name_plural = "Alias de artículos por proveedor"
        ordering = ["proveedor", "codigo_proveedor"]
        indexes = [
            models.Index(fields=["team", "proveedor"]),
            models.Index(fields=["team", "codigo_proveedor"]),
            models.Index(fields=["articulo"]),
            models.Index(fields=["estado"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["team", "proveedor", "codigo_proveedor"],
                name="uniq_gestion_alias_team_proveedor_codigo",
            )
        ]

    def __str__(self):
        return f"{self.proveedor} · {self.codigo_proveedor} → {self.articulo}"


class EmpresaGestionLegacy(models.Model):
    team = models.OneToOneField(
        "usuarios.Team",
        on_delete=models.PROTECT,
        related_name="empresa_gestion_legacy",
    )

    legacy_id_empresa = models.IntegerField(unique=True)

    nombre_empresa = models.CharField(max_length=255)
    cif_empresa = models.CharField(max_length=50, blank=True)

    direccion_empresa = models.CharField(max_length=255, blank=True)
    poblacion_empresa = models.CharField(max_length=120, blank=True)
    provincia_empresa = models.CharField(max_length=120, blank=True)
    cod_postal_empresa = models.CharField(max_length=20, blank=True)

    periodo_gestion = models.CharField(max_length=20, blank=True)

    ult_codigo_factura = models.IntegerField(default=0)
    prefijo_factura = models.CharField(max_length=20, blank=True)

    ult_codigo_albaran = models.IntegerField(default=0)
    prefijo_albaran = models.CharField(max_length=20, blank=True)

    obra_defecto_legacy = models.IntegerField(default=0)

    prefijo_pedido = models.CharField(max_length=20, blank=True)
    ult_codigo_pedido = models.IntegerField(default=0)

    raw_data = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Empresa legacy de gestión"
        verbose_name_plural = "Empresas legacy de gestión"
        ordering = ["legacy_id_empresa"]
        indexes = [
            models.Index(fields=["legacy_id_empresa"]),
            models.Index(fields=["team"]),
            models.Index(fields=["cif_empresa"]),
        ]

    def __str__(self):
        return f"{self.legacy_id_empresa} - {self.nombre_empresa}"


class FacturaProveedorGestion(models.Model):
    team = models.ForeignKey(
        "usuarios.Team",
        on_delete=models.PROTECT,
        related_name="gestion_facturas_proveedor",
    )

    empresa_legacy = models.ForeignKey(
        "gestion.EmpresaGestionLegacy",
        on_delete=models.PROTECT,
        related_name="facturas_proveedor",
        null=True,
        blank=True,
    )

    proveedor = models.ForeignKey(
        "gestion.Proveedor",
        on_delete=models.SET_NULL,
        related_name="facturas_gestion",
        null=True,
        blank=True,
    )

    cod_factura = models.CharField(max_length=50)
    cod_obra_legacy = models.CharField(max_length=50, blank=True)
    cod_proveedor_legacy = models.IntegerField(null=True, blank=True)
    empresa_legacy_raw = models.IntegerField(null=True, blank=True)

    num_factura_proveedor = models.CharField(max_length=120, blank=True)

    fecha_emision = models.DateField(null=True, blank=True)
    fecha_autorizacion_gerencia = models.DateField(null=True, blank=True)
    fecha_pago_segun_contrato = models.DateField(null=True, blank=True)
    fecha_real_pago = models.DateField(null=True, blank=True)

    importe_base_imponible = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    importe_iva = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    importe_factura = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    retencion_porcentaje = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    retencion = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    importe_pagado = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    forma_pago = models.CharField(max_length=160, blank=True)
    estado = models.CharField(max_length=80, blank=True)
    observaciones = models.TextField(blank=True)

    asignada = models.BooleanField(default=False)
    tiene_retencion = models.BooleanField(default=False)
    generado_albaran = models.BooleanField(default=False)
    certificada = models.BooleanField(default=False)

    archivo = models.CharField(max_length=255, blank=True)
    archivo1 = models.CharField(max_length=255, blank=True)


    # GESTION_TRAZABILIDAD_V1
    ORIGEN_ALTA_CHOICES = [
        ("LEGACY", "Legacy / importación histórica"),
        ("MANUAL", "Manual"),
        ("PDF_OCR", "PDF / OCR"),
        ("SYNC_ACCESS", "Sincronización MS Access"),
        ("SISTEMA", "Sistema"),
    ]
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="gestion_facturas_creadas",
    )
    modificado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="gestion_facturas_modificadas",
    )
    origen_alta = models.CharField(
        max_length=30,
        choices=ORIGEN_ALTA_CHOICES,
        default="LEGACY",
        blank=True,
    )


    # CENTRO_COSTE_GESTION_V1
    ambito_gestion = models.CharField(
        max_length=40,
        choices=GESTION_AMBITO_CHOICES,
        default="OBRA",
        blank=True,
    )
    centro_coste = models.ForeignKey(
        "gestion.CentroCosteGestion",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="facturas",
    )
    obra_planificacion = models.ForeignKey(
        "planificacion_obra.ObraPlanificacion",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="facturas_gestion",
    )


    # FACTURA_RECTIFICATIVA_V1
    TIPO_FACTURA_NORMAL = "NORMAL"
    TIPO_FACTURA_RECTIFICATIVA = "RECTIFICATIVA"

    TIPO_FACTURA_CHOICES = [
        (TIPO_FACTURA_NORMAL, "Normal"),
        (TIPO_FACTURA_RECTIFICATIVA, "Rectificativa"),
    ]

    SUBTIPO_RECTIFICATIVA_ABONO = "ABONO"
    SUBTIPO_RECTIFICATIVA_OTRA = "OTRA"

    SUBTIPO_RECTIFICATIVA_CHOICES = [
        ("", "—"),
        (SUBTIPO_RECTIFICATIVA_ABONO, "Abono"),
        (SUBTIPO_RECTIFICATIVA_OTRA, "Otra rectificativa"),
    ]

    tipo_factura = models.CharField(
        max_length=20,
        choices=TIPO_FACTURA_CHOICES,
        default=TIPO_FACTURA_NORMAL,
        db_index=True,
    )

    subtipo_rectificativa = models.CharField(
        max_length=20,
        choices=SUBTIPO_RECTIFICATIVA_CHOICES,
        blank=True,
        default="",
    )

    numero_factura_rectificada = models.CharField(
        max_length=120,
        blank=True,
        default="",
    )

    factura_rectificada = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="documentos_rectificativos",
    )

    raw_data = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Factura de proveedor"
        verbose_name_plural = "Facturas de proveedores"
        ordering = ["-fecha_emision", "-cod_factura"]
        constraints = [
            models.UniqueConstraint(
                fields=["team", "cod_factura"],
                name="uniq_gestion_factura_team_cod",
            )
        ]
        indexes = [
            models.Index(fields=["team", "cod_factura"]),
            models.Index(fields=["team", "fecha_emision"]),
            models.Index(fields=["team", "estado"]),
            models.Index(fields=["team", "proveedor"]),
            models.Index(fields=["empresa_legacy_raw"]),
        ]
        permissions = [
            (
                "edit_invoice_withholding",
                "Puede editar retenciones de facturas de proveedor",
            ),
        ]

    def __str__(self):
        return f"{self.cod_factura} - {self.num_factura_proveedor or self.proveedor}"


class AlbaranProveedorGestion(models.Model):
    team = models.ForeignKey(
        "usuarios.Team",
        on_delete=models.PROTECT,
        related_name="gestion_albaranes_proveedor",
    )

    empresa_legacy = models.ForeignKey(
        "gestion.EmpresaGestionLegacy",
        on_delete=models.PROTECT,
        related_name="albaranes_proveedor",
        null=True,
        blank=True,
    )

    proveedor = models.ForeignKey(
        "gestion.Proveedor",
        on_delete=models.SET_NULL,
        related_name="albaranes_gestion",
        null=True,
        blank=True,
    )

    cod_albaran = models.CharField(max_length=50)
    cod_obra_legacy = models.CharField(max_length=50, blank=True)
    cod_proveedor_legacy = models.IntegerField(null=True, blank=True)
    empresa_legacy_raw = models.IntegerField(null=True, blank=True)

    num_albaran_proveedor = models.CharField(max_length=120, blank=True)

    fecha_albaran = models.DateField(null=True, blank=True)
    fecha_entrega_mercaderia = models.DateField(null=True, blank=True)

    importe_albaran = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    importe_asignado_factura = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    descripcion = models.TextField(blank=True)
    recepcionado_por = models.CharField(max_length=160, blank=True)

    presupuesto = models.BooleanField(default=False)
    cod_presupuesto_legacy = models.CharField(max_length=50, blank=True)
    ok_presupuesto = models.BooleanField(default=False)

    autorizado_jefe_obra = models.BooleanField(default=False)
    asignado_partida_obra = models.BooleanField(default=False)
    asignado_factura = models.BooleanField(default=False)
    lineas_asignadas = models.IntegerField(default=0)

    situacion = models.CharField(max_length=80, blank=True)
    archivo = models.CharField(max_length=255, blank=True)


    # GESTION_TRAZABILIDAD_V1
    ORIGEN_ALTA_CHOICES = [
        ("LEGACY", "Legacy / importación histórica"),
        ("MANUAL", "Manual"),
        ("PDF_OCR", "PDF / OCR"),
        ("SYNC_ACCESS", "Sincronización MS Access"),
        ("SISTEMA", "Sistema"),
    ]
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="gestion_albaranes_creados",
    )
    modificado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="gestion_albaranes_modificados",
    )
    origen_alta = models.CharField(
        max_length=30,
        choices=ORIGEN_ALTA_CHOICES,
        default="LEGACY",
        blank=True,
    )


    # CENTRO_COSTE_GESTION_V1
    ambito_gestion = models.CharField(
        max_length=40,
        choices=GESTION_AMBITO_CHOICES,
        default="OBRA",
        blank=True,
    )
    centro_coste = models.ForeignKey(
        "gestion.CentroCosteGestion",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="albaranes",
    )
    obra_planificacion = models.ForeignKey(
        "planificacion_obra.ObraPlanificacion",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="albaranes_gestion",
    )

    raw_data = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Albarán de proveedor"
        verbose_name_plural = "Albaranes de proveedores"
        ordering = ["-fecha_albaran", "-cod_albaran"]
        constraints = [
            models.UniqueConstraint(
                fields=["team", "cod_albaran"],
                name="uniq_gestion_albaran_team_cod",
            )
        ]
        indexes = [
            models.Index(fields=["team", "cod_albaran"]),
            models.Index(fields=["team", "fecha_albaran"]),
            models.Index(fields=["team", "proveedor"]),
            models.Index(fields=["team", "asignado_factura"]),
            models.Index(fields=["empresa_legacy_raw"]),
        ]

    def __str__(self):
        return f"{self.cod_albaran} - {self.num_albaran_proveedor}"


class FacturaProveedorLineaGestion(models.Model):
    factura = models.ForeignKey(
        "gestion.FacturaProveedorGestion",
        on_delete=models.CASCADE,
        related_name="lineas",
    )

    albaran = models.ForeignKey(
        "gestion.AlbaranProveedorGestion",
        on_delete=models.SET_NULL,
        related_name="lineas_factura",
        null=True,
        blank=True,
    )

    linea = models.IntegerField()
    articulo_compra = models.ForeignKey(
        "gestion.ArticuloCompra",
        on_delete=models.SET_NULL,
        related_name="lineas_factura",
        null=True,
        blank=True,
    )
    cod_articulo_legacy = models.IntegerField(null=True, blank=True)

    cod_albaran_legacy = models.CharField(max_length=50, blank=True)
    linea_albaran_legacy = models.IntegerField(null=True, blank=True)

    cantidad = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    unidad_compra = models.CharField(max_length=30, blank=True)
    precio_unitario = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    importe_linea = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    importe_descuento = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    descuento = models.DecimalField(max_digits=10, decimal_places=4, default=0)

    en_partida = models.BooleanField(default=False)
    cantidad_en_partidas = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    en_almacen = models.BooleanField(default=False)
    # GESTION_FACTURA_LINEA_OBSERVACIONES_V1
    observaciones = models.TextField(blank=True)


    # GESTION_TRAZABILIDAD_V1
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="gestion_lineas_factura_creadas",
    )
    modificado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="gestion_lineas_factura_modificadas",
    )
    origen_alta = models.CharField(max_length=30, default="LEGACY", blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)

    raw_data = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "Línea de factura de proveedor"
        verbose_name_plural = "Líneas de facturas de proveedores"
        ordering = ["factura", "linea"]
        constraints = [
            models.UniqueConstraint(
                fields=["factura", "linea"],
                name="uniq_gestion_factura_linea",
            )
        ]
        indexes = [
            models.Index(fields=["factura", "linea"]),
            models.Index(fields=["albaran"]),
            models.Index(fields=["articulo_compra"]),
            models.Index(fields=["cod_articulo_legacy"]),
        ]

    def __str__(self):
        return f"{self.factura.cod_factura} / Línea {self.linea}"


class AlbaranProveedorLineaGestion(models.Model):
    albaran = models.ForeignKey(
        "gestion.AlbaranProveedorGestion",
        on_delete=models.CASCADE,
        related_name="lineas",
    )

    linea = models.IntegerField()
    articulo_compra = models.ForeignKey(
        "gestion.ArticuloCompra",
        on_delete=models.SET_NULL,
        related_name="lineas_albaran",
        null=True,
        blank=True,
    )
    cod_articulo_legacy = models.IntegerField(null=True, blank=True)

    cantidad = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    unidad = models.CharField(max_length=30, blank=True)

    cantidad_compra = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    unidad_compra = models.CharField(max_length=30, blank=True)
    cantidad_x_unidad = models.DecimalField(max_digits=14, decimal_places=4, default=0)

    precio_unitario = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    importe_linea = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    facturado = models.BooleanField(default=False)
    factura_legacy = models.CharField(max_length=50, blank=True)

    en_pedido = models.BooleanField(default=False)
    en_partida = models.BooleanField(default=False)

    fecha_entrega = models.DateField(null=True, blank=True)
    recepcionado_por = models.CharField(max_length=160, blank=True)

    importe_descuento = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    descuento = models.DecimalField(max_digits=10, decimal_places=4, default=0)

    id_almacen_legacy = models.IntegerField(null=True, blank=True)
    observaciones = models.TextField(blank=True)
    tipo_recurso = models.CharField(max_length=80, blank=True)

    cantidad_en_partidas = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    en_almacen = models.BooleanField(default=False)


    # GESTION_TRAZABILIDAD_V1
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="gestion_lineas_albaran_creadas",
    )
    modificado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="gestion_lineas_albaran_modificadas",
    )
    origen_alta = models.CharField(max_length=30, default="LEGACY", blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)

    raw_data = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "Línea de albarán de proveedor"
        verbose_name_plural = "Líneas de albaranes de proveedores"
        ordering = ["albaran", "linea"]
        constraints = [
            models.UniqueConstraint(
                fields=["albaran", "linea"],
                name="uniq_gestion_albaran_linea",
            )
        ]
        indexes = [
            models.Index(fields=["albaran", "linea"]),
            models.Index(fields=["articulo_compra"]),
            models.Index(fields=["cod_articulo_legacy"]),
            models.Index(fields=["facturado"]),
        ]

    def __str__(self):
        return f"{self.albaran.cod_albaran} / Línea {self.linea}"



class FacturaAlbaranGestion(models.Model):
    team = models.ForeignKey(
        "usuarios.Team",
        on_delete=models.PROTECT,
        related_name="gestion_factura_albaran_vinculos",
    )

    factura = models.ForeignKey(
        "gestion.FacturaProveedorGestion",
        on_delete=models.CASCADE,
        related_name="albaranes_vinculados",
    )

    albaran = models.ForeignKey(
        "gestion.AlbaranProveedorGestion",
        on_delete=models.PROTECT,
        related_name="facturas_vinculadas",
    )

    importe_asignado = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    observaciones = models.TextField(blank=True)


    # GESTION_TRAZABILIDAD_V1
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="gestion_vinculos_factura_albaran_creados",
    )
    modificado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="gestion_vinculos_factura_albaran_modificados",
    )
    origen_alta = models.CharField(max_length=30, default="LEGACY", blank=True)

    raw_data = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Vínculo factura-albarán"
        verbose_name_plural = "Vínculos factura-albarán"
        ordering = ["factura", "albaran"]
        constraints = [
            models.UniqueConstraint(
                fields=["factura", "albaran"],
                name="uniq_gestion_factura_albaran",
            )
        ]
        indexes = [
            models.Index(fields=["team", "factura"]),
            models.Index(fields=["team", "albaran"]),
        ]

    def __str__(self):
        return f"{self.factura.cod_factura} ← {self.albaran.cod_albaran}"

def gestion_compra_adjunto_upload_to(instance, filename):
    import os
    import uuid

    original = filename or "documento.pdf"
    _, ext = os.path.splitext(original)
    ext = (ext or ".pdf").lower()

    team_id = instance.team_id or "sin_team"

    if instance.factura_id:
        carpeta = "facturas"
        objeto_id = instance.factura_id
    elif instance.albaran_id:
        carpeta = "albaranes"
        objeto_id = instance.albaran_id
    else:
        carpeta = "otros"
        objeto_id = "sin_id"

    return f"gestion/compras/{team_id}/{carpeta}/{objeto_id}/{uuid.uuid4().hex}{ext}"


class DocumentoCompraAdjunto(models.Model):
    TIPO_FACTURA_PDF = "FACTURA_PDF"
    TIPO_ALBARAN_PDF = "ALBARAN_PDF"
    TIPO_ANEXO = "ANEXO"
    TIPO_OTRO = "OTRO"

    TIPO_DOCUMENTO_CHOICES = [
        (TIPO_FACTURA_PDF, "PDF factura"),
        (TIPO_ALBARAN_PDF, "PDF albarán"),
        (TIPO_ANEXO, "Anexo"),
        (TIPO_OTRO, "Otro"),
    ]

    OCR_PENDIENTE = "PENDIENTE"
    OCR_NO_APLICA = "NO_APLICA"
    OCR_PROCESANDO = "PROCESANDO"
    OCR_COMPLETADO = "COMPLETADO"
    OCR_ERROR = "ERROR"

    OCR_ESTADO_CHOICES = [
        (OCR_PENDIENTE, "Pendiente"),
        (OCR_NO_APLICA, "No aplica"),
        (OCR_PROCESANDO, "Procesando"),
        (OCR_COMPLETADO, "Completado"),
        (OCR_ERROR, "Error"),
    ]

    team = models.ForeignKey(
        "usuarios.Team",
        on_delete=models.PROTECT,
        related_name="gestion_documentos_compra",
    )
    factura = models.ForeignKey(
        "gestion.FacturaProveedorGestion",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="adjuntos",
    )
    albaran = models.ForeignKey(
        "gestion.AlbaranProveedorGestion",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="adjuntos",
    )

    archivo = models.FileField(
        upload_to=gestion_compra_adjunto_upload_to,
        max_length=500,
    )

    tipo_documento = models.CharField(
        max_length=30,
        choices=TIPO_DOCUMENTO_CHOICES,
        default=TIPO_OTRO,
    )
    nombre_original = models.CharField(max_length=255)
    tamano_bytes = models.PositiveBigIntegerField(default=0)
    content_type = models.CharField(max_length=120, blank=True)

    subido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gestion_documentos_compra_subidos",
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    ocr_estado = models.CharField(
        max_length=20,
        choices=OCR_ESTADO_CHOICES,
        default=OCR_PENDIENTE,
    )
    ocr_texto = models.TextField(blank=True)
    ocr_json = models.JSONField(null=True, blank=True)
    ocr_error = models.TextField(blank=True)

    class Meta:
        verbose_name = "Documento adjunto de compra"
        verbose_name_plural = "Documentos adjuntos de compra"
        ordering = ["-creado_en", "-id"]
        indexes = [
            models.Index(fields=["team", "tipo_documento"]),
            models.Index(fields=["factura"]),
            models.Index(fields=["albaran"]),
            models.Index(fields=["ocr_estado"]),
        ]
        constraints = [
            models.CheckConstraint(
                name="gestion_adjunto_factura_o_albaran",
                check=(
                    models.Q(factura__isnull=False, albaran__isnull=True)
                    | models.Q(factura__isnull=True, albaran__isnull=False)
                ),
            ),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError

        if bool(self.factura_id) == bool(self.albaran_id):
            raise ValidationError(
                "El adjunto debe estar vinculado a una factura o a un albarán, pero no a ambos."
            )

    def __str__(self):
        destino = self.factura_id or self.albaran_id or "-"
        return f"{self.nombre_original} [{self.tipo_documento}] #{destino}"



class GestionAccessSyncRun(models.Model):
    class Mode(models.TextChoices):
        DRY_RUN = "DRY_RUN", "Dry-run"
        COMMIT = "COMMIT", "Commit"

    class Status(models.TextChoices):
        RUNNING = "RUNNING", "En ejecución"
        OK = "OK", "Correcto"
        ERROR = "ERROR", "Error"

    source_path = models.CharField(max_length=500)
    mode = models.CharField(max_length=20, choices=Mode.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RUNNING)
    backup_path = models.CharField(max_length=500, blank=True)
    output_text = models.TextField(blank=True)
    error_text = models.TextField(blank=True)
    meta = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.mode} · {self.status} · {self.source_path}"


# === OCR_PLANTILLAS_PROVEEDOR_V1 ===
class PlantillaOCRProveedor(models.Model):
    class TipoDocumento(models.TextChoices):
        ALBARAN = "ALBARAN", "Albarán"
        FACTURA = "FACTURA", "Factura"

    team = models.ForeignKey(
        "usuarios.Team",
        on_delete=models.CASCADE,
        related_name="plantillas_ocr_proveedor",
    )
    proveedor = models.ForeignKey(
        "gestion.Proveedor",
        on_delete=models.CASCADE,
        related_name="plantillas_ocr",
    )

    tipo_documento = models.CharField(
        max_length=20,
        choices=TipoDocumento.choices,
        db_index=True,
    )
    codigo = models.CharField(
        max_length=80,
        help_text="Código interno estable de plantilla, por ejemplo divelec_albaran_valorado_v1.",
    )
    nombre = models.CharField(max_length=160)
    variante = models.CharField(max_length=120, blank=True)

    activa = models.BooleanField(default=True, db_index=True)
    prioridad = models.PositiveIntegerField(default=100)

    parser_key = models.CharField(
        max_length=120,
        help_text="Clave del parser a aplicar para esta plantilla.",
    )
    valorado_default = models.BooleanField(
        default=True,
        help_text="Indica si por defecto las líneas vienen valoradas con precio/importe.",
    )

    detector_texto = models.TextField(
        blank=True,
        help_text="Texto orientativo esperado para comprobar si el PDF parece coincidir con la plantilla.",
    )
    config_json = models.JSONField(
        default=dict,
        blank=True,
        help_text="Configuración flexible de regex, columnas, totales y reglas de líneas.",
    )

    descripcion = models.TextField(blank=True)

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["team", "proveedor", "tipo_documento", "prioridad", "nombre"]
        verbose_name = "Plantilla OCR de proveedor"
        verbose_name_plural = "Plantillas OCR de proveedor"
        constraints = [
            models.UniqueConstraint(
                fields=["team", "proveedor", "tipo_documento", "codigo"],
                name="uniq_gestion_ocr_tpl_proveedor_tipo_codigo",
            ),
        ]
        indexes = [
            models.Index(fields=["team", "tipo_documento", "activa"], name="idx_gocr_tpl_team_tipo_act"),
            models.Index(fields=["proveedor", "tipo_documento", "activa"], name="idx_gocr_tpl_prov_tipo_act"),
        ]

    def __str__(self):
        estado = "activa" if self.activa else "inactiva"
        return f"{self.proveedor} · {self.get_tipo_documento_display()} · {self.nombre} ({estado})"




class CentroCosteGestion(models.Model):
    # CENTRO_COSTE_GESTION_V1
    team = models.ForeignKey(
        "usuarios.Team",
        on_delete=models.CASCADE,
        related_name="centros_coste_gestion",
    )
    codigo = models.CharField(max_length=80)
    nombre = models.CharField(max_length=180)
    tipo = models.CharField(
        max_length=40,
        choices=GESTION_AMBITO_CHOICES,
        default="SIN_CLASIFICAR",
    )
    obra_planificacion = models.ForeignKey(
        "planificacion_obra.ObraPlanificacion",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="centros_coste_gestion",
    )
    activo = models.BooleanField(default=True)
    observaciones = models.TextField(blank=True)
    raw_data = models.JSONField(default=dict, blank=True)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="centros_coste_gestion_creados",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["team__name", "tipo", "codigo", "nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=["team", "codigo"],
                name="uniq_gestion_centro_coste_team_codigo",
            ),
        ]
        indexes = [
            models.Index(fields=["team", "tipo"]),
            models.Index(fields=["team", "activo"]),
        ]

    def __str__(self):
        return f"{self.codigo} · {self.nombre}"


class GestionAuditLog(models.Model):
    # GESTION_TRAZABILIDAD_V1
    ACCION_CHOICES = [
        ("CREADO", "Creado"),
        ("MODIFICADO", "Modificado"),
        ("ELIMINADO", "Eliminado"),
        ("PDF_SUBIDO", "PDF subido"),
        ("OCR_LEIDO", "OCR leído"),
        ("LINEAS_OCR_IMPORTADAS", "Líneas OCR importadas"),
        ("RECALCULO_IMPORTES", "Recálculo de importes"),
        ("VINCULO_CREADO", "Vínculo creado"),
        ("VINCULO_ELIMINADO", "Vínculo eliminado"),
        ("BACKFILL", "Backfill trazabilidad"),
    ]

    team = models.ForeignKey(AlbaranProveedorGestion._meta.get_field("team").remote_field.model, null=True, blank=True, on_delete=models.SET_NULL)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    accion = models.CharField(max_length=60, choices=ACCION_CHOICES)
    entidad = models.CharField(max_length=120)
    objeto_id = models.PositiveBigIntegerField(null=True, blank=True)
    objeto_repr = models.CharField(max_length=255, blank=True)

    albaran = models.ForeignKey(
        "gestion.AlbaranProveedorGestion",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
    )
    factura = models.ForeignKey(
        "gestion.FacturaProveedorGestion",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
    )
    adjunto = models.ForeignKey(
        "gestion.DocumentoCompraAdjunto",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
    )

    descripcion = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["entidad", "objeto_id"]),
            models.Index(fields=["accion", "created_at"]),
            models.Index(fields=["team", "created_at"]),
        ]

    def __str__(self):
        user = self.usuario.get_username() if self.usuario else "Sistema"
        return f"{self.created_at:%Y-%m-%d %H:%M} · {user} · {self.accion} · {self.entidad}#{self.objeto_id}"

# FACTURA_PAGOS_MULTIPLES_V1
class FacturaVencimientoGestion(models.Model):
    ESTADO_PENDIENTE = "PENDIENTE"
    ESTADO_PAGADO = "PAGADO"
    ESTADO_ANULADO = "ANULADO"

    ESTADO_CHOICES = [
        (ESTADO_PENDIENTE, "Pendiente"),
        (ESTADO_PAGADO, "Pagado"),
        (ESTADO_ANULADO, "Anulado"),
    ]

    team = models.ForeignKey(
        "usuarios.Team",
        on_delete=models.PROTECT,
        related_name="gestion_factura_vencimientos",
    )

    factura = models.ForeignKey(
        "gestion.FacturaProveedorGestion",
        on_delete=models.CASCADE,
        related_name="vencimientos_pago",
    )

    numero_pago = models.PositiveIntegerField()

    fecha_vencimiento = models.DateField()

    importe_previsto = models.DecimalField(
        max_digits=14,
        decimal_places=2,
    )

    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default=ESTADO_PENDIENTE,
    )

    fecha_real_pago = models.DateField(
        null=True,
        blank=True,
    )

    importe_pagado = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
    )

    forma_pago = models.CharField(
        max_length=160,
        blank=True,
    )

    referencia_pago = models.CharField(
        max_length=255,
        blank=True,
    )

    observaciones = models.TextField(
        blank=True,
    )

    autorizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="gestion_vencimientos_autorizados",
    )

    pagado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="gestion_vencimientos_pagados",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        verbose_name = "Vencimiento de factura"
        verbose_name_plural = "Vencimientos de facturas"
        ordering = [
            "fecha_vencimiento",
            "numero_pago",
        ]
        permissions = [
            (
                "authorize_factura_payment_plan",
                "Puede autorizar planes de pago de facturas",
            ),
            (
                "register_factura_installment_payment",
                "Puede registrar pagos de vencimientos",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "factura",
                    "numero_pago",
                ],
                name="uniq_gestion_factura_venc_num",
            ),
            models.CheckConstraint(
                check=models.Q(
                    importe_previsto__gt=0
                ) | models.Q(
                    importe_previsto__lt=0
                ),
                name="chk_gestion_venc_importe_pos",
            ),
            models.CheckConstraint(
                check=models.Q(
                    importe_pagado__gte=0
                ) | models.Q(
                    importe_pagado__lt=0
                ),
                name="chk_gestion_venc_pagado_nonneg",
            ),
        ]
        indexes = [
            models.Index(
                fields=[
                    "team",
                    "fecha_vencimiento",
                ],
                name="gestion_venc_team_fecha_idx",
            ),
            models.Index(
                fields=[
                    "factura",
                    "estado",
                ],
                name="gestion_venc_fact_est_idx",
            ),
        ]

    def __str__(self):
        return (
            f"{self.factura.cod_factura} · "
            f"Pago {self.numero_pago} · "
            f"{self.fecha_vencimiento}"
        )

# GESTION_UNIDADES_COMPRA_V1A_SIGNALS
from . import purchase_memory_signals_v1  # noqa: E402,F401
