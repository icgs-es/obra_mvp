from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.forms import formset_factory

from planificacion_obra.models import ObraPlanificacion

from .forms_pagos import PlanPagoLineaForm
from .models import PresupuestoProveedorGestion, Proveedor
from .views import _validar_pdf_compra_upload


class PresupuestoForm(forms.ModelForm):
    class Meta:
        model = PresupuestoProveedorGestion
        fields = (
            "proveedor", "obra", "numero_proveedor", "concepto", "fecha_emision", "fecha_entrega",
            "valido_hasta", "importe_total", "condiciones_pago", "observaciones", "pdf",
        )
        widgets = {"pdf": forms.FileInput(attrs={"accept": "application/pdf"})} | {
            name: forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"})
            for name in ("fecha_emision", "fecha_entrega", "valido_hasta")
        }

    def __init__(self, *args, team, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["proveedor"].queryset = Proveedor.objects.filter(team=team)
        self.fields["obra"].queryset = ObraPlanificacion.objects.filter(team=team)
        for field in self.fields.values():
            field.widget.attrs["class"] = (
                "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            )
        for name in ("condiciones_pago", "observaciones"):
            self.fields[name].widget.attrs["rows"] = 2

    def clean_pdf(self):
        pdf = self.cleaned_data["pdf"]
        if self.files.get("pdf") and pdf:
            _validar_pdf_compra_upload(pdf)
            signature = pdf.read(5)
            pdf.seek(0)
            if signature != b"%PDF-":
                raise ValidationError("El archivo debe ser un PDF válido.")
        return pdf

    def clean_importe_total(self):
        total = self.cleaned_data["importe_total"]
        if total is not None and total < 0:
            raise ValidationError("El total debe ser igual o superior a cero.")
        if self.instance.pk and total is not None:
            previsto = sum(self.instance.vencimientos.values_list("importe_previsto", flat=True))
            if previsto > total:
                raise ValidationError("El total es inferior a lo ya planificado. Ajusta primero el plan.")
        return total


class PresupuestoPagoForm(PlanPagoLineaForm):
    hito = forms.CharField(
        label="Hito", max_length=160, required=False,
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["fecha_vencimiento"].required = False
        self.fields["importe_previsto"].widget.attrs["min"] = "0.01"

    def clean_importe_previsto(self):
        importe = self.cleaned_data["importe_previsto"]
        if importe < Decimal("0.01"):
            raise ValidationError("El importe debe ser mayor que cero.")
        return importe

    def clean(self):
        data = super().clean()
        if not data.get("fecha_vencimiento") and not data.get("hito"):
            self.add_error("hito", "Indica un hito o una fecha prevista.")
        return data


PresupuestoPlanFormSet = formset_factory(
    PresupuestoPagoForm, extra=1, can_delete=True, max_num=50, validate_max=True,
)
