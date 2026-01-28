# Phoenix Legal - Interfaz Web

Guía de uso de la interfaz web MVP con Streamlit.

---

## Inicio Rápido

### 1. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 2. Iniciar interfaz web

```bash
# 1) Iniciar API (en otra terminal)
uvicorn app.main:app --reload --port 8000

# 2) Iniciar UI
streamlit run app/ui/streamlit_mvp.py
```

La interfaz se abrirá automáticamente en http://localhost:8501

---

## Funcionalidades

### 📁 Gestión de Casos

**Crear Nuevo Caso:**
1. Ir a "Gestión de Casos"
2. Tab "Nuevo Caso"
3. Ingresar ID del caso (ej: `CASE_2024_001`)
4. Click en "Crear Caso"

**Ver Casos Existentes:**
1. Tab "Casos Existentes"
2. Ver lista de casos con documentos e informes
3. Click en "Seleccionar" para trabajar con un caso

---

### 📊 Análisis

**Subir Documentos:**
1. Seleccionar un caso primero
2. Ir a "Análisis"
3. Tab "Subir Documentos"
4. Arrastrar archivos o click en "Browse files"
5. Click en "Subir Documentos"

**Ejecutar Análisis:**
1. Tab "Ejecutar Análisis"
2. Click en "▶️ Iniciar Análisis"
3. Esperar (puede tomar 2-5 minutos)
4. Ver resumen de resultados

---

### 📄 Informes

**Descargar PDF:**
1. Seleccionar un caso
2. Ir a "Informes"
3. Click en "⬇️ Descargar PDF"

---

### 📈 Métricas

**Ver Métricas del Sistema:**
1. Ir a "Métricas"
2. Ver estadísticas de uso:
   - Casos analizados
   - Tiempos de ejecución
   - Tasa de éxito LLM/RAG
   - Errores

---

## Características

✅ **Interfaz Simple**: Diseño minimalista enfocado en funcionalidad  
✅ **Gestión de Casos**: Crear y organizar casos  
✅ **Carga de Documentos**: Subir PDF, TXT, DOCX  
✅ **Análisis Completo**: Ejecutar pipeline completo  
✅ **Progreso Visual**: Barra de progreso durante análisis  
✅ **Descarga PDF**: Informes listos para usar  
✅ **Métricas en Tiempo Real**: Observabilidad del sistema  

---

## Limitaciones (MVP)

- **Sin autenticación en UI** (usar API REST para auth)
- **Un usuario a la vez**
- **Sin edición de casos**
- **Sin comparación de informes**

Para funcionalidades avanzadas, usar la API REST (ver `README_API.md`).

---

## Troubleshooting

### Puerto 8501 en uso

```bash
streamlit run app/ui/streamlit_mvp.py --server.port 8502
```

### Error "Module not found"

```bash
pip install -r requirements.txt
```

### Análisis muy lento

- Verificar `OPENAI_API_KEY` configurada
- Sin API key, el sistema funciona pero puede ser más lento

---

**Phoenix Legal** — Análisis legal automatizado con IA.

