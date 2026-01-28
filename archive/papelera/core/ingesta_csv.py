import pandas as pd
import io

def detectar_columna(columnas_disponibles, posibles_nombres):
    """
    Busca si alguna de las columnas del Excel coincide con nuestra lista de sinónimos.
    Devuelve el nombre real de la columna en el Excel o None.
    """
    # Convertimos todo a minúsculas para comparar mejor
    cols_lower = [c.lower() for c in columnas_disponibles]
    
    for candidato in posibles_nombres:
        if candidato in cols_lower:
            idx = cols_lower.index(candidato)
            return columnas_disponibles[idx] # Devolvemos el nombre original exacto
            
    # Si no encuentra coincidencia exacta, buscamos parcial (ej: "Fecha" en "Fecha Operación")
    for col in columnas_disponibles:
        for candidato in posibles_nombres:
            if candidato in col.lower():
                return col
                
    return None

def normalizar_datos(df):
    """
    Transforma cualquier Excel bancario al estándar: Fecha, Concepto, Importe.
    """
    df.columns = df.columns.str.strip() # Limpiar espacios
    cols = df.columns.tolist()
    
    # 1. DICCIONARIOS DE SINÓNIMOS (Esto es lo que hace que funcione con cualquier banco)
    # Patrones para FECHA
    posibles_fechas = ['fecha', 'date', 'f.valor', 'f. valor', 'f.operacion', 'f. operación', 'día', 'dia', 'time']
    # Patrones para CONCEPTO
    posibles_conceptos = ['concepto', 'descripción', 'descripcion', 'detalle', 'movimiento', 'asunto', 'transacción', 'transaction', 'leyenda']
    # Patrones para IMPORTE
    posibles_importes = ['importe', 'amount', 'cantidad', 'saldo', 'euros', 'valor', 'cuantia', 'monto']

    # 2. DETECCIÓN AUTOMÁTICA
    col_fecha = detectar_columna(cols, posibles_fechas)
    col_concepto = detectar_columna(cols, posibles_conceptos)
    col_importe = detectar_columna(cols, posibles_importes)

    # 3. RENOMBRADO O ERROR
    nuevas_cols = {}
    if col_fecha: nuevas_cols[col_fecha] = 'Fecha'
    if col_concepto: nuevas_cols[col_concepto] = 'Concepto'
    if col_importe: nuevas_cols[col_importe] = 'Importe'
    
    if nuevas_cols:
        print(f"✅ Mapeo detectado: {nuevas_cols}")
        df.rename(columns=nuevas_cols, inplace=True)
    else:
        # Si falla, imprimimos qué columnas había para depurar
        print(f"⚠️ No se pudo normalizar automáticamente. Columnas encontradas: {cols}")

    # 4. LIMPIEZA DE DATOS (Vital para que no falle SQL)
    # Aseguramos que solo devolvemos las columnas que nos interesan
    cols_finales = ['Fecha', 'Concepto', 'Importe']
    for c in cols_finales:
        if c not in df.columns:
            df[c] = None # Rellenar con vacío si falta alguna columna no crítica
            
    return df[cols_finales]

def leer_banco(archivo_stream):
    """Función principal de lectura"""
    print(f"📊 Procesando archivo inteligente: {archivo_stream.name}...")
    df = None

    try:
        nombre = archivo_stream.name.lower()
        
        if nombre.endswith('.csv'):
            try:
                df = pd.read_csv(archivo_stream)
                if len(df.columns) < 2: 
                    archivo_stream.seek(0)
                    df = pd.read_csv(archivo_stream, sep=';')
            except:
                archivo_stream.seek(0)
                df = pd.read_csv(archivo_stream, sep=';', on_bad_lines='skip')
                
        elif nombre.endswith(('.xls', '.xlsx')):
            df = pd.read_excel(archivo_stream)

        if df is not None:
            # APLICAMOS LA INTELIGENCIA AQUÍ
            df = normalizar_datos(df)
            
            # Formateo final de tipos
            if 'Fecha' in df.columns:
                df['Fecha'] = pd.to_datetime(df['Fecha'], dayfirst=True, errors='coerce')
            
            # Limpieza de importe (convertir "-1.200,50 €" a número)
            if 'Importe' in df.columns:
                 # Si es string, limpiamos símbolos
                if df['Importe'].dtype == object:
                    df['Importe'] = df['Importe'].astype(str).str.replace('€', '').str.replace('.', '').str.replace(',', '.')
                df['Importe'] = pd.to_numeric(df['Importe'], errors='coerce').fillna(0)

        return df

    except Exception as e:
        print(f"❌ Error leyendo banco: {e}")
        return None