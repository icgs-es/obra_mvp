---
id: archivos.acceso_visibilidad
titulo: Acceso, visibilidad y acciones sobre archivos
modulo: Archivos
submodulo: Permisos
resumen: Por qué un usuario puede ver un documento pero no moverlo, renombrarlo o eliminarlo.
palabras_clave: permiso archivo, mover, renombrar, eliminar, acceso denegado, visibilidad
permisos:
rutas: /app/archivos/
orden: 33
actualizado: 2026-07-30
---

# Acceso, visibilidad y acciones sobre archivos

Ver un archivo no implica disponer de todas las acciones sobre él.

Las operaciones pueden depender de:

- empresa;
- carpeta;
- propiedad;
- grupo;
- permisos asignados;
- reglas del almacenamiento.

## Acción denegada

Si el Portal permite ver el documento pero rechaza mover, renombrar o eliminar, el usuario no tiene el permiso efectivo para esa operación.

La solución correcta es revisar sus permisos o grupos.

No debe concederse acceso mediante la condición staff salvo que la persona necesite entrar en Django Admin.
