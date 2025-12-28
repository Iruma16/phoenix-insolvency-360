# Ley Concursal - Corpus Legal

## Fuente

**Ley 22/2003, de 9 de julio, Concursal** (texto consolidado)

- BOE: https://www.boe.es/buscar/act.php?id=BOE-A-2003-14086
- Última actualización manual: Ver `metadata.json`

## Contenido

- **Archivo raw**: `raw/ley_concursal_consolidada.txt`
- **Estrategia de chunking**: Por artículo (cada artículo = 1 chunk)
- **Metadatos**: `article`, `law`, `type`

## ⚠️ ADVERTENCIA LEGAL

**ACTUALIZACIÓN MANUAL OBLIGATORIA**

- NO se permite scraping automático
- NO se permite actualización sin revisión legal previa
- Cualquier actualización debe:
  1. Ser aprobada por abogado especializado
  2. Actualizar `metadata.json` (fecha, referencia, hash, version_label)
  3. Regenerar embeddings manualmente
  4. Documentarse en este README

## Versionado

El campo `version_label` en `metadata.json` identifica de forma legible la versión del corpus:
- Formato: "LC consolidada BOE {fecha}"
- Ejemplo: "LC consolidada BOE 2024-01-01"
- Debe actualizarse cada vez que se ingiere una nueva versión
- Permite trazabilidad clara de qué versión legal se está usando

## Uso

Este corpus es consumido por el **Legal RAG** para enriquecer las acusaciones del Prosecutor con citas legales específicas.

## Chunking

Los chunks se generan por artículo, preservando:
- Número de artículo
- Texto completo del artículo
- Referencia a la ley

