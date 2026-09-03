---
id: gestion.facturacion.planes_pago
titulo: Planes de pago y vencimientos
modulo: Gestión
submodulo: Facturación
resumen: Cómo crear, dividir, revisar y autorizar los vencimientos de una factura.
palabras_clave: plan de pagos, vencimiento, cuotas, dividir pago, autorizar plan
permisos: gestion.access_gestion
rutas: /app/gestion/facturas/, /app/gestion/pagos
orden: 11
actualizado: 2026-07-30
---

# Planes de pago y vencimientos

Toda la información de pago de una factura se gestiona mediante su **plan de pagos**.

## Pago único

Un pago único se representa mediante un solo vencimiento por el importe total de la factura.

## Varios vencimientos

Una factura puede dividirse en varias cuotas.

La suma de todas las cuotas debe coincidir exactamente con el total de la factura.

## Crear no significa autorizar

La creación o modificación de un plan no autoriza el pago.

Gerencia debe revisar las fechas, los importes y la forma de pago antes de pulsar **Autorizar plan de pagos**.

## Fechas pasadas

Una fecha de vencimiento pasada no convierte automáticamente una cuota en PAGADA.

El pago solo se considera realizado cuando una persona autorizada registra el pago real.
