from django import forms
from django.db.models import Q

from apps.gestion.models import (
    Proveedor,
    AlbaranProveedorGestion,
    AlbaranProveedorLineaGestion,
    FacturaProveedorGestion,
    FacturaProveedorLineaGestion,
)


def _gestion_normalize_spanish_decimal(value):
    """Acepta 5,00 y 1.179,80 además del formato técnico Decimal."""
    raw = str(value or "").strip().replace("€", "").replace("EUR", "")
    raw = raw.replace("\xa0", "").replace(" ", "")
    if "," in raw and "." in raw:
        if raw.rfind(",") > raw.rfind("."):
            return raw.replace(".", "").replace(",", ".")
        return raw.replace(",", "")
    if "," in raw:
        return raw.replace(",", ".")
    return raw


class GestionSpanishDecimalField(forms.DecimalField):
    def to_python(self, value):
        return super().to_python(_gestion_normalize_spanish_decimal(value))


def aplicar_estilo(form):
    for field in form.fields.values():
        if isinstance(field.widget, forms.CheckboxInput):
            field.widget.attrs.update({"class": "form-check-input"})
        elif isinstance(field.widget, forms.Textarea):
            field.widget.attrs.update({"class": "form-control form-control-sm"})
        else:
            field.widget.attrs.update({"class": "form-control form-control-sm"})



def _gestion_align_numeric_fields(form):
    """
    Alinea a la derecha los campos numéricos y monetarios en formularios de Gestión.
    Solo modifica atributos HTML del widget.
    """
    numeric_names = {
        "linea",
        "cantidad",
        "cantidad_compra",
        "cantidad_x_unidad",
        "cantidad_en_partidas",
        "precio_unitario",
        "importe_linea",
        "importe_descuento",
        "descuento",
        "importe_albaran",
        "importe_asignado_factura",
        "importe_base_imponible",
        "importe_iva",
        "importe_factura",
        "retencion",
        "importe_pagado",
        "base",
        "iva",
        "total",
    }

    numeric_field_types = (
        forms.DecimalField,
        forms.IntegerField,
        forms.FloatField,
    )

    for name, field in form.fields.items():
        widget = field.widget
        input_type = getattr(widget, "input_type", "") or ""

        if input_type in {"checkbox", "select", "select-multiple", "file", "date"}:
            continue

        is_numeric = name in numeric_names or isinstance(field, numeric_field_types)

        if not is_numeric:
            continue

        current_class = widget.attrs.get("class", "")
        classes = current_class.split()

        if "text-end" not in classes:
            classes.append("text-end")

        widget.attrs["class"] = " ".join(classes).strip()
        widget.attrs.setdefault("inputmode", "decimal")

        if isinstance(field, forms.IntegerField):
            widget.attrs.setdefault("step", "1")
        else:
            widget.attrs.setdefault("step", "any")




