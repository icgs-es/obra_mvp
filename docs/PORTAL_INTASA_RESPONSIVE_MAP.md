# PORTAL INTASA · MAPA RESPONSIVE MÓVIL / TABLET

## Objetivo

Este documento sirve como referencia rápida para futuras mejoras responsive de **INTASA PLATFORM**.

Cuando se solicite mejorar una pantalla para **móvil o tablet**, usar primero este mapa antes de buscar archivos al azar.

---

## 1. Agenda — archivos principales

### Calendario principal
**Archivo**
`backend/agenda/templates/agenda/calendar.html`

**Contiene**
- FullCalendar 6.1.15.
- Vista Día / 3 días / Mes / Lista.
- Toolbar y navegación.
- Filtros de visibilidad.
- Colores y render de eventos.
- Responsive móvil principal.
- Botones `Nuevo evento` y `Añadir tarea`.
- Importar / Exportar visibles solo para `is_superuser`.

**Marcadores importantes**
- `PORTAL_RESPONSIVE_AGENDA_V1_MOBILE`
- `PORTAL_AGENDA_V1_1_ACTIONS_ADMIN`

**Usar este archivo cuando**
- El calendario no entra bien en móvil.
- Hay que cambiar tamaños de horas, eventos o cabecera.
- Hay que modificar Día / Semana / 3 días / Mes / Lista.
- Hay que ajustar toolbar, filtros o botones.
- Hay que mejorar tablet horizontal/vertical.

---

### Formulario de Evento
**Archivo**
`backend/agenda/templates/agenda/form.html`

**Contiene**
- Crear / editar evento.
- Título.
- Calendario.
- Estado.
- Inicio / Fin.
- Todo el día.
- Visibilidad.
- Ubicación.
- Asistentes.
- Notas.
- Recordatorio.
- Responsive móvil en una sola columna.

**Marcador**
- `PORTAL_AGENDA_FORM_RESPONSIVE_V1`

**Usar este archivo cuando**
- Un campo se sale del ancho.
- Inicio / Fin aparecen comprimidos.
- Selects o inputs son demasiado grandes.
- Hay que mejorar Asistentes.
- Hay que adaptar botones Guardar / Cancelar.

---

### Formulario de Tarea
**Archivo**
`backend/tareas/templates/tareas/form.html`

**Contiene**
- Crear / editar tarea.
- Título y descripción.
- Estado y prioridad.
- Vencimiento.
- Inicio / fin programado.
- Visibilidad.
- Asignados.
- Botones Guardar / Guardar y nueva / Cancelar.

**Marcador**
- `PORTAL_TASK_FORM_RESPONSIVE_V1`

**Usar este archivo cuando**
- El formulario de tareas necesita ajustes móvil/tablet.
- Hay que mejorar selector de Asignados.
- Estado / prioridad necesitan otro layout móvil.

---

## 2. Lógica y permisos relacionados con Agenda

### Vistas
**Archivo**
`backend/agenda/views.py`

**Importante**
No modificar para cambios puramente visuales salvo que haya un requisito de permisos o comportamiento.

Actualmente:
- Importar agenda: solo `request.user.is_superuser`.
- Exportar agenda: solo `request.user.is_superuser`.

**Marcador**
- `PORTAL_AGENDA_ADMIN_IO_V1`

---

### Permisos / alcance
**Archivo**
`backend/agenda/access.py`

Gestiona:
- Alcance de Gerencia.
- Privacidad.
- Visibilidad de eventos.
- `user_is_agenda_manager`.

**Regla**
No tocar para responsive salvo que el cambio solicitado sea realmente funcional.

---

## 3. Responsive general del Portal

### Base general
**Archivo**
`backend/templates/base.html`

Usar cuando el problema afecte:
- Navbar.
- Cabecera global.
- Menú hamburguesa.
- Márgenes generales.
- Contenedor principal.
- Comportamiento común a varios módulos.

**Precaución**
Un cambio aquí puede afectar todo INTASA PLATFORM.

---

### Base específica de Obra móvil
**Archivo**
`backend/templates/obra_movil/base_mobile.html`

Usar para:
- Pantallas específicas del módulo `obra_movil`.
- Layout base móvil de almacén, stock, etc.

---

