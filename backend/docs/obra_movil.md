# Obra móvil · Portal INTASA

Documento generado en Fase 7.

## Objetivo

Módulo mobile-first para registrar y consultar operaciones desde obra sin pasar por oficina ni por las antiguas mini-aplicaciones Access.

## Rutas principales

- `/app/obra-movil/` · Dashboard móvil.
- `/app/obra-movil/produccion/` · Sección producción.
- `/app/obra-movil/produccion/nueva/` · Alta de producción real.
- `/app/obra-movil/almacen/` · Sección almacén.
- `/app/obra-movil/almacen/nuevo/` · Alta de movimiento de almacén.
- `/app/obra-movil/stock/` · Consulta móvil de stock.
- `/app/obra-movil/stock/control/` · Control manual de stock.
- `/app/obra-movil/stock/control/<recurso>/` · Control directo de stock de un recurso.
- `/app/obra-movil/mortero/` · Sección mortero.
- `/app/obra-movil/mortero/nuevo/` · Acceso directo a salida de mortero.
- `/app/obra-movil/gasoil/` · Sección gasoil.
- `/app/obra-movil/gasoil/nuevo/` · Acceso directo a salida de gasoil.
- `/app/obra-movil/historial/` · Historial móvil.
- `/app/obra-movil/historial/produccion/<id>/` · Detalle de producción móvil.
- `/app/obra-movil/historial/movimiento/<id>/` · Detalle de movimiento móvil.
- `/app/obra-movil/incidencias/` · Listado de incidencias móviles.
- `/app/obra-movil/incidencias/nueva/` · Alta de incidencia móvil.
- `/app/obra-movil/incidencias/<id>/` · Detalle de incidencia móvil.

## Modelos reutilizados

- `planificacion_obra.TareaRecursoReal`
- `planificacion_obra.RecursoAlmacenMovimiento`
- `planificacion_obra.RecursoCatalogo`
- `planificacion_obra.AlmacenObra`
- `planificacion_obra.ObraPlanificacion`
- `planificacion_obra.UnidadObra`
- `planificacion_obra.TareaObra`
- `planificacion_obra.EmpleadoObra`

## Modelo nuevo

- `obra_movil.IncidenciaObraMovil`

Migración:

- `obra_movil/migrations/0001_incidencia_obra_movil.py`

## Producción móvil

La producción móvil crea registros directos en `TareaRecursoReal`.

Identificación técnica:

- `raw_data.origen = obra_movil_produccion`
- `legacy_id_recurso_tarea >= 900000000`

La producción móvil puede registrar:

- Mano de obra administrada.
- Material/recurso.

## Almacén móvil

El alta de almacén crea registros directos en `RecursoAlmacenMovimiento` y actualiza `RecursoCatalogo.stock`.

Identificación técnica:

- `raw_data.origen = obra_movil_almacen`

Reglas de stock:

- `ENTRADA` suma stock.
- `SALIDA` resta stock.
- `ROTURA` resta stock.
- `CONTROL_STOCK` fija stock al conteo real.

## Control stock móvil

Crea movimiento `CONTROL_STOCK` y fija `RecursoCatalogo.stock`.

Identificación técnica:

- `raw_data.origen = obra_movil_control_stock`

## Incidencias móviles

`IncidenciaObraMovil` permite registrar desde obra:

- Obra.
- Unidad/vivienda.
- Tarea.
- Empleado.
- Tipo.
- Prioridad.
- Estado.
- Fecha.
- Título.
- Descripción.
- Resolución.

Al crear incidencia vinculada a tarea, se marca:

- `TareaObra.con_incidencias = True`

Identificación técnica:

- `raw_data.origen = obra_movil_incidencia`

## Historial móvil

El historial muestra registros creados desde Obra móvil:

- Producción móvil.
- Movimientos de almacén móvil.
- Control stock móvil.

Las incidencias tienen listado propio en `/app/obra-movil/incidencias/`.

## Scope multiempresa

El módulo respeta empresa activa cuando existe. Si `active_team_id` es `all` o no existe:

- Superusuario ve todo.
- Usuario normal ve solo sus teams.

## Backups principales

- Fase 1: `obra_movil_fase1_dashboard_*`
- Fase 2A: `obra_movil_fase2a_produccion_*`
- Fix 2A scope: `fix_obra_movil_fase2a_queryset_scope_*`
- Fase 2B: `obra_movil_fase2b_filtros_produccion_*`
- Fase 3A: `obra_movil_fase3a_almacen_movimiento_*`
- Fase 3B: `obra_movil_fase3b_filtros_mortero_gasoil_*`
- Fase 4: `obra_movil_fase4_stock_control_*`
- Fase 5A: `obra_movil_fase5a_historial_*`
- Fase 5B: `obra_movil_fase5b_detalle_historial_*`
- Fix 5B scope: `fix_obra_movil_fase5b_detalle_scope_*`
- Fase 6B: `obra_movil_fase6b_incidencias_*`
- Fase 7: `obra_movil_fase7_cierre_tecnico_*`

## Pendientes UX detectados

- Mejorar búsqueda de recursos.
- Autocomplete/AJAX.
- Favoritos por almacén.
- Recursos recientes.
- Priorizar stock positivo.
- Posible QR/código de barras.
- Posible adjunto/foto en incidencias.
- Posible edición/cierre de incidencias desde móvil.

## UX 0 · Acceso móvil / usuario de obra

Añadido acceso móvil operativo:

- `/app/obra-movil/instalar/` · instrucciones de instalación.
- `/app/obra-movil/manifest.webmanifest` · manifest PWA específico.
- `/app/obra-movil/icon.svg` · icono SVG.
- Acceso directo desde dashboard móvil.
- Acceso directo desde login con `next=/app/obra-movil/`.
- Validación con usuario normal no superusuario y pertenencia a team.

Regla operativa:

- Usuarios de obra entran con usuario y contraseña del portal.
- No deben trabajar con superusuario.
- El usuario debe pertenecer a su `Team`.
- El acceso directo recomendado es `https://finaninvestgroup.com/app/obra-movil/`.

## UX 0B · Redirección usuario almacén

Se añade middleware:

- `obra_movil.middleware.ObraMovilUserRedirectMiddleware`

Regla:

- Si el usuario autenticado es `almacen`
- y entra en `/`, `/app/`, `/app/mi-jornada/`, `/app/jornada/` o `/app/dashboard/`
- se redirige automáticamente a `/app/obra-movil/`.

No afecta a otros usuarios.
No redirige dentro de `/app/obra-movil/`.

## ALM UX 1A · Almacén rápido

Nueva ruta:

- `/app/obra-movil/almacen/rapido/`

Objetivo:

- Pantalla rápida para operario de almacén.
- Buscar artículo por código o texto.
- Filtrar por Material, Maquinaria, Herramienta o E.P.I.S.
- Elegir movimiento: Salida, Entrada, C. Stock o Rotura.
- Indicar cantidad.
- Elegir destino operativo:
  - `PARTIDA`: vivienda/unidad + capítulo/partida, queda imputado.
  - `PERSONA`: empleado, queda pendiente de imputación administrativa.
  - `ALMACEN`: usado para entrada/control stock.

Reglas:

- SALIDA/ROTURA descuentan stock.
- ENTRADA suma stock.
- CONTROL_STOCK fija stock.
- Si destino es PARTIDA, `en_partida=True`.
- Si destino es PERSONA, se guarda `empleado` y queda sin `unidad_obra`/`partida`.
- `raw_data.ui = almacen_rapido`.
- `raw_data.destino_operativo` indica el destino elegido.
