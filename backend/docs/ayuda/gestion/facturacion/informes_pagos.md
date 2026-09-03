---
id: gestion.facturacion.informes_pagos
titulo: Informe de pagos pendientes
modulo: Gestión
submodulo: Facturación
resumen: Cómo interpreta el informe las fechas y cuotas pendientes.
palabras_clave: informe pagos, pagos pendientes, vencimiento, tesorería, fecha pago
permisos: gestion.access_gestion
rutas: /app/gestion/pagos, /app/gestion/facturas/
orden: 15
actualizado: 2026-07-30
---

# Informe de pagos pendientes

El informe utiliza los vencimientos del plan de pagos como fuente principal.

## Fecha utilizada

La fecha mostrada es la fecha de vencimiento de cada cuota.

No se utilizan como fuente principal los antiguos campos de pago de la cabecera de factura.

## Facturas con varias cuotas

Una misma factura puede aparecer en varios vencimientos cuando tiene un plan dividido.

## Estados

El informe debe distinguir entre:

- cuota pendiente;
- plan autorizado;
- cuota vencida;
- cuota pagada;
- factura parcialmente pagada.

Una fecha pasada no significa que la cuota esté pagada.
