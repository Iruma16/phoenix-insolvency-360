import csv
import database # Importamos nuestro gestor de base de datos

# Ruta del archivo
ARCHIVO_CSV = "data/contabilidad.csv"

def cargar_contabilidad():
    print(f"📊 Abriendo libro contable: {ARCHIVO_CSV}...")
    
    # 1. Aseguramos que la tabla exista
    database.crear_tablas()
    
    try:
        with open(ARCHIVO_CSV, mode='r', encoding='utf-8') as f:
            lector = csv.reader(f)
            
            # Saltamos la cabecera (la primera línea que dice "ID, Concepto...")
            next(lector)
            
            contador = 0
            for fila in lector:
                # fila es una lista: ['1', 'Prestamo ICO', '2024-01-15', '-15000', ...]
                
                # Convertimos el ID y el Importe a números reales
                datos_limpios = [
                    int(fila[0]),       # ID
                    fila[1],            # Concepto
                    fila[2],            # Fecha
                    float(fila[3]),     # Importe (OJO: float para decimales)
                    fila[4],            # Estado
                    fila[5]             # Tipo Deuda
                ]
                
                # Guardamos en la base de datos
                database.guardar_asiento_contable(datos_limpios)
                contador += 1
                
            print(f"✅ Se han importado {contador} asientos contables correctamente.")

    except Exception as e:
        print(f"❌ Error leyendo el CSV: {e}")

if __name__ == "__main__":
    cargar_contabilidad()