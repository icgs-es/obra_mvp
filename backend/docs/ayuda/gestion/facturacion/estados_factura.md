---
id: gestion.facturacion.estados_factura
titulo: Estados de una factura
modulo: Gestión
submodulo: Facturación
resumen: Diferencias entre PENDIENTE, AUT. PAGO, PARCIAL y PAGADA.
palabras_clave: estado factura, pendiente, aut pago, parcial, pagada, vencido
permisos: gestion.access_gestion
rutas: /app/gestion/facturas/, /app/gestion/pagos
orden: 10
actualizado: 2026-07-30
---

# Estados de una factura

## PENDIENTE

La factura existe y puede tener un plan de pagos, pero **Gerencia todavía no ha autorizado el pago**.

Crear un plan no significa autorizarlo.

## AUT. PAGO

Gerencia ha revisado y autorizado el plan de pagos.

A partir de este momento, los usuarios autorizados de Administración pueden registrar los pagos realmente realizados.

## PARCIAL

Al menos uno de los vencimientos ha sido pagado, pero todavía queda importe pendiente.

## PAGADA

Todos los vencimientos del plan están realmente pagados.

## VENCIDO

VENCIDO es una señal relacionada con la fecha.

Una cuota vencida puede seguir pendiente o autorizada. Una fecha pasada **nunca demuestra que el pago se haya realizado**.
