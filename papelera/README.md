# 🦅 Phoenix Legal: Insolvency 360

![Status](https://img.shields.io/badge/Status-Production_Ready-green)
![Python](https://img.shields.io/badge/Python-3.9+-blue)
![AI](https://img.shields.io/badge/AI-GPT_4o-purple)

**Phoenix Legal** es una plataforma SaaS de **Auditoría Forense Automatizada** diseñada para administradores concursales. Utiliza Inteligencia Artificial Generativa para ingerir documentación desestructurada (facturas PDF), validarla y cruzarla con registros bancarios para detectar fraudes e insolvencias.

---

## 🚀 Características Principales

* **🧠 Ingesta Inteligente:** Extracción de datos financieros de PDFs usando GPT-4o (Temp=0).
* **🛡️ Seguridad del Dato:** Base de datos SQL con control de integridad y rechazo de duplicados.
* **⛓️ Trazabilidad Forense:** Almacenamiento de la evidencia original (`raw_text`) junto al dato procesado.
* **📊 Dashboard Financiero:** Visualización en tiempo real de la evolución de la deuda y acreedores.
* **📑 Informes Automáticos:** Redacción de informes ejecutivos de insolvencia listos para el juzgado.

---

## 🛠️ Stack Tecnológico

* **Core:** Python 3.9+
* **Frontend:** Streamlit
* **IA:** OpenAI API (GPT-4o)
* **Base de Datos:** SQLite3
* **ETL:** PDFPlumber, Pandas

---

## 📦 Instalación y Uso

### 1. Requisitos Previos
Necesitas tener instalado Python y una API Key de OpenAI.

### 2. Configuración
Clona el repositorio y crea un archivo `.env`:
```bash
OPENAI_API_KEY="tu-clave-aqui"

---
## ⚖️ Licencia y Derechos de Uso

**© 2025 Iruma Bragado. Todos los derechos reservados.**

El código fuente de este proyecto se publica únicamente con fines demostrativos y educativos para procesos de selección y portafolio técnico.

🚫 **Prohibiciones:**
* No está permitido el uso comercial de este software.
* No está permitida la redistribución ni la modificación del código sin autorización expresa de la autora.
* Este proyecto es Propiedad Intelectual de Iruma Bragado.