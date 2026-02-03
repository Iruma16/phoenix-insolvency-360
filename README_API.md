# Phoenix Legal — API (mini guía)

La documentación principal está en `README.md`. Aquí solo lo mínimo para probar la API.

## Ejecutar

```bash
make run-api
```

## Docs

- Swagger: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Health

```bash
curl http://localhost:8000/health
```

## Informe de situación económica (internal vs client)

### Generar (sin descarga)

- `POST /api/cases/{case_id}/economic-report/generate`

### Descargar PDF ya generado

- Internal (por defecto): `GET /api/cases/{case_id}/economic-report/pdf?audience=internal`
- Client (exportación): `GET /api/cases/{case_id}/economic-report/pdf?audience=client`

Nota (audience=client):
- Requiere firma completa en `.env`: `LAWYER_NAME`, `LAWYER_COLLEGIATE_NUMBER`, `LAW_FIRM`, `LAWYER_SIGNATURE_DATE`
- Si falla cualquier requisito, la exportación se bloquea con `422` y motivos (y **no** se exporta PDF cliente).