## 4. Otros módulos con responsive propio

### Productividad / planificación
Archivos frecuentes:

`backend/templates/planificacion_obra/_responsive_productividad.css`

`backend/templates/planificacion_obra/asignaciones_informe.html`

`backend/templates/planificacion_obra/asignaciones_calendario.html`

Usar solo cuando la mejora pertenece a Planificación / Productividad.

---

### Almacén móvil
Archivos frecuentes:

`backend/templates/obra_movil/almacen_rapido.html`

`backend/templates/obra_movil/almacen_movimientos.html`

`backend/templates/obra_movil/stock_rapido.html`

`backend/templates/obra_movil/stock_explanation_report.html`

---

## 5. Criterio responsive acordado

### Móvil vertical
Prioridad máxima.

Objetivo:
- Una sola columna cuando sea posible.
- Sin scroll horizontal.
- Inputs y selects al 100%.
- Texto legible.
- Controles táctiles de al menos ~44 px.
- Evitar versiones de escritorio comprimidas.
- Ocultar elementos secundarios si consumen demasiado espacio.
- Mantener acciones principales visibles.

### Tablet
Objetivo:
- Aprovechar más ancho que móvil.
- Permitir 2 columnas cuando realmente aporten valor.
- En calendarios: más días visibles sin perder legibilidad.
- Tablet horizontal puede acercarse al layout desktop.

---

## 6. Regla para FullCalendar

Para Agenda:

**NO intentar mostrar siempre 7 días en móvil vertical.**

Estado actual:
- Móvil: `timeGridDay`, `timeGridMobile3`, `dayGridMonth`, `listWeek`.
- Desktop: `dayGridMonth`, `timeGridWeek`, `timeGridDay`, `listWeek`.
- Breakpoint móvil actual: `max-width: 640px`.

Si se mejora tablet, hacerlo con un breakpoint nuevo sin romper el comportamiento móvil existente.

---

## 7. Flujo de trabajo recomendado por SSH

Siempre:

1. Inspección.
2. `git status --short`.
3. Backup del archivo concreto.
4. Parche mínimo.
5. Validar template Django.
6. `python manage.py check`.
7. Tests dirigidos.
8. Reiniciar solo el servicio necesario, normalmente `web`.
9. Esperar `healthy`.
10. Verificación visual real en móvil/tablet.
11. Commit separado y claro.

Evitar:
- `git reset`.
- Limpiar cambios ajenos.
- Reescribir varios módulos a la vez.
- Mezclar responsive con lógica de negocio.

---

## 8. Estado actual Agenda Responsive

Bloques implementados:

- `PORTAL_RESPONSIVE_AGENDA_V1_MOBILE`
- `PORTAL_AGENDA_V1_1_ACTIONS_ADMIN`
- `PORTAL_AGENDA_FORM_RESPONSIVE_V1`
- `PORTAL_TASK_FORM_RESPONSIVE_V1`
- `PORTAL_AGENDA_ADMIN_IO_V1`

Estado:
- Agenda móvil vertical usable.
- Día / 3 días / Mes / Lista operativos.
- `Nuevo evento` + `Añadir tarea`.
- Importar / Exportar solo Administrador General (`is_superuser`).
- Formulario Evento responsive.
- Formulario Tarea responsive.
- `web` validado `healthy`.

---

## 9. Próxima mejora recomendada

### Asistentes / Asignados
El `<select multiple>` tradicional funciona, pero no es ideal en móvil.

Siguiente mejora sugerida:
- Selector táctil.
- Búsqueda por usuario.
- Chips o lista seleccionable.
- Mantener compatibilidad con los formularios Django existentes.

Archivos a revisar:
- `backend/agenda/templates/agenda/form.html`
- `backend/agenda/forms.py`
- `backend/tareas/templates/tareas/form.html`
- `backend/tareas/forms.py`

---

## Frase de contexto para iniciar un nuevo hilo

> Proyecto PORTAL INTASA. Usa `PORTAL_INTASA_RESPONSIVE_MAP.md` como mapa de referencia. Quiero modificar responsive móvil/tablet sin tocar lógica de negocio salvo que sea imprescindible. Trabajaremos por SSH con inspección, backup, parche mínimo, tests y reinicio solo de `web`.
