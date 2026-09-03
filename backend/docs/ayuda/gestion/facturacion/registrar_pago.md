---
id: gestion.facturacion.registrar_pago
titulo: Registrar un vencimiento como pagado
modulo: Gestión
submodulo: Facturación
resumen: Requisitos y procedimiento para marcar una cuota realmente pagada.
palabras_clave: marcar pagado, registrar pago, administración, fecha real, referencia bancaria
permisos: gestion.access_gestion
rutas: /app/gestion/facturas/, /app/gestion/pagos
orden: 12
actualizado: 2026-07-30
---

# Registrar un vencimiento como pagado

## Requisito previo

El plan debe haber sido autorizado por Gerencia.

Mientras el plan permanezca sin autorizar, el Portal muestra el mensaje **Pendiente de autorización de Gerencia** y no permite marcar cuotas como pagadas.

## Registro del pago

Administración debe indicar:

- fecha real del pago;
- referencia bancaria, cuando exista;
- forma de pago;
- importe realmente pagado.

## Cambio de estado

Después del primer pago, la factura pasa a **PARCIAL** si todavía quedan vencimientos pendientes.

Cuando todos los vencimientos quedan pagados, la factura pasa a **PAGADA**.
