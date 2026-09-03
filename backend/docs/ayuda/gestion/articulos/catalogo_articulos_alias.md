---
id: gestion.articulos.catalogo_alias
titulo: Artículos, recursos y alias de proveedor
modulo: Gestión
submodulo: Catálogo de compras
resumen: Cómo reutiliza el Portal los artículos identificados en facturas y albaranes.
palabras_clave: artículo, recurso, alias, código proveedor, descripción, catálogo compras
permisos: gestion.access_gestion
rutas: /app/gestion/articulos/, /app/gestion/facturas/, /app/gestion/albaranes/
orden: 26
actualizado: 2026-07-30
---

# Artículos, recursos y alias de proveedor

El catálogo evita crear una referencia distinta cada vez que se registra el mismo material o servicio.

## Artículo o recurso

Representa el concepto común utilizado por el Portal.

## Alias de proveedor

Relaciona la descripción o código utilizado por un proveedor con el artículo común.

## Al registrar una línea

Busca primero por:

- nombre;
- parte de la descripción;
- código del proveedor;
- tipo de recurso.

Solo debe crearse un artículo nuevo cuando no existe una referencia equivalente.
