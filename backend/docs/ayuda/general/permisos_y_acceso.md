---
id: general.permisos_y_acceso
titulo: Permisos, grupos y acceso a funciones
modulo: General
submodulo: Seguridad
resumen: Por qué algunos usuarios ven módulos, botones o acciones diferentes.
palabras_clave: permisos, grupos, acceso, denegado, staff, superusuario, botones
permisos:
rutas: /app/
orden: 3
actualizado: 2026-07-30
---

# Permisos, grupos y acceso a funciones

El Portal utiliza permisos y grupos para decidir qué información y acciones puede utilizar cada persona.

## Acceso por grupos

Los permisos funcionales se asignan normalmente mediante grupos como Gerencia, Administración, Comercializadora u otros grupos internos.

## Superusuario

El superusuario dispone de acceso completo y puede administrar permisos desde Django Admin.

## Staff no es un permiso funcional

La condición **staff** debe reservarse para entrar en Django Admin.

No debe utilizarse como sustituto de los permisos normales del Portal.

## Acción denegada

Si una operación muestra un mensaje de acceso denegado, significa que el usuario no tiene el permiso efectivo requerido, aunque pueda visualizar la pantalla o algún botón.

En ese caso debe revisarse su grupo o permiso desde la administración.
