# Facturación · Ayuda

## Regla principal
Crear un plan no significa autorizarlo, y una fecha vencida nunca convierte un pago en PAGADO automáticamente.

## Estados
- PENDIENTE: existe la factura y puede existir un plan, pero Gerencia todavía no lo ha autorizado.
- AUT. PAGO: Gerencia ha autorizado el plan y Administración ya puede registrar pagos.
- PARCIAL: existe al menos un vencimiento pagado, pero todavía queda saldo pendiente.
- PAGADA: todos los vencimientos del plan están realmente pagados.
- VENCIDO: es una señal del vencimiento, no una prueba de pago.

## Flujo correcto
1. Crear factura.
2. Definir plan de pagos.
3. Autorizar por Gerencia.
4. Registrar pagos reales por Administración.

## Regla histórica
- Factura histórica PAGADA → vencimiento histórico PAGADO.
- Factura histórica autorizada → AUT. PAGO.
- Factura histórica pendiente → sigue PENDIENTE hasta autorización expresa.
- Una fecha pasada no implica pago.
