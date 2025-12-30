# PHOENIX LEGAL - API REST

## 🚀 Inicio Rápido

### Iniciar el servidor

```bash
cd /Users/irumabragado/Documents/procesos/202512_phoenix-legal
source .venv/bin/activate
python app/api/public.py
```

El servidor estará disponible en: `http://localhost:8000`

### Documentación interactiva

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

---

## 📡 Endpoints

### 1. GET `/` - Información del servicio

```bash
curl http://localhost:8000/
```

**Respuesta**:
```json
{
  "service": "Phoenix Legal API",
  "version": "1.0.0",
  "status": "operational",
  "endpoints": [...]
}
```

---

### 2. POST `/cases` - Crear caso

```bash
curl -X POST http://localhost:8000/cases \
  -H "Content-Type: application/json" \
  -d '{
    "case_id": "CASE_001",
    "company_name": "Empresa Ejemplo SL",
    "sector": "Retail",
    "size": "PYME"
  }'
```

**Respuesta**:
```json
{
  "case_id": "CASE_001",
  "status": "created",
  "paths": {
    "documents": "clients_data/cases/CASE_001/documents",
    "reports": "clients_data/cases/CASE_001/reports"
  },
  "message": "Caso CASE_001 creado correctamente"
}
```

---

### 3. POST `/cases/{case_id}/documents` - Subir documento

```bash
curl -X POST http://localhost:8000/cases/CASE_001/documents \
  -F "file=@/path/to/balance.pdf"
```

**Respuesta**:
```json
{
  "case_id": "CASE_001",
  "filename": "balance.pdf",
  "size": 45678,
  "path": "clients_data/cases/CASE_001/documents/balance.pdf",
  "message": "Documento balance.pdf subido correctamente"
}
```

---

### 4. POST `/cases/{case_id}/analyze` - Analizar caso

```bash
curl -X POST http://localhost:8000/cases/CASE_001/analyze
```

**Respuesta**:
```json
{
  "case_id": "CASE_001",
  "status": "completed",
  "overall_risk": "high",
  "risks_count": 4,
  "legal_findings_count": 4,
  "pdf_path": "clients_data/cases/CASE_001/reports/phoenix_legal_report_CASE_001_20241230_120000.pdf",
  "message": "Análisis completado. PDF generado: ..."
}
```

---

### 5. GET `/cases/{case_id}/reports/latest` - Descargar último PDF

```bash
curl http://localhost:8000/cases/CASE_001/reports/latest \
  --output informe.pdf
```

**Respuesta**: Archivo PDF

---

## 🔧 Ejemplo Completo

```bash
# 1. Crear caso
curl -X POST http://localhost:8000/cases \
  -H "Content-Type: application/json" \
  -d '{"case_id": "CASE_DEMO", "company_name": "Demo SL"}'

# 2. Subir documentos
curl -X POST http://localhost:8000/cases/CASE_DEMO/documents \
  -F "file=@balance.txt"

curl -X POST http://localhost:8000/cases/CASE_DEMO/documents \
  -F "file=@acta.txt"

# 3. Analizar
curl -X POST http://localhost:8000/cases/CASE_DEMO/analyze

# 4. Descargar PDF
curl http://localhost:8000/cases/CASE_DEMO/reports/latest \
  --output informe_demo.pdf
```

---

## ✅ Tests

```bash
# Tests de API
pytest tests/test_api_cases.py -v
pytest tests/test_api_reports.py -v

# Todos los tests
pytest tests/test_api_*.py -v
```

---

## 🔑 Configuración

### Variables de entorno

```bash
# Opcional: API key para agentes LLM
export OPENAI_API_KEY="sk-..."

# El sistema funciona sin API key (modo heurístico)
```

---

## 📊 Códigos de Estado

| Código | Significado |
|--------|-------------|
| 200 | OK - Operación exitosa |
| 201 | Created - Caso creado |
| 400 | Bad Request - Datos inválidos |
| 404 | Not Found - Recurso no encontrado |
| 409 | Conflict - Caso duplicado |
| 500 | Internal Server Error - Error del servidor |

---

## 🎯 Notas Importantes

1. **El sistema funciona sin LLM**: Si no hay `OPENAI_API_KEY`, el análisis usa solo heurísticas
2. **Los PDFs se generan siempre**: Independiente de si hay LLM o no
3. **Casos persistentes**: Los casos se guardan en `clients_data/cases/`
4. **Documentos soportados**: TXT, PDF (más formatos próximamente)

---

## 🐛 Troubleshooting

### Error: "Caso no existe"
```bash
# Solución: Crear el caso primero
curl -X POST http://localhost:8000/cases -d '{"case_id": "CASE_X"}'
```

### Error: "No hay documentos"
```bash
# Solución: Subir al menos un documento
curl -X POST http://localhost:8000/cases/CASE_X/documents -F "file=@doc.txt"
```

### Error: "No hay reportes"
```bash
# Solución: Ejecutar el análisis primero
curl -X POST http://localhost:8000/cases/CASE_X/analyze
```

---

**Versión**: 1.0.0  
**Fecha**: 30 de diciembre de 2024

