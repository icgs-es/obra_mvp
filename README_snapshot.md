# Snapshot rápido del proyecto

Fecha: 2025-08-18 11:56:54

## Archivos incluidos
- `snapshot_now.sh` — Script que:
  1. Inicializa git si no existe
  2. Crea `.gitignore` básico si falta
  3. Hace **commit** con tu mensaje (o por defecto con timestamp)
  4. Crea una **tag** con timestamp
  5. Genera 3 backups en `backups/`:
     - ZIP del `HEAD` (solo archivos trackeados)
     - TAR.GZ del `HEAD`
     - ZIP **FULL** de todo el árbol (excluyendo `venv/`, `node_modules/`, `__pycache__/`, `media/`, `staticfiles/`, y volúmenes locales comunes)

- `.gitignore_template.txt` — Por si quieres revisar/ajustar el `.gitignore` de referencia.

## Uso recomendado
1. Copia estos archivos a la **raíz** de tu proyecto (p.ej. `~/Documentos/proyectos/obra_mvp`).
2. Da permisos y ejecuta:
   ```bash
   chmod +x snapshot_now.sh
   ./snapshot_now.sh "estado estable: tabs CRUD ok"
   ```
3. Archivos generados en `./backups/`.

> Nota: `git archive` solo empaqueta lo que está **trackeado** por git. El ZIP **FULL** es por si todavía no trackeaste todo, pero evita incluir directorios pesados.
