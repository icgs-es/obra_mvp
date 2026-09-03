# Comparativas

Módulo de expedientes para comparación de ofertas.

## Frontera de arquitectura

El núcleo de Comparativas no depende de modelos de:

- Facturas
- Albaranes
- Proveedores
- Obras

Las referencias de proveedor y proyecto se almacenan como referencias
externas y snapshots.

Las dependencias particulares de PORTAL INTASA se concentran en:

    comparativas/integrations.py

Esto permite sustituir la integración cuando el módulo se incorpore
a ORDIX u otra instalación.

## Documento original

DocumentoComparativa conserva el fichero original y su SHA-256.

La extracción documental y el razonamiento IA deberán escribirse en
campos separados y nunca modificar el documento original.

## Fases previstas

V1:
- expediente
- ofertantes
- versiones
- archivos multiformato

V2:
- extracción documental común
- adaptador INTASA IA / proveedor IA

V3:
- partidas normalizadas
- matching semántico
- confianza de coincidencia
- revisión humana

V4:
- adjudicación
- creación/vinculación de proveedor
- informes ejecutivos
