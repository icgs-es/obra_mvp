# Puesta en marcha en Linux Mint (Ubuntu-based)

## ¿Docker Desktop o Docker Engine?
En Linux NO necesitas Docker Desktop. Instala **Docker Engine + Docker Compose plugin** (sin GUI).

## Paso 1 — Instalar Docker Engine + Compose
```bash
bash install_docker_mint.sh
# cierra sesión y vuelve a entrar (o: newgrp docker)
docker run --rm hello-world
docker compose version
```

## Paso 2 — Levantar el proyecto (desde la raíz del repo)
```bash
bash run_project.sh
```

Abre:
- App: http://localhost:8001/health
- Admin: http://localhost:8001/admin
- PgAdmin (si está en tu compose): http://localhost:5050
