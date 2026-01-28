# Phoenix Legal — Docker (mini guía)

Esta guía es intencionalmente corta. Para ejecución local sin Docker, ver `README.md`.

## Ejecutar

```bash
cp .env.example .env
cd docker
docker compose build
docker compose up
```

Health:

```bash
curl http://localhost:8000/health
```

