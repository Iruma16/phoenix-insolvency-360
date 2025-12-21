@echo off
TITLE Phoenix Insolvency 360 - Launcher
ECHO Iniciando Sistema...

:: COMANDO CLAVE: %~dp0 es la ruta de este archivo. 
:: "..\" le dice que suba una carpeta hacia arriba (al proyecto principal).
CD /D "%~dp0.."

ECHO Detectando entorno virtual...
IF EXIST "venv\Scripts\activate.bat" (
    CALL venv\Scripts\activate.bat
) ELSE (
    ECHO No se encuentra el entorno virtual. Instalando dependencias...
    python -m venv venv
    CALL venv\Scripts\activate.bat
    pip install -r requirements.txt
)

ECHO Lanzando Aplicacion Web...
streamlit run app.py
PAUSE