class ProveedorForm(forms.ModelForm):
    class Meta:
        model = Proveedor
        fields = [
            "nombre_comercial",
            "nombre_fiscal",
            "cif",
            "direccion",
            "cod_postal",
            "poblacion",
            "provincia",
            "pais",
            "email",
            "telefono",
            "contacto_comercial",
            "tel_contacto_comercial",
            "contacto_admin",
            "tel_contacto_admin",
            "sp_iva",
            "aplica_retencion_habitual",
            "retencion_habitual_porcentaje",
            "es_subcontrata",
            "fuera_listado",
            "activo",
            "observaciones",
        ]
        widgets = {
            "observaciones": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        self.can_manage_retention = bool(kwargs.pop("can_manage_retention", False))
        super().__init__(*args, **kwargs)
        if not self.can_manage_retention:
            self.fields.pop("aplica_retencion_habitual", None)
            self.fields.pop("retencion_habitual_porcentaje", None)
        aplicar_estilo(self)
        _gestion_align_numeric_fields(self)


# GESTION_FORMULARIOS_AMBITO_VISIBLE_V1
# GESTION_FORMULARIOS_AMBITO_VISIBLE_V2
class AlbaranProveedorForm(forms.ModelForm):
    class Meta:
        model = AlbaranProveedorGestion
        fields = [
            "proveedor",
            "ambito_gestion",
            "num_albaran_proveedor",
            "fecha_albaran",
            "fecha_entrega_mercaderia",
            "importe_albaran",
            "descripcion",
            "recepcionado_por",
            "presupuesto",
            "cod_presupuesto_legacy",
            "ok_presupuesto",
            "autorizado_jefe_obra",
            "asignado_partida_obra",
            "asignado_factura",
            "situacion",
        ]
        widgets = {
            "fecha_albaran": forms.DateInput(attrs={"type": "date"}),
            "fecha_entrega_mercaderia": forms.DateInput(attrs={"type": "date"}),
            "descripcion": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        team = kwargs.pop("team", None)

        self.team = team  # ANTI_DUP_ALBARAN_PROVEEDOR_FORM_TEAM_ATTR_V1
        super().__init__(*args, **kwargs)

        if team:
            self.fields["proveedor"].queryset = Proveedor.objects.filter(team=team, activo=True).order_by("nombre_comercial")
        else:
            self.fields["proveedor"].queryset = Proveedor.objects.none()

        self.fields["proveedor"].required = True

        
        if "ambito_gestion" in self.fields:
            self.fields["ambito_gestion"].label = "Ámbito"
            self.fields["ambito_gestion"].required = True
            self.fields["ambito_gestion"].help_text = "El centro de coste se asignará automáticamente."
            if not getattr(self.instance, "pk", None) and not self.data.get("ambito_gestion"):
                self.fields["ambito_gestion"].initial = "OBRA"
        aplicar_estilo(self)
        _gestion_align_numeric_fields(self)

    def clean(self):
        cleaned = super().clean()
        # ANTI_DUP_ALBARAN_PROVEEDOR_FORM_V1
        team = getattr(self, "team", None) or getattr(getattr(self, "instance", None), "team", None)
        proveedor = cleaned.get("proveedor")
        num_albaran = (cleaned.get("num_albaran_proveedor") or "").strip()

        placeholders = {
            "S/N", "S / N", "SN", "S\\N",
            "SIN NUMERO", "SIN NÚMERO",
            "NO TIENE", "-", "--", ".", "0", "0000",
        }
        num_norm = " ".join(num_albaran.upper().replace("\\", "/").split())
        num_norm = num_norm.replace("S / N", "S/N")

        if team and proveedor and num_albaran and num_norm not in placeholders:
            qs_dup = self.Meta.model.objects.filter(
                team=team,
                proveedor=proveedor,
                num_albaran_proveedor__iexact=num_albaran,
            )
            if getattr(self.instance, "pk", None):
                qs_dup = qs_dup.exclude(pk=self.instance.pk)

            dup = qs_dup.order_by("id").first()
            if dup:
                self.add_error(
                    "num_albaran_proveedor",
                    (
                        "Ya existe un albarán para este proveedor con este número "
                        f"en la misma empresa/equipo: {getattr(dup, 'cod_albaran', '')} "
                        f"(id {dup.pk})."
                    ),
                )


        if cleaned.get("fecha_albaran") and not cleaned.get("fecha_entrega_mercaderia"):
            cleaned["fecha_entrega_mercaderia"] = cleaned["fecha_albaran"]

        return cleaned


FACTURA_FORMA_PAGO_DIAS = [
    ("CONTADO", 0),
    # RECIBO_DOMICILIADO_INMEDIATO_V1
    ("RECIBO DOMICILIADO", 0),
    ("PAGARE 30 D.F.F.", 30),
    ("PAGARE 60 D.F.F.", 60),
    ("PAGARE 90 D.F.F.", 90),
    ("RECIBO DOMICILIADO 30 D.F.F.", 30),
    ("RECIBO DOMICILIADO 60 D.F.F.", 60),
    ("TARJETA CREDITO", 0),
    ("TRANSFERENCIA", 0),
    ("DEVOLUCION", 0),
    ("TRANSFERENCIA 30 D.F.F.", 30),
    ("TRANSFERENCIA 45 D.F.F.", 45),
    ("TRANSFERENCIA 60 D.F.F.", 60),
    ("4 MESES", 120),
]



# FACTURA_FORM_DATE_ISO_V2
def _factura_form_apply_iso_date_widgets_v2(form):
    from django import forms as _forms

    date_fields = [
        "fecha_emision",
        "fecha_autorizacion_gerencia",
        "fecha_pago_segun_contrato",
        "fecha_real_pago",
    ]

    for name in date_fields:
        if name not in form.fields:
            continue

        field = form.fields[name]
        old_attrs = dict(getattr(field.widget, "attrs", {}) or {})
        old_attrs["type"] = "date"

        # Mantener clase visual si existe; si no, aplicar Bootstrap.
        old_attrs["class"] = old_attrs.get("class", "form-control")

        field.input_formats = ["%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"]
        field.widget = _forms.DateInput(
            format="%Y-%m-%d",
            attrs=old_attrs,
        )

        current = getattr(getattr(form, "instance", None), name, None)
        if current and not form.is_bound:
            form.initial[name] = current.strftime("%Y-%m-%d")


def _factura_form_restore_existing_dates_if_blank_v2(form, cleaned):
    """
    Protección operativa: si una fecha existente llega vacía en edición
    por un problema de render/browser, no se pisa a NULL al guardar.
    """
    if not getattr(form, "instance", None) or not getattr(form.instance, "pk", None):
        return cleaned

    for name in [
        "fecha_emision",
        "fecha_autorizacion_gerencia",
        "fecha_pago_segun_contrato",
        "fecha_real_pago",
    ]:
        if name not in form.fields:
            continue

        posted = ""
        try:
            posted = (form.data.get(name) or "").strip()
        except Exception:
            posted = ""

        if not posted and not cleaned.get(name):
            current = getattr(form.instance, name, None)
            if current:
                cleaned[name] = current

    return cleaned


class FacturaProveedorForm(forms.ModelForm):
    iva_porcentaje = forms.DecimalField(
        label="% IVA",
        required=False,
        initial=21,
        max_digits=6,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
    )
    retencion_porcentaje = GestionSpanishDecimalField(
        label="% retención",
        required=False,
        initial=15,
        max_digits=6,
        decimal_places=2,
        widget=forms.TextInput(attrs={"inputmode": "decimal", "autocomplete": "off"}),
    )
    factura_pagada = forms.BooleanField(
        label="Factura pagada",
        required=False,
    )

    class Meta:
        model = FacturaProveedorGestion
        fields = [
            "proveedor",
            "ambito_gestion",
            "num_factura_proveedor",
            "fecha_emision",
            "fecha_autorizacion_gerencia",
            "fecha_pago_segun_contrato",
            "fecha_real_pago",
            "importe_base_imponible",
            "importe_iva",
            "importe_factura",
            "retencion_porcentaje",
            "retencion",
            "importe_pagado",
            "forma_pago",
            "estado",
            "observaciones",
            "asignada",
            "tiene_retencion",
            "generado_albaran",
            "certificada",
            "archivo",
            "archivo1",
        ]
        widgets = {
            "fecha_emision": forms.DateInput(attrs={"type": "date"}),
            "fecha_autorizacion_gerencia": forms.DateInput(attrs={"type": "date"}),
            "fecha_pago_segun_contrato": forms.DateInput(attrs={"type": "date"}),
            "fecha_real_pago": forms.DateInput(attrs={"type": "date"}),
            "observaciones": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        team = kwargs.pop("team", None)
        self.can_manage_retention = bool(kwargs.pop("can_manage_retention", False))
        super().__init__(*args, **kwargs)

        # Los importes se presentan como ES (miles y coma) por JavaScript;
        # normalizamos también el POST para que la validación del servidor sea
        # idéntica aunque JS esté desactivado o un cliente manipule el envío.
        if self.is_bound:
            data = self.data.copy()
            for name in (
                "importe_base_imponible", "importe_iva", "importe_factura",
                "retencion", "importe_pagado", "iva_porcentaje",
            ):
                key = self.add_prefix(name)
                if key in data:
                    data[key] = _gestion_normalize_spanish_decimal(data[key])
            self.data = data

        if team:
            self.fields["proveedor"].queryset = Proveedor.objects.filter(team=team, activo=True).order_by("nombre_comercial")
        else:
            self.fields["proveedor"].queryset = Proveedor.objects.none()

        self.fields["proveedor"].required = True

        
        if "ambito_gestion" in self.fields:
            self.fields["ambito_gestion"].label = "Ámbito"
            self.fields["ambito_gestion"].required = True
            self.fields["ambito_gestion"].help_text = "El centro de coste se asignará automáticamente."
            if not getattr(self.instance, "pk", None) and not self.data.get("ambito_gestion"):
                self.fields["ambito_gestion"].initial = "OBRA"

        estado_choices = [
            ("PENDIENTE", "PENDIENTE"),
            ("PAGADA", "PAGADA"),
            ("VENCIDA", "VENCIDA"),
            ("PAGARE ENTR.", "PAGARE ENTR."),
        ]
        current_estado = getattr(self.instance, "estado", "") if self.instance else ""
        if current_estado and current_estado not in [value for value, _label in estado_choices]:
            estado_choices.append((current_estado, current_estado))
        self.fields["estado"].widget = forms.Select(choices=estado_choices)

        forma_choices = [("", "---------")] + [(nombre, nombre) for nombre, _dias in FACTURA_FORMA_PAGO_DIAS]
        current_forma = getattr(self.instance, "forma_pago", "") if self.instance else ""
        if current_forma and current_forma not in [value for value, _label in forma_choices]:
            forma_choices.append((current_forma, current_forma))
        self.fields["forma_pago"].widget = forms.Select(choices=forma_choices)

        for name in ["importe_base_imponible", "importe_iva", "importe_factura", "retencion", "importe_pagado"]:
            self.fields[name].required = False

        if not self.instance.pk:
            self.fields["estado"].initial = "PENDIENTE"

        from decimal import Decimal, ROUND_HALF_UP

        base = getattr(self.instance, "importe_base_imponible", None) or Decimal("0.00")
        iva = getattr(self.instance, "importe_iva", None) or Decimal("0.00")
        ret = getattr(self.instance, "retencion", None) or Decimal("0.00")

        if base:
            self.fields["iva_porcentaje"].initial = ((iva / base) * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if ret:
                self.fields["retencion_porcentaje"].initial = ((ret / base) * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        else:
            self.fields["iva_porcentaje"].initial = Decimal("21.00")
            self.fields["retencion_porcentaje"].initial = Decimal("0.00")

        if not self.can_manage_retention:
            # El cálculo se conserva para facturas históricas, pero un POST no
            # puede alterar retención sin el permiso funcional explícito.
            self.fields["retencion_porcentaje"].disabled = True
            self.fields["retencion"].disabled = True
            self.fields["tiene_retencion"].disabled = True
        else:
            self.fields["retencion"].widget.attrs["readonly"] = True
            self.fields["retencion"].widget.attrs["aria-readonly"] = "true"

        aplicar_estilo(self)
        _gestion_align_numeric_fields(self)


        # FACTURA_PAGOS_MULTIPLES_FORM_LOCK_V1
        try:
            tiene_plan_pagos = bool(
                getattr(self.instance, "pk", None)
                and self.instance.vencimientos_pago.exists()
            )
        except Exception:
            tiene_plan_pagos = False

        if tiene_plan_pagos:
            self.fields["factura_pagada"].initial = (
                (self.instance.estado or "").upper()
                == "PAGADA"
            )

            for field_name in [
                "estado",
                "fecha_autorizacion_gerencia",
                "fecha_pago_segun_contrato",
                "fecha_real_pago",
                "importe_pagado",
                "factura_pagada",
            ]:
                if field_name in self.fields:
                    self.fields[field_name].disabled = True

        _factura_form_apply_iso_date_widgets_v2(self)
    def clean(self):
        from datetime import date, timedelta
        from decimal import Decimal, ROUND_HALF_UP

        cleaned = super().clean()
        cleaned = _factura_form_restore_existing_dates_if_blank_v2(self, cleaned)

        for name in ["importe_base_imponible", "importe_iva", "importe_factura", "retencion", "importe_pagado"]:
            if cleaned.get(name) is None:
                cleaned[name] = Decimal("0.00")

        base = cleaned.get("importe_base_imponible") or Decimal("0.00")
        iva_pct = cleaned.get("iva_porcentaje")
        ret_pct = cleaned.get("retencion_porcentaje")

        if iva_pct is None:
            iva_pct = Decimal("21.00")
        if ret_pct is None and self.can_manage_retention:
            proveedor = cleaned.get("proveedor")
            if getattr(proveedor, "aplica_retencion_habitual", False):
                ret_pct = getattr(proveedor, "retencion_habitual_porcentaje", Decimal("0.00"))
        if ret_pct is None:
            ret_pct = Decimal("0.00")

        if not self.can_manage_retention:
            ret_pct = (
                getattr(self.instance, "retencion_porcentaje", Decimal("0.00"))
                if getattr(self.instance, "pk", None)
                else Decimal("0.00")
            ) or Decimal("0.00")

        if ret_pct < Decimal("0.00"):
            self.add_error("retencion_porcentaje", "El porcentaje de retención no puede ser negativo.")

        # Activar o editar la retención no puede modificar IVA/base por un
        # redondeo colateral. Solo se recalcula IVA si se altera la base o su
        # porcentaje (las altas nuevas siempre se calculan por porcentaje).
        iva = cleaned.get("importe_iva") or Decimal("0.00")
        base_original = getattr(self.instance, "importe_base_imponible", Decimal("0.00")) or Decimal("0.00")
        iva_original = getattr(self.instance, "importe_iva", Decimal("0.00")) or Decimal("0.00")
        iva_pct_original = (
            (iva_original / base_original) * Decimal("100")
            if base_original else Decimal("21.00")
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if not getattr(self.instance, "pk", None) or base != base_original or iva_pct != iva_pct_original:
            iva = (base * iva_pct / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # El porcentaje solo aplica cuando el usuario lo activa. El importe
        # enviado no participa: siempre se deriva de base y porcentaje.
        if not cleaned.get("tiene_retencion"):
            ret_pct = Decimal("0.00")
        retencion = (base * ret_pct / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        
        total = (base + iva - retencion).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        cleaned["importe_iva"] = iva
        cleaned["retencion"] = retencion
        cleaned["retencion_porcentaje"] = ret_pct.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        cleaned["tiene_retencion"] = retencion != Decimal("0.00")
        cleaned["importe_factura"] = total

        fecha_emision = cleaned.get("fecha_emision")
        forma_pago = cleaned.get("forma_pago") or ""
        dias_pago = dict(FACTURA_FORMA_PAGO_DIAS).get(forma_pago)

        if fecha_emision and dias_pago is not None and not cleaned.get("fecha_pago_segun_contrato"):
            cleaned["fecha_pago_segun_contrato"] = fecha_emision + timedelta(days=dias_pago)

        # FACTURA_ESTADO_PAGADA_SYNC_BACKEND_V2
        #
        # IMPORTANTE:
        #
        # Estado textual PAGADA y pago real no son lo mismo.
        #
        # Solo el checkbox explícito "Factura pagada" crea
        # automáticamente evidencia económica:
        #
        # - importe_pagado = total;
        # - fecha_real_pago = hoy;
        # - estado = PAGADA.
        #
        # Si la factura ya llega con estado PAGADA pero el checkbox
        # no se ha marcado explícitamente, se conserva el estado
        # sin fabricar un pago que no existe.
        estado_actual = (
            cleaned.get("estado")
            or ""
        ).upper()

        factura_pagada_explicitamente = bool(
            cleaned.get(
                "factura_pagada"
            )
        )

        if factura_pagada_explicitamente:
            cleaned["factura_pagada"] = True
            cleaned["importe_pagado"] = total

            if not cleaned.get(
                "fecha_real_pago"
            ):
                cleaned[
                    "fecha_real_pago"
                ] = date.today()

            cleaned["estado"] = "PAGADA"

        elif estado_actual == "PAGADA":
            cleaned["factura_pagada"] = False

            # En una edición no convertimos una PAGADA administrativa
            # en un pago real por el mero hecho de guardar el formulario.
            if getattr(
                self.instance,
                "pk",
                None,
            ):
                cleaned[
                    "importe_pagado"
                ] = (
                    self.instance.importe_pagado
                    or Decimal("0.00")
                )

                cleaned[
                    "fecha_real_pago"
                ] = (
                    self.instance.fecha_real_pago
                )

        # FACTURA_PAGOS_MULTIPLES_FORM_GUARD_V1
        try:
            tiene_plan_pagos = bool(
                getattr(self.instance, "pk", None)
                and self.instance.vencimientos_pago.exists()
            )
        except Exception:
            tiene_plan_pagos = False

        if tiene_plan_pagos:
            total_original = (
                self.instance.importe_factura
                or Decimal("0.00")
            ).quantize(Decimal("0.01"))

            if total != total_original:
                self.add_error(
                    "importe_base_imponible",
                    "No puede cambiarse el total mientras "
                    "la factura tenga un plan de pagos. "
                    "Elimine primero el plan desde el "
                    "detalle de la factura.",
                )

            for field_name in [
                "estado",
                "fecha_autorizacion_gerencia",
                "fecha_pago_segun_contrato",
                "fecha_real_pago",
                "importe_pagado",
            ]:
                cleaned[field_name] = getattr(
                    self.instance,
                    field_name,
                )

            cleaned["factura_pagada"] = (
                (self.instance.estado or "").upper()
                == "PAGADA"
            )

        return cleaned


class FacturaProveedorLineaForm(forms.ModelForm):
    class Meta:
        model = FacturaProveedorLineaGestion
        fields = [
            "linea",
            "articulo_compra",
            "albaran",
            "cod_articulo_legacy",
            "cod_albaran_legacy",
            "linea_albaran_legacy",
            "cantidad",
            "unidad_compra",
            "precio_unitario",
            "importe_linea",
            "importe_descuento",
            "descuento",
            "en_partida",
            "cantidad_en_partidas",
            "en_almacen",
            "observaciones",
        ]
        widgets = {
            "observaciones": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": (
                        "Ej.: 2 UD vivienda 14, "
                        "1 UD vivienda 16 y "
                        "1 UD para almacén."
                    ),
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        team = kwargs.pop("team", None)
        factura = kwargs.pop("factura", None)
        super().__init__(*args, **kwargs)
        # FACTURA_LINEA_ARTICULO_COMPRA_TEAM_SCOPE_V2
        if "articulo_compra" in self.fields:
            try:
                from django.apps import apps as django_apps
                from django.db.models import Q

                ArticuloCompra = django_apps.get_model(
                    "gestion",
                    "ArticuloCompra",
                )

                articulo_qs = (
                    ArticuloCompra.objects
                    .filter(activo=True)
                )

                selected_articulo_id = None

                if self.is_bound:
                    selected_articulo_id = (
                        self.data.get(
                            self.add_prefix(
                                "articulo_compra"
                            )
                        )
                        or self.data.get(
                            "articulo_compra"
                        )
                    )

                if (
                    not selected_articulo_id
                    and getattr(
                        self.instance,
                        "articulo_compra_id",
                        None,
                    )
                ):
                    selected_articulo_id = (
                        self.instance.articulo_compra_id
                    )

                try:
                    selected_articulo_id = (
                        int(selected_articulo_id)
                        if selected_articulo_id
                        else None
                    )
                except (TypeError, ValueError):
                    selected_articulo_id = None

                if team:
                    if selected_articulo_id:
                        articulo_qs = (
                            articulo_qs.filter(
                                Q(team=team)
                                | Q(
                                    id=selected_articulo_id
                                )
                            )
                        )
                    else:
                        articulo_qs = (
                            articulo_qs.filter(
                                team=team
                            )
                        )

                elif selected_articulo_id:
                    articulo_qs = (
                        articulo_qs.filter(
                            id=selected_articulo_id
                        )
                    )

                else:
                    articulo_qs = (
                        ArticuloCompra.objects.none()
                    )

                self.fields[
                    "articulo_compra"
                ].queryset = articulo_qs.order_by(
                    "nombre",
                    "id",
                )

            except Exception:
                self.fields[
                    "articulo_compra"
                ].queryset = self.fields[
                    "articulo_compra"
                ].queryset.none()

            self.fields[
                "articulo_compra"
            ].label = "Artículo / servicio"

            self.fields[
                "articulo_compra"
            ].required = False

            css = self.fields[
                "articulo_compra"
            ].widget.attrs.get("class", "")

            self.fields[
                "articulo_compra"
            ].widget.attrs["class"] = (
                css + " form-select"
            ).strip()

        # FACTURA_LINEA_LABELS_SERVICIO_UI_V1
        if "linea" in self.fields:
            self.fields["linea"].label = "Nº línea"
        if "unidad_compra" in self.fields:
            self.fields["unidad_compra"].label = "Unidad de compra"
            self.fields["unidad_compra"].required = False

            unidades_compra = [
                "",
                "UD",
                "UDS",
                "UNIDADES",
                "SACO",
                "SACOS",
                "CAJA",
                "CAJAS",
                "BOLSA",
                "BOLSAS",
                "PAQUETE",
                "PAQUETES",
                "PALET",
                "PALETS",
                "ROLLO",
                "ROLLOS",
                "BOTE",
                "BOTES",
                "CUBA",
                "CUBAS",
                "KG",
                "TONELADA",
                "TONELADAS",
                "TN",
                "LITRO",
                "LITROS",
                "LTRS",
                "M",
                "ML",
                "M2",
                "M3",
                "HORA",
                "HORAS",
                "DIA",
                "DIAS",
                "MES",
                "MESES",
                "SERVICIO",
                "PORTE",
            ]

            valor_actual = str(
                self.initial.get("unidad_compra")
                or getattr(
                    self.instance,
                    "unidad_compra",
                    "",
                )
                or ""
            ).strip().upper()

            if valor_actual and valor_actual not in unidades_compra:
                unidades_compra.append(valor_actual)

            self.fields["unidad_compra"].widget = forms.Select(
                choices=[
                    (value, value or "Selecciona unidad...")
                    for value in unidades_compra
                ],
                attrs={
                    "class": "form-select",
                },
            )

        if "precio_unitario" in self.fields:
            self.fields["precio_unitario"].label = "Precio unitario"
        if "importe_linea" in self.fields:
            self.fields["importe_linea"].label = "Base línea"
        if "importe_descuento" in self.fields:
            self.fields["importe_descuento"].label = "Descuento adicional"
        if "descuento" in self.fields:
            self.fields["descuento"].label = "Descuento unitario"


        if "observaciones" in self.fields:
            self.fields[
                "observaciones"
            ].label = "Observaciones"

            self.fields[
                "observaciones"
            ].required = False

            self.fields[
                "observaciones"
            ].help_text = (
                "Indica el destino previsto de la línea: "
                "vivienda, partida, almacén o reparto "
                "de cantidades."
            )

        qs = AlbaranProveedorGestion.objects.none()

        if team:
            qs = AlbaranProveedorGestion.objects.filter(team=team).order_by("-fecha_albaran", "-id")

            if factura and factura.proveedor_id:
                qs = qs.filter(proveedor=factura.proveedor)

        self.fields["albaran"].queryset = qs
        self.fields["albaran"].required = False
        self.fields["linea"].required = False
        self.fields["cod_albaran_legacy"].required = False
        self.fields["linea_albaran_legacy"].required = False
        self.fields["cod_articulo_legacy"].required = False

        for name in [
            "cantidad",
            "precio_unitario",
            "importe_linea",
            "importe_descuento",
            "descuento",
            "cantidad_en_partidas",
        ]:
            self.fields[name].required = False

        aplicar_estilo(self)
        _gestion_align_numeric_fields(self)

    def clean(self):
        from decimal import Decimal

        cleaned = super().clean()

        articulo = cleaned.get("articulo_compra")

        unidad_compra = str(
            cleaned.get("unidad_compra") or ""
        ).strip().upper()

        if not unidad_compra and articulo:
            unidad_compra = str(
                getattr(articulo, "unidad", "") or ""
            ).strip().upper()

        cleaned["unidad_compra"] = unidad_compra

        cantidad = cleaned.get("cantidad") or Decimal("0.0000")
        precio = cleaned.get("precio_unitario") or Decimal("0.0000")
        descuento_importe = cleaned.get("importe_descuento") or Decimal("0.00")

        if cleaned.get("importe_linea") is None:
            cleaned["importe_linea"] = (cantidad * precio - descuento_importe).quantize(Decimal("0.01"))

        if cleaned.get("cantidad_en_partidas") is None:
            cleaned["cantidad_en_partidas"] = Decimal("0.0000")

        if cleaned.get("importe_descuento") is None:
            cleaned["importe_descuento"] = Decimal("0.00")

        if cleaned.get("descuento") is None:
            cleaned["descuento"] = Decimal("0.00")

        return cleaned



class AlbaranProveedorLineaForm(forms.ModelForm):
    class Meta:
        model = AlbaranProveedorLineaGestion
        fields = [
            "linea",
            "articulo_compra",
            "cantidad",
            "unidad",
            "precio_unitario",
            "importe_linea",
            "importe_descuento",
            "descuento",
            "facturado",
            "en_pedido",
            "en_partida",
            "cantidad_en_partidas",
            "en_almacen",
            "observaciones",
        ]
        widgets = {
            "observaciones": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        team = kwargs.pop("team", None)
        super().__init__(*args, **kwargs)

        from apps.gestion.models import ArticuloCompra

        self.fields["linea"].required = False

        articulo_qs = ArticuloCompra.objects.filter(activo=True)

        selected_articulo_id = None
        if self.is_bound:
            selected_articulo_id = (
                self.data.get(self.add_prefix("articulo_compra"))
                or self.data.get("articulo_compra")
            )

        if not selected_articulo_id and getattr(self.instance, "articulo_compra_id", None):
            selected_articulo_id = self.instance.articulo_compra_id

        if team:
            if selected_articulo_id:
                try:
                    selected_articulo_id_int = int(selected_articulo_id)
                except Exception:
                    selected_articulo_id_int = None

                if selected_articulo_id_int:
                    articulo_qs = articulo_qs.filter(
                        Q(team=team) | Q(id=selected_articulo_id_int)
                    )
                else:
                    articulo_qs = articulo_qs.filter(team=team)
            else:
                articulo_qs = articulo_qs.filter(team=team)
        else:
            if selected_articulo_id:
                try:
                    articulo_qs = articulo_qs.filter(id=int(selected_articulo_id))
                except Exception:
                    articulo_qs = ArticuloCompra.objects.none()
            else:
                articulo_qs = ArticuloCompra.objects.none()

        articulo_qs = articulo_qs.order_by("nombre", "id")

        self.fields["articulo_compra"].queryset = articulo_qs
        self.fields["articulo_compra"].required = True
        self.fields["articulo_compra"].label = "Artículo / recurso"
        self.fields["articulo_compra"].help_text = "Busca por nombre del artículo o recurso. Ejemplo: CONTENEDOR, ESCOMBROS, PORTE."

        def _label_articulo(obj):
            recurso_id = getattr(obj, "recurso_catalogo_id", None)
            unidad = getattr(obj, "unidad", "") or ""
            extra = []
            if recurso_id:
                extra.append(f"recurso {recurso_id}")
            if unidad:
                extra.append(unidad)
            return f"{obj.nombre} · {' · '.join(extra)}" if extra else obj.nombre

        self.fields["articulo_compra"].label_from_instance = _label_articulo

        self.fields["unidad"].required = False
        self.fields["observaciones"].required = False

        for name in [
            "cantidad",
            "precio_unitario",
            "importe_linea",
            "importe_descuento",
            "descuento",
            "cantidad_en_partidas",
        ]:
            self.fields[name].required = False

        aplicar_estilo(self)

        for _field_name, _default in {
            "descuento": "0",
            "importe_descuento": "0.00",
        }.items():
            if _field_name in self.fields:
                self.fields[_field_name].initial = _default
                current_value = self.initial.get(_field_name)
                if current_value in (None, ""):
                    self.initial[_field_name] = _default
        _gestion_align_numeric_fields(self)

    def clean(self):
        from decimal import Decimal

        cleaned = super().clean()

        cantidad = cleaned.get("cantidad") or Decimal("0.0000")
        precio = cleaned.get("precio_unitario") or Decimal("0.0000")
        descuento_importe = cleaned.get("importe_descuento") or Decimal("0.00")

        if cleaned.get("importe_linea") is None:
            cleaned["importe_linea"] = (cantidad * precio - descuento_importe).quantize(Decimal("0.01"))

        if cleaned.get("importe_descuento") is None:
            cleaned["importe_descuento"] = Decimal("0.00")

        if cleaned.get("descuento") is None:
            cleaned["descuento"] = Decimal("0.00")

        if cleaned.get("cantidad_en_partidas") is None:
            cleaned["cantidad_en_partidas"] = Decimal("0.0000")

        return cleaned


# PATCH_PORTAL_INTASA_ALBARAN_FECHAS_ISO
# Normaliza fechas para inputs HTML type=date en edición de albaranes.
# El navegador necesita value="YYYY-MM-DD"; con "DD/MM/YYYY" deja el campo vacío.
try:
    _portal_intasa_original_albaran_form_init = AlbaranProveedorForm.__init__

    def _portal_intasa_albaran_form_init_fechas_iso(self, *args, **kwargs):
        _portal_intasa_original_albaran_form_init(self, *args, **kwargs)

        date_fields = (
            "fecha_albaran",
            "fecha_entrega_mercaderia",
            "fecha_entrega",
        )

        for field_name in date_fields:
            if field_name not in self.fields:
                continue

            field = self.fields[field_name]

            try:
                field.widget.input_type = "date"
            except Exception:
                pass

            try:
                field.widget.format = "%Y-%m-%d"
            except Exception:
                pass

            try:
                field.input_formats = ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"]
            except Exception:
                pass

            value = self.initial.get(field_name)

            if not value and getattr(self, "instance", None) is not None:
                value = getattr(self.instance, field_name, None)

            if hasattr(value, "strftime"):
                self.initial[field_name] = value.strftime("%Y-%m-%d")

    AlbaranProveedorForm.__init__ = _portal_intasa_albaran_form_init_fechas_iso
except NameError:
    pass



# === FACTURA_LINEA_RECALCULO_V1 ===
def _gestion_decimal_es_to_decimal_v1(value, default="0"):
    from decimal import Decimal, InvalidOperation
    import re

    if value is None:
        return Decimal(default)

    s = str(value).strip()
    if not s:
        return Decimal(default)

    s = (
        s.replace("€", "")
         .replace("EUR", "")
         .replace("\u00a0", "")
         .replace(" ", "")
         .replace("'", "")
    )

    s = re.sub(r"[^0-9,.\-]", "", s)

    if not s or s in {"-", ".", ","}:
        return Decimal(default)

    negative = s.startswith("-")
    if negative:
        s = s[1:]

    if "." in s and "," in s:
        if s.rfind(",") > s.rfind("."):
            # Español: 17.475,62
            s = s.replace(".", "").replace(",", ".")
        else:
            # Anglosajón/técnico: 17,475.62
            s = s.replace(",", "")
    elif "," in s:
        # Español sin miles: 17475,62
        s = s.replace(".", "").replace(",", ".")
    elif "." in s:
        parts = s.split(".")
        # Miles sin decimales: 17.475
        if len(parts) > 1 and all(len(p) == 3 for p in parts[1:]) and len(parts[0]) <= 3:
            s = "".join(parts)

    if negative:
        s = "-" + s

    try:
        return Decimal(s)
    except InvalidOperation:
        return Decimal(default)


def _gestion_factura_linea_calc_importe_v1(cantidad, precio_unitario, importe_descuento=None):
    from decimal import Decimal, ROUND_HALF_UP

    q2 = Decimal("0.01")

    cantidad_d = _gestion_decimal_es_to_decimal_v1(cantidad)
    precio_d = _gestion_decimal_es_to_decimal_v1(precio_unitario)
    descuento_d = _gestion_decimal_es_to_decimal_v1(importe_descuento)

    importe = (cantidad_d * precio_d) - descuento_d
    return importe.quantize(q2, rounding=ROUND_HALF_UP)


if "_FacturaProveedorLineaFormBaseRecalculoV1" not in globals():
    _FacturaProveedorLineaFormBaseRecalculoV1 = FacturaProveedorLineaForm

    class FacturaProveedorLineaForm(_FacturaProveedorLineaFormBaseRecalculoV1):
        def clean(self):
            cleaned = super().clean()

            cantidad = cleaned.get("cantidad")
            precio_unitario = cleaned.get("precio_unitario")
            importe_descuento = cleaned.get("importe_descuento")

            # Siempre que haya cantidad y precio, el importe debe ser coherente.
            # Esto permite líneas negativas: -1 × 17475.62 = -17475.62
            if cantidad is not None and precio_unitario is not None:
                cleaned["importe_linea"] = _gestion_factura_linea_calc_importe_v1(
                    cantidad,
                    precio_unitario,
                    importe_descuento,
                )

            return cleaned



# === FACTURA_LINEA_FORMULA_DESCUENTO_IVA_V2 ===
from django import forms as _gestion_django_forms_v2

def _gestion_decimal_es_v2(value, default="0"):
    from decimal import Decimal, InvalidOperation
    import re

    if value is None:
        return Decimal(default)

    s = str(value).strip()
    if not s:
        return Decimal(default)

    s = (
        s.replace("€", "")
         .replace("EUR", "")
         .replace("\u00a0", "")
         .replace(" ", "")
         .replace("'", "")
    )

    s = re.sub(r"[^0-9,.\-]", "", s)

    if not s or s in {"-", ".", ","}:
        return Decimal(default)

    negative = s.startswith("-")
    if negative:
        s = s[1:]

    if "." in s and "," in s:
        if s.rfind(",") > s.rfind("."):
            # Español: 17.475,62
            s = s.replace(".", "").replace(",", ".")
        else:
            # Técnico/anglosajón: 17,475.62
            s = s.replace(",", "")
    elif "," in s:
        # Español: 17475,62
        s = s.replace(".", "").replace(",", ".")
    elif "." in s:
        parts = s.split(".")
        if len(parts) > 1 and all(len(p) == 3 for p in parts[1:]) and len(parts[0]) <= 3:
            s = "".join(parts)

    if negative:
        s = "-" + s

    try:
        return Decimal(s)
    except InvalidOperation:
        return Decimal(default)


def _gestion_factura_linea_calc_importes_v2(
    cantidad,
    precio_unitario,
    descuento_unitario=None,
    importe_descuento=None,
    iva_porcentaje=None,
):
    from decimal import Decimal, ROUND_HALF_UP

    q2 = Decimal("0.01")

    cantidad_d = _gestion_decimal_es_v2(cantidad)
    precio_d = _gestion_decimal_es_v2(precio_unitario)
    dto_unit_d = _gestion_decimal_es_v2(descuento_unitario)
    dto_total_d = _gestion_decimal_es_v2(importe_descuento)
    iva_pct_d = _gestion_decimal_es_v2(iva_porcentaje, default="21.00")

    base = (cantidad_d * (precio_d - dto_unit_d)) - dto_total_d
    base = base.quantize(q2, rounding=ROUND_HALF_UP)

    iva_importe = (base * iva_pct_d / Decimal("100")).quantize(q2, rounding=ROUND_HALF_UP)
    total_con_iva = (base + iva_importe).quantize(q2, rounding=ROUND_HALF_UP)

    return {
        "base": base,
        "iva_porcentaje": iva_pct_d.quantize(q2, rounding=ROUND_HALF_UP),
        "iva_importe": iva_importe,
        "total_con_iva": total_con_iva,
    }


if "_FacturaProveedorLineaFormBaseFormulaDescuentoIvaV2" not in globals():
    _FacturaProveedorLineaFormBaseFormulaDescuentoIvaV2 = FacturaProveedorLineaForm

    class FacturaProveedorLineaForm(_FacturaProveedorLineaFormBaseFormulaDescuentoIvaV2):
        iva_porcentaje = _gestion_django_forms_v2.DecimalField(
            label="IVA %",
            required=False,
            max_digits=6,
            decimal_places=2,
            initial="21.00",
            help_text="Porcentaje de IVA de la línea. Se guarda en trazabilidad de línea.",
        )

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

            self.fields["precio_unitario"].label = "Precio unitario bruto"
            self.fields["descuento"].label = "Descuento unitario"
            self.fields["importe_descuento"].label = "Importe descuento adicional"
            self.fields["importe_linea"].label = "Base línea"

            raw = getattr(self.instance, "raw_data", None)
            if isinstance(raw, dict):
                iva = (
                    raw.get("iva_porcentaje")
                    or raw.get("porcentaje_iva")
                    or raw.get("iva_pct")
                    or raw.get("tasa_iva")
                    or raw.get("tasa")
                )
                if iva not in (None, ""):
                    self.fields["iva_porcentaje"].initial = iva

            # Si el importador guardó total con IVA, lo dejamos como ayuda visual.
            if isinstance(raw, dict):
                total_con_iva = (
                    raw.get("importe_total_con_iva")
                    or raw.get("total_con_iva")
                    or raw.get("importe_tti")
                    or raw.get("total_tti")
                )
                if total_con_iva not in (None, ""):
                    self.fields["iva_porcentaje"].help_text = (
                        f"Total con IVA importado: {total_con_iva}. "
                        "Al guardar se recalcula desde base e IVA."
                    )

        def clean(self):
            cleaned = super().clean()

            cantidad = cleaned.get("cantidad")
            precio_unitario = cleaned.get("precio_unitario")
            descuento_unitario = cleaned.get("descuento")
            importe_descuento = cleaned.get("importe_descuento")
            iva_porcentaje = cleaned.get("iva_porcentaje")

            if cantidad is not None and precio_unitario is not None:
                calc = _gestion_factura_linea_calc_importes_v2(
                    cantidad,
                    precio_unitario,
                    descuento_unitario,
                    importe_descuento,
                    iva_porcentaje,
                )
                cleaned["importe_linea"] = calc["base"]
                cleaned["_calc_importes_v2"] = calc

            return cleaned

        def save(self, commit=True):
            obj = super().save(commit=False)

            calc = self.cleaned_data.get("_calc_importes_v2") or _gestion_factura_linea_calc_importes_v2(
                self.cleaned_data.get("cantidad"),
                self.cleaned_data.get("precio_unitario"),
                self.cleaned_data.get("descuento"),
                self.cleaned_data.get("importe_descuento"),
                self.cleaned_data.get("iva_porcentaje"),
            )

            raw = getattr(obj, "raw_data", None)
            if not isinstance(raw, dict):
                raw = {}

            raw["formula_descuento_iva_v2"] = {
                "formula": "base = cantidad * (precio_unitario - descuento_unitario) - importe_descuento",
                "cantidad": str(self.cleaned_data.get("cantidad")),
                "precio_unitario": str(self.cleaned_data.get("precio_unitario")),
                "descuento_unitario": str(self.cleaned_data.get("descuento")),
                "importe_descuento": str(self.cleaned_data.get("importe_descuento")),
                "iva_porcentaje": str(calc["iva_porcentaje"]),
                "base": str(calc["base"]),
                "iva_importe": str(calc["iva_importe"]),
                "total_con_iva": str(calc["total_con_iva"]),
            }

            raw["iva_porcentaje"] = str(calc["iva_porcentaje"])
            raw["importe_iva_linea"] = str(calc["iva_importe"])
            raw["importe_total_con_iva"] = str(calc["total_con_iva"])
            raw["total_con_iva"] = str(calc["total_con_iva"])

            obj.raw_data = raw
            obj.importe_linea = calc["base"]

            if commit:
                obj.save()

            return obj



# GESTION_FORMULARIOS_AMBITO_RUNTIME_PATCH_V3
# Defensa final: garantiza que ambito_gestion exista en los ModelForm aunque haya parches previos.
def _gestion_insert_after_proveedor_ordered_v3(fields_dict, field_name):
    try:
        from collections import OrderedDict
        if field_name not in fields_dict:
            return fields_dict
        ordered = OrderedDict()
        inserted = False
        for key, value in fields_dict.items():
            ordered[key] = value
            if key == "proveedor" and field_name != "proveedor":
                ordered[field_name] = fields_dict[field_name]
                inserted = True
        if not inserted and field_name in fields_dict:
            ordered[field_name] = fields_dict[field_name]
        # quitar duplicado conservando orden final
        final = OrderedDict()
        for key, value in ordered.items():
            final[key] = value
        return final
    except Exception:
        return fields_dict


def _gestion_ensure_ambito_model_form_v3(FormClass, ModelClass):
    try:
        fields = list(getattr(FormClass._meta, "fields", []) or [])
        if "ambito_gestion" not in fields:
            if "proveedor" in fields:
                fields.insert(fields.index("proveedor") + 1, "ambito_gestion")
            else:
                fields.append("ambito_gestion")
            FormClass._meta.fields = fields

        model_field = ModelClass._meta.get_field("ambito_gestion")
        form_field = model_field.formfield()
        form_field.label = "Ámbito"
        form_field.required = True
        form_field.help_text = "El centro de coste se asignará automáticamente."
        form_field.initial = "OBRA"
        try:
            form_field.widget.attrs.update({"class": "form-select form-select-sm"})
        except Exception:
            pass

        FormClass.base_fields["ambito_gestion"] = form_field
        FormClass.base_fields = _gestion_insert_after_proveedor_ordered_v3(FormClass.base_fields, "ambito_gestion")
    except Exception:
        pass


def _gestion_config_ambito_instance_v3(form):
    try:
        field = form.fields.get("ambito_gestion")
        if not field:
            return
        field.label = "Ámbito"
        field.required = True
        field.help_text = "El centro de coste se asignará automáticamente."
        if not getattr(form.instance, "pk", None) and not form.data.get("ambito_gestion"):
            field.initial = "OBRA"
        try:
            field.widget.attrs.update({"class": "form-select form-select-sm"})
        except Exception:
            pass
    except Exception:
        pass


try:
    _gestion_ensure_ambito_model_form_v3(AlbaranProveedorForm, AlbaranProveedorGestion)
    _gestion_ensure_ambito_model_form_v3(FacturaProveedorForm, FacturaProveedorGestion)

    if not getattr(AlbaranProveedorForm, "_gestion_ambito_runtime_patch_v3", False):
        _albaran_init_v3 = AlbaranProveedorForm.__init__
        def _albaran_init_ambito_v3(self, *args, **kwargs):
            _albaran_init_v3(self, *args, **kwargs)
            _gestion_config_ambito_instance_v3(self)
        AlbaranProveedorForm.__init__ = _albaran_init_ambito_v3
        AlbaranProveedorForm._gestion_ambito_runtime_patch_v3 = True

    if not getattr(FacturaProveedorForm, "_gestion_ambito_runtime_patch_v3", False):
        _factura_init_v3 = FacturaProveedorForm.__init__
        def _factura_init_ambito_v3(self, *args, **kwargs):
            _factura_init_v3(self, *args, **kwargs)
            _gestion_config_ambito_instance_v3(self)
        FacturaProveedorForm.__init__ = _factura_init_ambito_v3
        FacturaProveedorForm._gestion_ambito_runtime_patch_v3 = True
except Exception:
    pass


# GESTION_PROVEEDOR_FILTRADO_POR_AMBITO_V1
def _gestion_reorder_ambito_before_proveedor_v1(fields_dict):
    try:
        from collections import OrderedDict
        final = OrderedDict()
        if "ambito_gestion" in fields_dict:
            final["ambito_gestion"] = fields_dict["ambito_gestion"]
        if "proveedor" in fields_dict:
            final["proveedor"] = fields_dict["proveedor"]
        for key, value in fields_dict.items():
            if key not in final:
                final[key] = value
        return final
    except Exception:
        return fields_dict


def _gestion_ambito_choices_v1():
    return [
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


def _gestion_selected_ambito_form_v1(form, ambito_param=None):
    value = (
        getattr(form, "data", {}).get("ambito_gestion")
        or ambito_param
        or getattr(getattr(form, "instance", None), "ambito_gestion", None)
        or "OBRA"
    )
    value = str(value or "OBRA").strip()
    if not value or value == "SIN_CLASIFICAR":
        value = "OBRA"
    return value


def _gestion_configurar_ambito_y_proveedor_v1(form, team=None, ambito_param=None):
    try:
        selected = _gestion_selected_ambito_form_v1(form, ambito_param)

        if "ambito_gestion" in form.fields:
            form.fields["ambito_gestion"].label = "Ámbito"
            form.fields["ambito_gestion"].required = True
            form.fields["ambito_gestion"].choices = _gestion_ambito_choices_v1()
            form.fields["ambito_gestion"].initial = selected
            form.fields["ambito_gestion"].help_text = "Selecciona el ámbito antes del proveedor."
            form.fields["ambito_gestion"].widget.attrs.update({"class": "form-select form-select-sm"})

        if "proveedor" in form.fields:
            from django.db.models import Q
            team = team or getattr(form, "team", None) or getattr(getattr(form, "instance", None), "team", None)
            qs = Proveedor.objects.none()
            if team:
                qs = Proveedor.objects.filter(team=team, activo=True)
                if any(f.name == "ambito_gestion" for f in Proveedor._meta.fields):
                    qs = qs.filter(ambito_gestion=selected)

                proveedor_id = (
                    getattr(form, "data", {}).get("proveedor")
                    or getattr(getattr(form, "instance", None), "proveedor_id", None)
                )
                if proveedor_id:
                    try:
                        proveedor_id = int(proveedor_id)
                        qs = Proveedor.objects.filter(
                            Q(id__in=list(qs.values_list("id", flat=True))) | Q(id=proveedor_id),
                            team=team,
                            activo=True,
                        )
                    except Exception:
                        pass

            form.fields["proveedor"].queryset = qs.order_by("nombre_comercial", "nombre_fiscal")
            form.fields["proveedor"].label = "Proveedor"
            form.fields["proveedor"].help_text = "La lista se filtra por empresa y ámbito."

        form.fields = _gestion_reorder_ambito_before_proveedor_v1(form.fields)
    except Exception:
        pass


try:
    for _FormClass in [AlbaranProveedorForm, FacturaProveedorForm]:
        if "ambito_gestion" in getattr(_FormClass._meta, "fields", []):
            fields = list(_FormClass._meta.fields)
            fields = [f for f in fields if f not in ("ambito_gestion", "proveedor")]
            _FormClass._meta.fields = ["ambito_gestion", "proveedor"] + fields
            _FormClass.base_fields = _gestion_reorder_ambito_before_proveedor_v1(_FormClass.base_fields)

    if not getattr(AlbaranProveedorForm, "_gestion_proveedor_filtrado_ambito_v1", False):
        _old_albaran_init_ambito_v1 = AlbaranProveedorForm.__init__
        def _new_albaran_init_ambito_v1(self, *args, **kwargs):
            ambito_param = kwargs.pop("ambito_gestion", None)
            team_param = kwargs.get("team")
            _old_albaran_init_ambito_v1(self, *args, **kwargs)
            _gestion_configurar_ambito_y_proveedor_v1(self, team=team_param, ambito_param=ambito_param)
        AlbaranProveedorForm.__init__ = _new_albaran_init_ambito_v1
        AlbaranProveedorForm._gestion_proveedor_filtrado_ambito_v1 = True

    if not getattr(FacturaProveedorForm, "_gestion_proveedor_filtrado_ambito_v1", False):
        _old_factura_init_ambito_v1 = FacturaProveedorForm.__init__
        def _new_factura_init_ambito_v1(self, *args, **kwargs):
            ambito_param = kwargs.pop("ambito_gestion", None)
            team_param = kwargs.get("team")
            _old_factura_init_ambito_v1(self, *args, **kwargs)
            _gestion_configurar_ambito_y_proveedor_v1(self, team=team_param, ambito_param=ambito_param)
        FacturaProveedorForm.__init__ = _new_factura_init_ambito_v1
        FacturaProveedorForm._gestion_proveedor_filtrado_ambito_v1 = True
except Exception:
    pass


# GESTION_PROVEEDOR_FORM_AMBITO_V1
# El proveedor también debe tener ámbito operativo para filtrar altas/OCR.
def _gestion_proveedor_ambito_choices_v1():
    return [
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


def _gestion_reorder_proveedor_form_ambito_v1(fields_dict):
    try:
        from collections import OrderedDict
        final = OrderedDict()

        # Orden operativo del alta de proveedor: ámbito primero.
        if "ambito_gestion" in fields_dict:
            final["ambito_gestion"] = fields_dict["ambito_gestion"]

        for key, value in fields_dict.items():
            if key not in final:
                final[key] = value

        return final
    except Exception:
        return fields_dict


def _gestion_ensure_proveedor_form_ambito_v1(FormClass):
    try:
        from django import forms as _forms

        # Garantizar que ModelForm guarde el campo.
        fields = getattr(FormClass._meta, "fields", None)

        if fields and fields != "__all__":
            fields = list(fields)
            if "ambito_gestion" not in fields:
                fields.insert(0, "ambito_gestion")
            FormClass._meta.fields = fields

        exclude = getattr(FormClass._meta, "exclude", None)
        if exclude:
            exclude = [x for x in list(exclude) if x != "ambito_gestion"]
            FormClass._meta.exclude = exclude

        field = _forms.ChoiceField(
            label="Ámbito",
            choices=_gestion_proveedor_ambito_choices_v1(),
            required=True,
            initial="OBRA",
            help_text="Ámbito operativo principal del proveedor.",
        )
        field.widget.attrs.update({"class": "form-select form-select-sm"})

        FormClass.base_fields["ambito_gestion"] = field
        FormClass.base_fields = _gestion_reorder_proveedor_form_ambito_v1(FormClass.base_fields)

    except Exception:
        pass


def _gestion_config_proveedor_form_ambito_v1(form):
    try:
        from django import forms as _forms

        if "ambito_gestion" not in form.fields:
            form.fields["ambito_gestion"] = _forms.ChoiceField(
                label="Ámbito",
                choices=_gestion_proveedor_ambito_choices_v1(),
                required=True,
                initial="OBRA",
                help_text="Ámbito operativo principal del proveedor.",
            )

        field = form.fields["ambito_gestion"]
        field.label = "Ámbito"
        field.required = True
        field.choices = _gestion_proveedor_ambito_choices_v1()
        field.initial = (
            getattr(form, "data", {}).get("ambito_gestion")
            or getattr(getattr(form, "instance", None), "ambito_gestion", None)
            or "OBRA"
        )
        field.help_text = "Ámbito operativo principal del proveedor."
        field.widget.attrs.update({"class": "form-select form-select-sm"})

        form.fields = _gestion_reorder_proveedor_form_ambito_v1(form.fields)

    except Exception:
        pass


try:
    _gestion_ensure_proveedor_form_ambito_v1(ProveedorForm)

    if not getattr(ProveedorForm, "_gestion_proveedor_form_ambito_v1", False):
        _old_proveedor_init_v1 = ProveedorForm.__init__

        def _new_proveedor_init_v1(self, *args, **kwargs):
            _old_proveedor_init_v1(self, *args, **kwargs)
            _gestion_config_proveedor_form_ambito_v1(self)

        ProveedorForm.__init__ = _new_proveedor_init_v1
        ProveedorForm._gestion_proveedor_form_ambito_v1 = True

except Exception:
    pass


# GESTION_FORM_PROVEEDOR_GRUPO_SCOPE_V1
# Factura/Albarán: el proveedor se selecciona por ámbito y grupo, no por empresa exclusiva.
def _gestion_form_proveedor_key_v1(p):
    import re
    cif = re.sub(r"[^A-Z0-9]", "", (getattr(p, "cif", "") or "").upper())
    if cif:
        return ("CIF", cif)
    nombre = re.sub(
        r"[^A-Z0-9]",
        "",
        ((getattr(p, "nombre_comercial", "") or getattr(p, "nombre_fiscal", "") or "").upper()),
    )
    return ("NOMBRE", nombre or str(getattr(p, "id", "")))


def _gestion_form_proveedor_canon_ids_v1(qs, preferred_team_id=None):
    grupos = {}
    for p in qs.select_related("team").order_by("nombre_comercial", "nombre_fiscal", "team_id", "id"):
        grupos.setdefault(_gestion_form_proveedor_key_v1(p), []).append(p)

    ids = []
    for _key, items in grupos.items():
        def score(p):
            preferred = 0 if preferred_team_id and p.team_id == preferred_team_id else 1
            return (preferred, p.team_id or 999999, p.id)
        ids.append(sorted(items, key=score)[0].id)
    return ids


def _gestion_configurar_ambito_y_proveedor_grupo_scope_v1(form, team=None, team_scope=None, ambito_param=None):
    try:
        selected = _gestion_selected_ambito_form_v1(form, ambito_param)

        if "ambito_gestion" in form.fields:
            form.fields["ambito_gestion"].label = "Ámbito"
            form.fields["ambito_gestion"].required = True
            form.fields["ambito_gestion"].choices = _gestion_ambito_choices_v1()
            form.fields["ambito_gestion"].initial = selected
            form.fields["ambito_gestion"].help_text = "Selecciona el ámbito antes del proveedor."
            form.fields["ambito_gestion"].widget.attrs.update({"class": "form-select form-select-sm"})

        if "proveedor" in form.fields:
            from django.db.models import Q

            scope_ids = []
            if team_scope is not None:
                if hasattr(team_scope, "values_list"):
                    scope_ids = list(team_scope.values_list("id", flat=True))
                else:
                    scope_ids = [getattr(t, "id", t) for t in team_scope]
            elif team is not None:
                scope_ids = [getattr(team, "id", team)]

            qs = Proveedor.objects.none()
            if scope_ids:
                qs = Proveedor.objects.filter(team_id__in=scope_ids, activo=True)
                if any(f.name == "ambito_gestion" for f in Proveedor._meta.fields):
                    qs = qs.filter(ambito_gestion=selected)

                ids = _gestion_form_proveedor_canon_ids_v1(qs, preferred_team_id=getattr(team, "id", None))
                qs = Proveedor.objects.filter(id__in=ids, activo=True)

                proveedor_id = (
                    getattr(form, "data", {}).get("proveedor")
                    or getattr(getattr(form, "instance", None), "proveedor_id", None)
                )
                if proveedor_id:
                    try:
                        proveedor_id = int(proveedor_id)
                        qs = Proveedor.objects.filter(
                            Q(id__in=list(qs.values_list("id", flat=True))) | Q(id=proveedor_id),
                            activo=True,
                        )
                    except Exception:
                        pass

            form.fields["proveedor"].queryset = qs.order_by("nombre_comercial", "nombre_fiscal")
            form.fields["proveedor"].label = "Proveedor"
            form.fields["proveedor"].help_text = "La lista se filtra por ámbito y grupo."

        form.fields = _gestion_reorder_ambito_before_proveedor_v1(form.fields)
    except Exception:
        pass


try:
    if not getattr(AlbaranProveedorForm, "_gestion_form_proveedor_grupo_scope_v1", False):
        _old_albaran_init_grupo_v1 = AlbaranProveedorForm.__init__
        def _new_albaran_init_grupo_v1(self, *args, **kwargs):
            team_scope_param = kwargs.pop("team_scope", None)
            ambito_param = kwargs.get("ambito_gestion", None)
            team_param = kwargs.get("team", None)
            _old_albaran_init_grupo_v1(self, *args, **kwargs)
            _gestion_configurar_ambito_y_proveedor_grupo_scope_v1(
                self,
                team=team_param,
                team_scope=team_scope_param,
                ambito_param=ambito_param,
            )
        AlbaranProveedorForm.__init__ = _new_albaran_init_grupo_v1
        AlbaranProveedorForm._gestion_form_proveedor_grupo_scope_v1 = True

    if not getattr(FacturaProveedorForm, "_gestion_form_proveedor_grupo_scope_v1", False):
        _old_factura_init_grupo_v1 = FacturaProveedorForm.__init__
        def _new_factura_init_grupo_v1(self, *args, **kwargs):
            team_scope_param = kwargs.pop("team_scope", None)
            ambito_param = kwargs.get("ambito_gestion", None)
            team_param = kwargs.get("team", None)
            _old_factura_init_grupo_v1(self, *args, **kwargs)
            _gestion_configurar_ambito_y_proveedor_grupo_scope_v1(
                self,
                team=team_param,
                team_scope=team_scope_param,
                ambito_param=ambito_param,
            )
        FacturaProveedorForm.__init__ = _new_factura_init_grupo_v1
        FacturaProveedorForm._gestion_form_proveedor_grupo_scope_v1 = True
except Exception:
    pass


# GESTION_FACTURA_CABECERA_OBLIGATORIA_V1
# Refuerzo defensivo: ninguna factura de gestión debe guardarse desde formulario
# sin cabecera mínima. Esto evita facturas sin fecha/proveedor/número/empresa/ámbito.
def _gestion_patch_factura_cabecera_obligatoria_v1():
    try:
        from django import forms as _dj_forms
        from django.forms import ModelForm as _ModelForm
        import inspect as _inspect
        import sys as _sys

        _mod = _sys.modules[__name__]

        # Campos equivalentes posibles según el modelo/formulario real.
        _required_candidates = (
            "team",                  # Empresa
            "empresa",               # Empresa, si algún form usa alias
            "ambito_gestion",         # Ámbito
            "ambito",                # Ámbito, si algún form usa alias
            "proveedor",             # Proveedor
            "num_factura_proveedor", # Nº factura proveedor
            "fecha_emision",         # Fecha emisión
        )

        def _is_empty(value):
            return value is None or value == "" or value == []

        for _name, _cls in list(_inspect.getmembers(_mod)):
            if not (_inspect.isclass(_cls) and issubclass(_cls, _ModelForm) and _cls is not _ModelForm):
                continue

            _meta = getattr(_cls, "Meta", None)
            _model = getattr(_meta, "model", None)
            if not _model or "Factura" not in getattr(_model, "__name__", ""):
                continue

            _base_fields = getattr(_cls, "base_fields", {})
            _target_fields = [f for f in _required_candidates if f in _base_fields]

            # Solo actuar sobre formularios reales de factura con los campos críticos.
            if not ("proveedor" in _target_fields and "fecha_emision" in _target_fields):
                continue

            if getattr(_cls, "_gestion_cabecera_obligatoria_v1", False):
                continue

            _orig_init = _cls.__init__
            _orig_clean = getattr(_cls, "clean", None)

            def _make_init(orig_init, target_fields):
                def __init__(self, *args, **kwargs):
                    orig_init(self, *args, **kwargs)
                    for fname in target_fields:
                        field = self.fields.get(fname)
                        if not field:
                            continue
                        field.required = True
                        field.widget.attrs["required"] = "required"
                return __init__

            def _make_clean(orig_clean, target_fields):
                def clean(self):
                    cleaned = orig_clean(self) if orig_clean else super(type(self), self).clean()
                    for fname in target_fields:
                        if fname not in self.fields:
                            continue
                        if _is_empty(cleaned.get(fname)):
                            self.add_error(fname, _dj_forms.ValidationError("Campo obligatorio para guardar la factura."))
                    return cleaned
                return clean

            _cls.__init__ = _make_init(_orig_init, tuple(_target_fields))
            _cls.clean = _make_clean(_orig_clean, tuple(_target_fields))
            _cls._gestion_cabecera_obligatoria_v1 = True

    except Exception:
        # No romper importación del módulo forms; los errores reales se verán en manage.py check.
        pass

_gestion_patch_factura_cabecera_obligatoria_v1()



# GESTION_AMBITO_NO_OBRA_SAVE_V1
# Refuerzo defensivo: en facturas/albaranes, el ámbito posteado por el usuario
# prevalece sobre initial/instance/default OBRA.
def _gestion_ambito_no_obra_validos_v1(form=None):
    valid = set()
    try:
        for value, label in _gestion_ambito_choices_v1():
            valid.add(str(value))
    except Exception:
        pass

    try:
        model = getattr(getattr(form, "Meta", None), "model", None) or getattr(getattr(form, "_meta", None), "model", None)
        if model:
            field = model._meta.get_field("ambito_gestion")
            for value, label in getattr(field, "choices", []) or []:
                valid.add(str(value))
    except Exception:
        pass

    if not valid:
        valid = {
            "SIN_CLASIFICAR",
            "OBRA",
            "ADMINISTRACION",
            "COMERCIAL",
            "GERENCIA",
            "INFORMATICA",
            "VEHICULOS",
            "ALQUILERES",
            "SERVICIOS_GENERALES",
            "OTROS",
        }

    return valid


try:
    _gestion_selected_ambito_form_v1_original = _gestion_selected_ambito_form_v1
except Exception:
    _gestion_selected_ambito_form_v1_original = None


def _gestion_selected_ambito_form_v1(form, ambito_param=None):
    valid = _gestion_ambito_no_obra_validos_v1(form)

    # 1) En formulario bound, manda siempre el POST.
    try:
        data = getattr(form, "data", None)
        if data:
            for key in ("ambito_gestion", "ambito"):
                value = data.get(key)
                value = str(value or "").strip()
                if value in valid:
                    return value
    except Exception:
        pass

    # 2) Luego parámetro explícito desde GET/vista.
    try:
        value = str(ambito_param or "").strip()
        if value in valid:
            return value
    except Exception:
        pass

    # 3) Luego instancia existente.
    try:
        value = str(getattr(getattr(form, "instance", None), "ambito_gestion", "") or "").strip()
        if value in valid:
            return value
    except Exception:
        pass

    # 4) Compatibilidad con función anterior.
    try:
        if _gestion_selected_ambito_form_v1_original:
            value = str(_gestion_selected_ambito_form_v1_original(form, ambito_param) or "").strip()
            if value in valid:
                return value
    except Exception:
        pass

    return "OBRA"


def _gestion_ambito_posted_para_guardar_v1(form):
    valid = _gestion_ambito_no_obra_validos_v1(form)

    try:
        cleaned = getattr(form, "cleaned_data", {}) or {}
        for key in ("ambito_gestion", "ambito"):
            value = str(cleaned.get(key) or "").strip()
            if value in valid:
                return value
    except Exception:
        pass

    try:
        data = getattr(form, "data", None)
        if data:
            for key in ("ambito_gestion", "ambito"):
                value = str(data.get(key) or "").strip()
                if value in valid:
                    return value
    except Exception:
        pass

    return None


def _gestion_aplicar_ambito_posted_a_instancia_v1(form, obj):
    value = _gestion_ambito_posted_para_guardar_v1(form)
    if not value or not hasattr(obj, "ambito_gestion"):
        return obj

    obj.ambito_gestion = value

    # Si no es obra, no debe quedar arrastrada una obra vinculada.
    if value != "OBRA":
        if hasattr(obj, "obra_planificacion"):
            obj.obra_planificacion = None

        # Intentar asignar centro de coste correspondiente al ámbito.
        try:
            from apps.gestion.models import CentroCosteGestion
            team = getattr(obj, "team", None)
            if team and hasattr(obj, "centro_coste"):
                centro = (
                    CentroCosteGestion.objects
                    .filter(team=team, codigo=value, activo=True)
                    .first()
                    or CentroCosteGestion.objects
                    .filter(team=team, tipo=value, activo=True)
                    .order_by("codigo")
                    .first()
                )
                if centro:
                    obj.centro_coste = centro
        except Exception:
            pass

    return obj


def _gestion_patch_save_ambito_no_obra_v1():
    for cls_name in ("FacturaProveedorForm", "AlbaranProveedorForm"):
        cls = globals().get(cls_name)
        if cls is None or getattr(cls, "_gestion_ambito_no_obra_save_v1", False):
            continue

        old_save = cls.save

        def make_save(_old_save):
            def save(self, commit=True):
                obj = _old_save(self, commit=False)
                obj = _gestion_aplicar_ambito_posted_a_instancia_v1(self, obj)

                if commit:
                    obj.save()
                    if hasattr(self, "save_m2m"):
                        self.save_m2m()

                return obj
            return save

        cls.save = make_save(old_save)
        cls._gestion_ambito_no_obra_save_v1 = True


try:
    _gestion_patch_save_ambito_no_obra_v1()
except Exception:
    pass

# =============================================================================
# GESTION_CATALOGO_PROVEEDORES_GLOBAL_FORMS_V2
# Catálogo compartido de proveedores.
# La empresa del documento no restringe el proveedor seleccionable.
# =============================================================================
def _gestion_form_global_norm_cif_v2(value):
    import re

    value = re.sub(
        r"[^A-Z0-9]",
        "",
        str(value or "").strip().upper(),
    )

    if len(value) < 8:
        return ""

    digits = "".join(ch for ch in value if ch.isdigit())

    if digits and len(set(digits)) == 1:
        return ""

    return value


def _gestion_form_global_provider_key_v2(proveedor):
    try:
        legacy = int(
            getattr(proveedor, "legacy_id_proveedor", None) or 0
        )
    except (TypeError, ValueError):
        legacy = 0

    if legacy > 0:
        return ("LEGACY", legacy)

    cif = _gestion_form_global_norm_cif_v2(
        getattr(proveedor, "cif", "")
    )

    if cif:
        return ("CIF", cif)

    return ("ID", proveedor.pk)


def _gestion_form_global_canonical_ids_v2(queryset):
    proveedores = list(
        queryset
        .select_related("team")
        .order_by("id")
    )

    canonicos = {}

    for proveedor in proveedores:
        key = _gestion_form_global_provider_key_v2(proveedor)

        # El queryset viene ordenado por ID.
        # Se conserva de forma determinista el primer registro activo/visible.
        if key not in canonicos:
            canonicos[key] = proveedor

    return [
        proveedor.pk
        for proveedor in canonicos.values()
    ]


def _gestion_configurar_ambito_y_proveedor_grupo_scope_v1(
    form,
    team=None,
    team_scope=None,
    ambito_param=None,
):
    try:
        from django.apps import apps
        from django.db.models import Q

        ProveedorGlobal = apps.get_model("gestion", "Proveedor")

        selected = _gestion_selected_ambito_form_v1(
            form,
            ambito_param,
        )

        if "ambito_gestion" in form.fields:
            field = form.fields["ambito_gestion"]
            field.label = "Ámbito"
            field.required = True
            field.choices = _gestion_ambito_choices_v1()
            field.initial = selected
            field.help_text = "Selecciona el ámbito antes del proveedor."
            field.widget.attrs.update({
                "class": "form-select form-select-sm",
            })

        if "proveedor" in form.fields:
            base_qs = ProveedorGlobal.objects.filter(
                activo=True,
                fuera_listado=False,
            )

            if any(
                model_field.name == "ambito_gestion"
                for model_field in ProveedorGlobal._meta.fields
            ):
                base_qs = base_qs.filter(
                    ambito_gestion=selected,
                )

            ids_canonicos = (
                _gestion_form_global_canonical_ids_v2(base_qs)
            )

            current_provider_id = (
                getattr(form, "data", {}).get("proveedor")
                or getattr(
                    getattr(form, "instance", None),
                    "proveedor_id",
                    None,
                )
            )

            filtro = Q(id__in=ids_canonicos)

            # En edición se mantiene visible el proveedor histórico,
            # aunque posteriormente haya quedado inactivo.
            if current_provider_id:
                try:
                    filtro |= Q(id=int(current_provider_id))
                except (TypeError, ValueError):
                    pass

            final_qs = (
                ProveedorGlobal.objects
                .filter(filtro)
                .select_related("team")
                .order_by(
                    "nombre_comercial",
                    "nombre_fiscal",
                    "id",
                )
            )

            field = form.fields["proveedor"]
            field.queryset = final_qs
            field.label = "Proveedor"
            field.help_text = (
                "Catálogo global compartido por todos los usuarios."
            )

        form.fields = (
            _gestion_reorder_ambito_before_proveedor_v1(
                form.fields
            )
        )

    except Exception:
        # Compatibilidad defensiva con wrappers históricos.
        pass



# FACTURA_PLAN_CANONICO_FORM_V1B
_factura_plan_canonico_original_init_v1b = (
    FacturaProveedorForm.__init__
)
_factura_plan_canonico_original_clean_v1b = (
    FacturaProveedorForm.clean
)

_FACTURA_PLAN_CAMPOS_LEGACY_V1B = [
    "fecha_autorizacion_gerencia",
    "fecha_pago_segun_contrato",
    "fecha_real_pago",
    "importe_pagado",
    "forma_pago",
    "estado",
    "factura_pagada",
]


def _factura_plan_canonico_init_v1b(
    self,
    *args,
    **kwargs,
):
    _factura_plan_canonico_original_init_v1b(
        self,
        *args,
        **kwargs,
    )

    for field_name in (
        _FACTURA_PLAN_CAMPOS_LEGACY_V1B
    ):
        self.fields.pop(
            field_name,
            None,
        )


def _factura_plan_canonico_clean_v1b(self):
    cleaned = (
        _factura_plan_canonico_original_clean_v1b(
            self
        )
    )

    for field_name in (
        _FACTURA_PLAN_CAMPOS_LEGACY_V1B
    ):
        cleaned.pop(
            field_name,
            None,
        )

    return cleaned


FacturaProveedorForm.__init__ = (
    _factura_plan_canonico_init_v1b
)
FacturaProveedorForm.clean = (
    _factura_plan_canonico_clean_v1b
)

# GESTION_UNIDADES_COMPRA_FORMS_V1A
from django import forms as _ucv1a_forms

from .unit_catalog_v1 import (
    normalize_unit as _ucv1a_normalize_unit,
    unit_choices as _ucv1a_unit_choices,
)


def _ucv1a_current_value(
    form,
    field_name,
):
    return str(
        form.initial.get(
            field_name
        )
        or getattr(
            form.instance,
            field_name,
            "",
        )
        or ""
    ).strip()


def _ucv1a_apply_unit_select(
    form,
    field_name,
):
    if field_name not in form.fields:
        return

    current = _ucv1a_current_value(
        form,
        field_name,
    )

    field = form.fields[
        field_name
    ]

    field.required = False

    css = field.widget.attrs.get(
        "class",
        "",
    )

    field.widget = (
        _ucv1a_forms.Select(
            choices=_ucv1a_unit_choices(
                current_value=current,
            ),
            attrs={
                "class": (
                    css
                    + " form-select"
                ).strip(),
                "data-unit-catalog": (
                    "canonical-v1"
                ),
            },
        )
    )


if not hasattr(
    FacturaProveedorLineaForm,
    "_ucv1a_original_init",
):
    FacturaProveedorLineaForm._ucv1a_original_init = (
        FacturaProveedorLineaForm.__init__
    )

    FacturaProveedorLineaForm._ucv1a_original_clean = (
        FacturaProveedorLineaForm.clean
    )

    def _ucv1a_factura_init(
        self,
        *args,
        **kwargs,
    ):
        (
            FacturaProveedorLineaForm
            ._ucv1a_original_init(
                self,
                *args,
                **kwargs,
            )
        )

        _ucv1a_apply_unit_select(
            self,
            "unidad_compra",
        )

    def _ucv1a_factura_clean(
        self,
    ):
        cleaned = (
            FacturaProveedorLineaForm
            ._ucv1a_original_clean(
                self
            )
        )

        if cleaned is None:
            cleaned = {}

        cleaned[
            "unidad_compra"
        ] = _ucv1a_normalize_unit(
            cleaned.get(
                "unidad_compra"
            )
        )

        return cleaned

    FacturaProveedorLineaForm.__init__ = (
        _ucv1a_factura_init
    )

    FacturaProveedorLineaForm.clean = (
        _ucv1a_factura_clean
    )


if not hasattr(
    AlbaranProveedorLineaForm,
    "_ucv1a_original_init",
):
    AlbaranProveedorLineaForm._ucv1a_original_init = (
        AlbaranProveedorLineaForm.__init__
    )

    AlbaranProveedorLineaForm._ucv1a_original_clean = (
        AlbaranProveedorLineaForm.clean
    )

    def _ucv1a_albaran_init(
        self,
        *args,
        **kwargs,
    ):
        (
            AlbaranProveedorLineaForm
            ._ucv1a_original_init(
                self,
                *args,
                **kwargs,
            )
        )

        _ucv1a_apply_unit_select(
            self,
            "unidad_compra",
        )

        _ucv1a_apply_unit_select(
            self,
            "unidad",
        )

    def _ucv1a_albaran_clean(
        self,
    ):
        cleaned = (
            AlbaranProveedorLineaForm
            ._ucv1a_original_clean(
                self
            )
        )

        if cleaned is None:
            cleaned = {}

        if "unidad_compra" in cleaned:
            cleaned[
                "unidad_compra"
            ] = _ucv1a_normalize_unit(
                cleaned.get(
                    "unidad_compra"
                )
            )

        if "unidad" in cleaned:
            cleaned[
                "unidad"
            ] = _ucv1a_normalize_unit(
                cleaned.get(
                    "unidad"
                )
            )

        return cleaned

    AlbaranProveedorLineaForm.__init__ = (
        _ucv1a_albaran_init
    )

    AlbaranProveedorLineaForm.clean = (
        _ucv1a_albaran_clean
    )



# GESTION_DESCUENTO_PORCENTUAL_CANONICO_V1_R3
from django.forms import BaseForm as _GdpBaseForm
from django.core.exceptions import ValidationError as _GdpValidationError
from apps.gestion.services.descuento_linea import (
    calcular_linea_compra as _gdp_calcular,
    descuento_adicional_historico as _gdp_adicional_historico,
    marcar_semantica_canonica as _gdp_marcar,
)

_gestion_descuento_forms_patched_v1 = []


def _gdp_patch_form(cls):
    if getattr(cls, "_gdp_v1", False):
        return

    old_init = cls.__init__
    old_clean = cls.clean

    def new_init(self, *args, **kwargs):
        old_init(self, *args, **kwargs)

        if "descuento" in self.fields:
            self.fields["descuento"].label = "Descuento %"

        if "importe_descuento" in self.fields:
            self.fields["importe_descuento"].label = (
                "Importe descuento adicional (€)"
            )

            if not self.is_bound and getattr(self.instance, "pk", None):
                self.initial["importe_descuento"] = (
                    _gdp_adicional_historico(self.instance)
                )

    def new_clean(self):
        data = old_clean(self)

        fields = {
            "cantidad",
            "precio_unitario",
            "descuento",
            "importe_descuento",
            "importe_linea",
        }

        if not fields.issubset(self.fields):
            return data

        if any(name in self._errors for name in fields):
            return data

        try:
            result = _gdp_calcular(
                cantidad=data.get("cantidad"),
                precio_unitario=data.get("precio_unitario"),
                descuento_porcentaje=data.get("descuento") or 0,
                descuento_adicional=data.get("importe_descuento") or 0,
            )
        except _GdpValidationError as exc:
            self.add_error("descuento", exc)
            return data

        data["cantidad"] = result["cantidad"]
        data["precio_unitario"] = result["precio_unitario"]
        data["descuento"] = result["descuento_porcentaje"]
        data["importe_descuento"] = result["descuento_adicional"]
        data["importe_linea"] = result["base_linea"]

        self.instance.cantidad = result["cantidad"]
        self.instance.precio_unitario = result["precio_unitario"]
        self.instance.descuento = result["descuento_porcentaje"]
        self.instance.importe_descuento = result["descuento_adicional"]
        self.instance.importe_linea = result["base_linea"]

        _gdp_marcar(self.instance, result)
        return data

    cls.__init__ = new_init
    cls.clean = new_clean
    cls._gdp_v1 = True


for _name, _obj in list(globals().items()):
    try:
        if not isinstance(_obj, type):
            continue

        if not issubclass(_obj, _GdpBaseForm):
            continue

        _model = getattr(getattr(_obj, "_meta", None), "model", None)

        if getattr(_model, "__name__", "") not in {
            "FacturaProveedorLineaGestion",
            "AlbaranProveedorLineaGestion",
        }:
            continue

        _gdp_patch_form(_obj)
        _gestion_descuento_forms_patched_v1.append(_name)
    except (TypeError, AttributeError):
        continue


# ============================================================================
# FACTURA_LINEA_DESCUENTO_PORCENTUAL_SAVE_V2
# ============================================================================
#
# Regla canónica:
#
#   bruto = cantidad * precio_unitario
#
#   dto_porcentaje_importe =
#       bruto * descuento_porcentaje / 100
#
#   base =
#       bruto
#       - dto_porcentaje_importe
#       - descuento_adicional
#
# El campo:
#   descuento         = porcentaje
#   importe_descuento = importe adicional €
#
# Nunca interpretar descuento=20 como 20 €/unidad.
# ============================================================================


if not getattr(
    FacturaProveedorLineaForm,
    "_gestion_descuento_porcentual_save_v2",
    False,
):

    _factura_linea_clean_before_desc_pct_v2 = (
        FacturaProveedorLineaForm.clean
    )

    _factura_linea_save_before_desc_pct_v2 = (
        FacturaProveedorLineaForm.save
    )


    def _factura_linea_clean_descuento_pct_v2(
        self,
    ):

        cleaned = (
            _factura_linea_clean_before_desc_pct_v2(
                self
            )
        )

        from apps.gestion.services.descuento_linea import (
            calcular_linea_compra,
        )


        resultado = calcular_linea_compra(
            cantidad=(
                cleaned.get("cantidad")
                or 0
            ),

            precio_unitario=(
                cleaned.get(
                    "precio_unitario"
                )
                or 0
            ),

            descuento_porcentaje=(
                cleaned.get(
                    "descuento"
                )
                or 0
            ),

            descuento_adicional=(
                cleaned.get(
                    "importe_descuento"
                )
                or 0
            ),
        )


        cleaned[
            "descuento"
        ] = resultado[
            "descuento_porcentaje"
        ]

        cleaned[
            "importe_descuento"
        ] = resultado[
            "descuento_adicional"
        ]

        cleaned[
            "importe_linea"
        ] = resultado[
            "base_linea"
        ]


        self.cleaned_data = cleaned

        return cleaned


    def _factura_linea_save_descuento_pct_v2(
        self,
        commit=True,
    ):

        from apps.gestion.services.descuento_linea import (
            calcular_linea_compra,
            marcar_semantica_canonica,
        )


        # Ejecutar cualquier compatibilidad previa,
        # pero SIN permitir que escriba en BD.
        obj = (
            _factura_linea_save_before_desc_pct_v2(
                self,
                commit=False,
            )
        )


        data = (
            getattr(
                self,
                "cleaned_data",
                {},
            )
            or {}
        )


        resultado = calcular_linea_compra(
            cantidad=(
                data.get("cantidad")
                or getattr(
                    obj,
                    "cantidad",
                    0,
                )
                or 0
            ),

            precio_unitario=(
                data.get(
                    "precio_unitario"
                )
                or getattr(
                    obj,
                    "precio_unitario",
                    0,
                )
                or 0
            ),

            descuento_porcentaje=(
                data.get(
                    "descuento"
                )
                or 0
            ),

            descuento_adicional=(
                data.get(
                    "importe_descuento"
                )
                or 0
            ),
        )


        obj.descuento = (
            resultado[
                "descuento_porcentaje"
            ]
        )

        obj.importe_descuento = (
            resultado[
                "descuento_adicional"
            ]
        )

        obj.importe_linea = (
            resultado[
                "base_linea"
            ]
        )


        marcar_semantica_canonica(
            obj,
            resultado,
        )


        raw = (
            dict(
                obj.raw_data
            )
            if isinstance(
                getattr(
                    obj,
                    "raw_data",
                    None,
                ),
                dict,
            )
            else {}
        )


        raw[
            "factura_linea_descuento_porcentual_save_v2"
        ] = {
            "formula": (
                "cantidad * precio * "
                "(1 - descuento_pct/100) "
                "- descuento_adicional"
            ),

            "cantidad": str(
                resultado[
                    "cantidad"
                ]
            ),

            "precio_unitario": str(
                resultado[
                    "precio_unitario"
                ]
            ),

            "descuento_porcentaje": str(
                resultado[
                    "descuento_porcentaje"
                ]
            ),

            "descuento_porcentaje_importe": str(
                resultado[
                    "descuento_porcentaje_importe"
                ]
            ),

            "descuento_adicional": str(
                resultado[
                    "descuento_adicional"
                ]
            ),

            "base_linea": str(
                resultado[
                    "base_linea"
                ]
            ),
        }


        obj.raw_data = raw


        if commit:

            obj.save()

            if hasattr(
                self,
                "save_m2m",
            ):
                self.save_m2m()


        return obj


    FacturaProveedorLineaForm.clean = (
        _factura_linea_clean_descuento_pct_v2
    )

    FacturaProveedorLineaForm.save = (
        _factura_linea_save_descuento_pct_v2
    )

    FacturaProveedorLineaForm._gestion_descuento_porcentual_save_v2 = True



# ============================================================================
# FACTURA_LINEA_DECIMAL_INPUT_CANONICAL_V1
# ============================================================================
#
# Entrada decimal manual canónica.
#
#   1,246       -> 1.246
#   1.246       -> 1.246
#   1234,56     -> 1234.56
#   1.234,56    -> 1234.56
#   1,234.56    -> 1234.56
#
# Un único punto NO se interpreta como separador de miles.
#
# La normalización ocurre antes de DecimalField.to_python(),
# por lo que el servidor funciona correctamente aunque JS no actúe.
# ============================================================================


def _gestion_factura_linea_decimal_input_canonical_v1(
    value,
):
    import re

    if value is None:
        return value

    raw = str(value).strip()

    if not raw:
        return raw

    raw = (
        raw
        .replace("€", "")
        .replace("EUR", "")
        .replace("\u00a0", "")
        .replace(" ", "")
        .replace("'", "")
    )

    raw = re.sub(
        r"[^0-9,.\-]",
        "",
        raw,
    )

    if raw in {
        "",
        "-",
        ".",
        ",",
    }:
        return raw

    negative = raw.startswith("-")

    if negative:
        raw = raw[1:]

    if "." in raw and "," in raw:

        if raw.rfind(",") > raw.rfind("."):
            # Español:
            # 1.234,56 -> 1234.56
            raw = (
                raw
                .replace(".", "")
                .replace(",", ".")
            )

        else:
            # Técnico/anglosajón:
            # 1,234.56 -> 1234.56
            raw = raw.replace(",", "")

    elif "," in raw:

        # Español sin miles:
        # 1,246 -> 1.246
        raw = raw.replace(",", ".")

    elif raw.count(".") > 1:

        # Solo varios puntos:
        # 1.234.567 -> 1234567
        parts = raw.split(".")

        if (
            len(parts) > 2
            and all(
                part.isdigit()
                for part in parts
            )
            and all(
                len(part) == 3
                for part in parts[1:]
            )
        ):
            raw = "".join(parts)

    # Un único punto permanece intacto:
    # 1.246 -> 1.246

    if negative:
        raw = "-" + raw

    return raw


if not getattr(
    FacturaProveedorLineaForm,
    "_gestion_decimal_input_canonical_v1",
    False,
):

    _factura_linea_init_before_decimal_input_v1 = (
        FacturaProveedorLineaForm.__init__
    )


    def _factura_linea_init_decimal_input_v1(
        self,
        *args,
        **kwargs,
    ):

        _factura_linea_init_before_decimal_input_v1(
            self,
            *args,
            **kwargs,
        )

        if not self.is_bound:
            return

        try:
            data = self.data.copy()
        except Exception:
            return

        decimal_fields = (
            "cantidad",
            "precio_unitario",
            "importe_linea",
            "importe_descuento",
            "descuento",
            "cantidad_en_partidas",
            "iva_porcentaje",
            "iva_porcentaje_manual",
            "importe_iva_linea_calc",
            "total_linea_con_iva_calc",
        )

        for field_name in decimal_fields:

            key = self.add_prefix(
                field_name
            )

            if key not in data:
                continue

            original = data.get(key)

            if original in (
                None,
                "",
            ):
                continue

            data[key] = (
                _gestion_factura_linea_decimal_input_canonical_v1(
                    original
                )
            )

        self.data = data


    FacturaProveedorLineaForm.__init__ = (
        _factura_linea_init_decimal_input_v1
    )

    FacturaProveedorLineaForm._gestion_decimal_input_canonical_v1 = True
