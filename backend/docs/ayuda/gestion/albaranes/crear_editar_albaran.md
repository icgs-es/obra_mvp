---
id: gestion.albaranes.crear_editar
titulo: Crear y editar un albarán
modulo: Gestión
submodulo: Albaranes
resumen: Datos necesarios para registrar correctamente un albarán de proveedor.
palabras_clave: nuevo albarán, editar albarán, proveedor, empresa, fecha entrega, líneas
permisos: gestion.access_gestion
rutas: /app/gestion/albaranes/
orden: 20
actualizado: 2026-07-30
---

# Crear y editar un albarán

## Datos principales

Comprueba:

- empresa;
- proveedor;
- número de albarán del proveedor;
- fecha del albarán;
- fecha de entrega;
- ámbito;
- centro de coste.

El formulario no debe asumir una empresa cuando el usuario puede trabajar con varias.

## Líneas

Cada línea puede incluir artículo, código del proveedor, descripción, cantidad, unidad de compra, precio e importe.

## Duplicados

El Portal controla los albaranes repetidos utilizando empresa, proveedor y número del proveedor.

Antes de crear un registro nuevo, busca el número del albarán para comprobar que no existe.
