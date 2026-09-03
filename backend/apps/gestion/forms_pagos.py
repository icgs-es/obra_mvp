# FACTURA_PAGOS_MULTIPLES_V1
from django import forms
from django.forms import formset_factory
from django.utils import timezone


FORMA_PAGO_CHOICES = [
    ("", "---------"),
    ("CONTADO", "CONTADO"),
    # RECIBO_DOMICILIADO_INMEDIATO_V1
    ("RECIBO DOMICILIADO", "RECIBO DOMICILIADO"),
    ("TRANSFERENCIA", "TRANSFERENCIA"),
    ("DEVOLUCION", "DEVOLUCIÓN"),
    (
        "TRANSFERENCIA 30 D.F.F.",
        "TRANSFERENCIA 30 D.F.F.",
    ),
    (
        "TRANSFERENCIA 45 D.F.F.",
        "TRANSFERENCIA 45 D.F.F.",
    ),
    (
        "TRANSFERENCIA 60 D.F.F.",
        "TRANSFERENCIA 60 D.F.F.",
    ),
    (
        "RECIBO DOMICILIADO 30 D.F.F.",
        "RECIBO DOMICILIADO 30 D.F.F.",
    ),
    (
        "RECIBO DOMICILIADO 60 D.F.F.",
        "RECIBO DOMICILIADO 60 D.F.F.",
    ),
    (
        "PAGARE 30 D.F.F.",
        "PAGARE 30 D.F.F.",
    ),
    (
        "PAGARE 60 D.F.F.",
        "PAGARE 60 D.F.F.",
    ),
    (
        "PAGARE 90 D.F.F.",
        "PAGARE 90 D.F.F.",
    ),
    ("TARJETA CREDITO", "TARJETA CREDITO"),
    ("4 MESES", "4 MESES"),
]


class PlanPagoLineaForm(forms.Form):
    # FACTURA_PLAN_DATE_ISO_V1
    fecha_vencimiento = forms.DateField(
        label="Fecha de vencimiento",
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(
            format="%Y-%m-%d",
            attrs={
                "type": "date",
                "class": "form-control form-control-sm",
            },
        ),
    )

    importe_previsto = forms.DecimalField(
        label="Importe",
        max_digits=14,
        decimal_places=2,
        widget=forms.NumberInput(
            attrs={
                "step": "0.01",
                "class": "form-control form-control-sm",
            }
        ),
    )

    forma_pago = forms.ChoiceField(
        label="Forma de pago",
        required=False,
        choices=FORMA_PAGO_CHOICES,
        widget=forms.Select(
            attrs={
                "class": "form-select form-select-sm",
            }
        ),
    )

    observaciones = forms.CharField(
        label="Observaciones",
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control form-control-sm",
                "placeholder": "Opcional",
            }
        ),
    )


PlanPagoFormSet = formset_factory(
    PlanPagoLineaForm,
    extra=0,
    can_delete=True,
    min_num=1,
    validate_min=True,
)


class RegistrarPagoVencimientoForm(forms.Form):
    fecha_real_pago = forms.DateField(
        required=False,
        initial=timezone.localdate,
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(
            format="%Y-%m-%d",
            attrs={
                "type": "date",
                "class": "form-control form-control-sm",
            },
        ),
    )

    referencia_pago = forms.CharField(
        required=False,
        max_length=255,
        widget=forms.TextInput(
            attrs={
                "class": "form-control form-control-sm",
                "placeholder": "Referencia bancaria",
            }
        ),
    )
