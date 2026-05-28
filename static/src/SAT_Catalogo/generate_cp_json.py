import xlrd
import json
import os
from odoo.modules.module import get_resource_path

# --- CONFIGURACIÓN DE RUTAS DINÁMICAS ---
# Definimos el nombre de tu módulo y las rutas relativas dentro de él
module_name = 'contabilidad_kuale'
rel_excel_path = 'static/src/SAT_Catalogo/catCFDI_V_4_20260302.xls'
rel_json_path = 'static/src/SAT_Catalogo/cp_data.json'

# Buscamos la ruta absoluta en el sistema de archivos actual
excel_path = get_resource_path(module_name, rel_excel_path)
json_path = get_resource_path(module_name, rel_json_path)

if not excel_path:
    raise FileNotFoundError(f"No se pudo encontrar el archivo Excel en el módulo: {module_name}")

# --- PROCESAMIENTO DEL EXCEL ---
wb = xlrd.open_workbook(excel_path)

# Estados
estados = {}
ws = wb.sheet_by_name('c_EstadoClave')
for i in range(1, ws.nrows):
    row = ws.row_values(i)
    try:
        if row[0] and row[2]:
            estados[row[0]] = row[2]
    except (ValueError, TypeError, IndexError):
        continue

# Municipios
municipios = {}
ws = wb.sheet_by_name('C_Municipio')
for i in range(1, ws.nrows):
    row = ws.row_values(i)
    try:
        if row[0] and row[1]:
            # Formateamos la llave como Estado-Municipio (ej. MEX-001)
            key = f"{row[1]}-{str(int(float(row[0]))).zfill(3)}"
            municipios[key] = row[2]
    except (ValueError, TypeError, IndexError):
        continue

# Colonias
colonias = {}
for sheet_name in ['C_Colonia_1', 'C_Colonia_2', 'C_Colonia_3']:
    try:
        ws = wb.sheet_by_name(sheet_name)
    except:
        continue
    for i in range(1, ws.nrows):
        row = ws.row_values(i)
        try:
            if row[1] and row[2]:
                cp = str(int(float(row[1]))).zfill(5)
                if cp not in colonias:
                    colonias[cp] = []
                colonias[cp].append(row[2])
        except (ValueError, TypeError, IndexError):
            continue

# Códigos Postales (CPs)
cp_dict = {}
for sheet_name in ['c_CodigoPostal_Parte_1', 'c_CodigoPostal_Parte_2']:
    try:
        ws = wb.sheet_by_name(sheet_name)
    except:
        continue
    for i in range(1, ws.nrows):
        row = ws.row_values(i)
        try:
            if not row[0]:
                continue
            cp           = str(int(float(row[0]))).zfill(5)
            clave_estado = row[1]
            clave_mun    = str(int(float(row[2]))).zfill(3)
            key_mun      = f"{clave_estado}-{clave_mun}"

            if cp not in cp_dict:
                cp_dict[cp] = {
                    'estado':    estados.get(clave_estado, ''),
                    'municipio': municipios.get(key_mun, ''),
                    'colonias':  colonias.get(cp, []),
                }
        except (ValueError, TypeError, IndexError):
            continue

# --- EXPORTACIÓN A JSON ---
if not json_path:
    json_path = os.path.join(os.path.dirname(excel_path), 'cp_data.json')

with open(json_path, 'w', encoding='utf-8') as f:
    json.dump(cp_dict, f, ensure_ascii=False, indent=4)

print(f" Proceso completado con éxito.")
print(f" Archivo generado en: {json_path}")
print(f" Total de CPs exportados: {len(cp_dict)}")
