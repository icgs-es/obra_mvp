---
id: gestion.facturacion.crear_editar_factura
titulo: Crear y editar una factura
modulo: Gestión
submodulo: Facturación
resumen: Datos principales y comprobaciones al registrar una factura de proveedor.
palabras_clave: nueva factura, editar factura, proveedor, empresa, fecha, importe, líneas
permisos: gestion.access_gestion
rutas: /app/gestion/facturas/
orden: 13
actualizado: 2026-07-30
---

# Crear y editar una factura

## Cabecera

Comprueba especialmente:

- empresa;
- proveedor;
- número de factura del proveedor;
- fecha;
- ámbito de gestión;
- centro de coste;
- base imponible, IVA, retención y total.

Cuando el usuario tiene varias empresas autorizadas, debe elegir expresamente la empresa correcta.

## Líneas

Cada línea recoge el artículo o servicio, cantidad, precio, descuento, base e IVA.

Las observaciones de una línea permiten indicar su destino o aclaraciones operativas.

## Pagos

Las fechas, cuotas, importes pagados y estados de pago no se editan directamente en la factura.

Toda la información de pago se gestiona desde el **plan de pagos y vencimientos**.

## Antes de guardar

Revisa que la suma de las líneas coincide con la cabecera y que el número del proveedor no duplica otra factura existente.
