from decimal import Decimal

from django.db.models import Sum, Count

from apps.gestion.models import FacturaProveedorGestion, AlbaranProveedorGestion


TOLERANCIA = Decimal("0.02")


def auditar_factura(factura):
    agg = factura.lineas.aggregate(
        suma_lineas=Sum("importe_linea"),
        num_lineas=Count("id"),
    )

    suma_lineas = agg["suma_lineas"] or Decimal("0.00")
    num_lineas = agg["num_lineas"] or 0
    diferencia = factura.importe_base_imponible - suma_lineas

    if num_lineas == 0:
        estado = "SIN_LINEAS"
    elif abs(diferencia) > TOLERANCIA:
        estado = "DIFERENCIA_LINEAS"
    else:
        estado = "OK"

    return {
        "estado": estado,
        "num_lineas": num_lineas,
        "base_cabecera": factura.importe_base_imponible,
        "suma_lineas": suma_lineas,
        "diferencia": diferencia,
    }


def auditar_albaran(albaran):
    agg = albaran.lineas.aggregate(
        suma_lineas=Sum("importe_linea"),
        num_lineas=Count("id"),
    )

    suma_lineas = agg["suma_lineas"] or Decimal("0.00")
    num_lineas = agg["num_lineas"] or 0
    diferencia = albaran.importe_albaran - suma_lineas

    if num_lineas == 0:
        estado = "SIN_LINEAS"
    elif abs(diferencia) > TOLERANCIA:
        estado = "DIFERENCIA_LINEAS"
    else:
        estado = "OK"

    return {
        "estado": estado,
        "num_lineas": num_lineas,
        "importe_cabecera": albaran.importe_albaran,
        "suma_lineas": suma_lineas,
        "diferencia": diferencia,
    }


def resumen_auditoria_gestion():
    resumen = {
        "facturas": {
            "OK": 0,
            "SIN_LINEAS": 0,
            "DIFERENCIA_LINEAS": 0,
        },
        "albaranes": {
            "OK": 0,
            "SIN_LINEAS": 0,
            "DIFERENCIA_LINEAS": 0,
        },
    }

    for factura in FacturaProveedorGestion.objects.all():
        resumen["facturas"][auditar_factura(factura)["estado"]] += 1

    for albaran in AlbaranProveedorGestion.objects.all():
        resumen["albaranes"][auditar_albaran(albaran)["estado"]] += 1

    return resumen
