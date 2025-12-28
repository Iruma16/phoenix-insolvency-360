# Jurisprudencia - Corpus Legal

## Fuente

**CENDOJ (Centro de Documentación Judicial)** - Sentencias seleccionadas

- CENDOJ: https://www.poderjudicial.es/cgpj/es/Temas/CENDOJ/
- Última actualización manual: Ver `metadata.json`

## Contenido

- **Archivos raw**: `raw/*.txt` (un archivo por sentencia)
- **Estrategia de chunking**: Por fundamento jurídico (cada fundamento relevante = 1 chunk)
- **Metadatos**: `court`, `date`, `case_ref`, `type`

## ⚠️ ADVERTENCIA LEGAL

**SELECCIÓN Y ACTUALIZACIÓN MANUAL OBLIGATORIA**

- NO se permite scraping automático
- NO se permite actualización sin criterio legal explícito
- Cada sentencia debe ser:
  1. Seleccionada por relevancia legal demostrable
  2. Aprobada por abogado especializado
  3. Documentada con referencia oficial
  4. Chunkeda por fundamentos jurídicos relevantes

Cualquier actualización debe:
  1. Ser aprobada por abogado especializado
  2. Actualizar `metadata.json` (fecha, referencia, hash, version_label)
  3. Regenerar embeddings manualmente
  4. Documentarse en este README

## Versionado

El campo `version_label` en `metadata.json` identifica de forma legible la selección de sentencias:
- Formato: "Jurisprudencia {órganos} seleccionada {rango temporal}"
- Ejemplo: "Jurisprudencia TS/AP seleccionada 2022-2024"
- Debe actualizarse cuando se añaden o modifican sentencias
- Permite trazabilidad clara de qué corpus jurisprudencial se está usando

## Uso

Este corpus es consumido por el **Legal RAG** para enriquecer las acusaciones del Prosecutor con jurisprudencia relevante.

## Chunking

Los chunks se generan por fundamento jurídico, preservando:
- Órgano jurisdiccional (TS, AP, etc.)
- Fecha de la sentencia
- Referencia del caso
- Fragmentos relevantes del fundamento jurídico

