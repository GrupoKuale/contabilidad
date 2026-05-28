# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError
from datetime import datetime
import logging
import base64
import io

_logger = logging.getLogger(__name__)

class BBVAXLSXStatementImporter(models.TransientModel):
    _name = 'bbva.xlsx.statement.importer'
    _description = 'Importador XLSX BBVA (Formato Excel Corregido)'

    data_file = fields.Binary(string='Archivo XLSX', required=True)
    filename = fields.Char(string='Nombre del Archivo')
    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda del Extracto',
        required=True,
        default=lambda self: self.env.company.currency_id,  # Por defecto MXN de la compañía
        help='Seleccione la moneda en la que están los montos del extracto'
    )
    numero_cuenta = fields.Char(string='Número de Cuenta (Opcional)',
                                help='Si se especifica, solo se importarán movimientos de esta cuenta')
    sheet_name = fields.Char(string='Nombre de Hoja', default='Hoja1',
                            help='Nombre de la hoja de Excel a importar')
    skip_rows = fields.Integer(string='Saltar Filas Iniciales', default=0,
                              help='Número de filas a saltar al inicio')
    has_headers = fields.Boolean(string='Archivo tiene Headers', default=False,
                                help='Marcar si el archivo tiene fila de encabezados')

    def _parse_bbva_date(self, date_value):
        """
        Parsea fechas de BBVA XLSX con manejo robusto
        """
        if not date_value or str(date_value).strip() == '' or str(date_value) == 'nan':
            return None

        # Si ya es un objeto datetime de pandas/excel
        if hasattr(date_value, 'date'):
            return date_value.date()

        # Si es string
        if isinstance(date_value, str):
            date_clean = date_value.strip()

            # Formato YYYY-MM-DD típico
            try:
                return datetime.strptime(date_clean, '%Y-%m-%d').date()
            except ValueError:
                pass

            # Otros formatos posibles
            formats = ['%d/%m/%Y', '%d-%m-%Y', '%Y/%m/%d', '%m/%d/%Y']
            for fmt in formats:
                try:
                    return datetime.strptime(date_clean, fmt).date()
                except ValueError:
                    continue

        # Si es numérico (número de serie de Excel)
        elif isinstance(date_value, (int, float)):
            try:
                # Convertir número de serie de Excel a fecha
                from datetime import date, timedelta
                excel_epoch = date(1899, 12, 30)  # Época de Excel
                return excel_epoch + timedelta(days=int(date_value))
            except:
                pass

        _logger.error(f" No se pudo parsear fecha BBVA: '{date_value}' (tipo: {type(date_value)})")
        return None

    def _parse_bbva_amount(self, amount_value):
        """
        Parsea importes de BBVA XLSX con manejo robusto
        """
        if amount_value is None or str(amount_value) == 'nan' or str(amount_value).strip() == '':
            return 0.0

        try:
            # Si ya es numérico
            if isinstance(amount_value, (int, float)):
                return float(amount_value)

            # Si es string, limpiar
            if isinstance(amount_value, str):
                clean_amount = amount_value.strip().replace(',', '').replace('$', '')
                if clean_amount and clean_amount != 'nan':
                    return float(clean_amount)

            return 0.0

        except (ValueError, TypeError):
            _logger.warning(f"No se pudo convertir importe BBVA: '{amount_value}' (tipo: {type(amount_value)})")
            return 0.0

    def _detect_bbva_structure_intelligent(self, df):
        """
        Detecta estructura de BBVA de manera inteligente por POSICIÓN y TIPO DE DATO
        """
        structure_info = {
            'column_mapping': {},
            'detected_pattern': 'unknown'
        }

        _logger.info(f" Analizando estructura DataFrame: {df.shape}")
        _logger.info(f" Tipos de datos por columna: {df.dtypes.to_dict()}")

        # Analizar las primeras filas para detectar el patrón
        if len(df) > 0:
            first_row = df.iloc[0]
            _logger.info(f" Primera fila de datos: {first_row.tolist()}")

            # PATRÓN BBVA TÍPICO: [índice, fecha, descripción, cargo, abono, saldo]
            # Detectar por TIPO DE DATO y POSICIÓN

            for col_idx, (col_name, value) in enumerate(first_row.items()):
                col_type = df.dtypes[col_name]
                _logger.debug(f"  Col {col_idx} '{col_name}': {value} (tipo: {col_type})")

                # Columna 0: generalmente índice (int)
                if col_idx == 0 and (col_type == 'int64' or col_type == 'float64'):
                    structure_info['column_mapping']['indice'] = col_name
                    _logger.info(f" Columna índice detectada: {col_name}")

                # Columna 1: fecha (datetime o object que parece fecha)
                elif col_idx == 1:
                    if 'datetime' in str(col_type) or self._looks_like_date(value):
                        structure_info['column_mapping']['fecha'] = col_name
                        _logger.info(f" Columna fecha detectada: {col_name} (valor: {value})")

                # Columna 2: descripción (object/string)
                elif col_idx == 2 and col_type == 'object':
                    structure_info['column_mapping']['descripcion'] = col_name
                    _logger.info(f" Columna descripción detectada: {col_name}")

                # Columna 3: cargo (numeric, puede estar vacío)
                elif col_idx == 3 and col_type in ['float64', 'int64', 'object']:
                    structure_info['column_mapping']['cargo'] = col_name
                    _logger.info(f" Columna cargo detectada: {col_name}")

                # Columna 4: abono (numeric, puede estar vacío)
                elif col_idx == 4 and col_type in ['float64', 'int64', 'object']:
                    structure_info['column_mapping']['abono'] = col_name
                    _logger.info(f" Columna abono detectada: {col_name}")

                # Columna 5: saldo (numeric)
                elif col_idx == 5 and col_type in ['float64', 'int64']:
                    structure_info['column_mapping']['saldo'] = col_name
                    _logger.info(f" Columna saldo detectada: {col_name}")

        # Verificar que se detectaron las columnas esenciales
        required_cols = ['fecha', 'descripcion']
        detected_cols = list(structure_info['column_mapping'].keys())

        if all(req in detected_cols for req in required_cols):
            structure_info['detected_pattern'] = 'bbva_standard'
            _logger.info(" Patrón BBVA estándar detectado correctamente")
        else:
            structure_info['detected_pattern'] = 'unknown'
            _logger.warning(f" Patrón no reconocido. Detectado: {detected_cols}")

        return structure_info

    def _looks_like_date(self, value):
        """
        Verifica si un valor parece ser una fecha
        """
        if hasattr(value, 'date'):  # datetime object
            return True

        if isinstance(value, str):
            # Buscar patrones de fecha
            import re
            if re.match(r'\d{4}-\d{2}-\d{2}', value) or re.match(r'\d{2}/\d{2}/\d{4}', value):
                return True

        return False

    def parse_bbva_xlsx(self, file_data):
        """
        Parser MEJORADO para XLSX de BBVA sin headers fijos
        """
        try:
            import pandas as pd
        except ImportError:
            raise UserError('Se requiere pandas: pip install pandas openpyxl')

        try:
            # LEER SIN HEADERS para evitar confusión
            excel_file = io.BytesIO(file_data)

            # Intentar diferentes estrategias de lectura
            df = None

            if self.has_headers:
                # Si el usuario confirma que hay headers
                df = pd.read_excel(excel_file, sheet_name=self.sheet_name,
                                 skiprows=self.skip_rows, header=0)
            else:
                # Leer sin asumir headers (más seguro)
                df = pd.read_excel(excel_file, sheet_name=self.sheet_name,
                                 skiprows=self.skip_rows, header=None)

                # Asignar nombres genéricos a las columnas
                column_names = [f'col_{i}' for i in range(len(df.columns))]
                df.columns = column_names

            _logger.info(f" BBVA Excel leído: {len(df)} filas, {len(df.columns)} columnas")
            _logger.info(f" Columnas asignadas: {list(df.columns)}")
            _logger.info(f"📋 Primera fila: {df.iloc[0].tolist() if len(df) > 0 else 'Sin datos'}")

            # Detectar estructura inteligentemente
            structure = self._detect_bbva_structure_intelligent(df)

            if structure['detected_pattern'] == 'unknown':
                raise UserError(
                    'No se pudo detectar el formato BBVA automáticamente. '
                    'Verifique que el archivo sea un extracto de BBVA válido.'
                )

            column_mapping = structure['column_mapping']
            parsed_records = []

            for index, row in df.iterrows():
                try:
                    record_data = {}

                    # ===== FECHA (OBLIGATORIA) =====
                    if 'fecha' not in column_mapping:
                        _logger.error(" No se detectó columna de fecha")
                        continue

                    fecha_col = column_mapping['fecha']
                    fecha = self._parse_bbva_date(row[fecha_col])
                    if not fecha:
                        _logger.debug(f" Fila {index}: Fecha inválida, saltando")
                        continue
                    record_data['fecha_movimiento'] = fecha

                    # ===== DESCRIPCIÓN =====
                    if 'descripcion' in column_mapping:
                        desc_col = column_mapping['descripcion']
                        if not pd.isna(row[desc_col]):
                            descripcion = str(row[desc_col]).strip()
                            record_data['descripcion'] = descripcion[:255]
                        else:
                            record_data['descripcion'] = ''
                    else:
                        record_data['descripcion'] = ''

                    # ===== PROCESAR IMPORTES =====
                    cargo = 0.0
                    abono = 0.0

                    if 'cargo' in column_mapping:
                        cargo_col = column_mapping['cargo']
                        if not pd.isna(row[cargo_col]):
                            cargo = self._parse_bbva_amount(row[cargo_col])

                    if 'abono' in column_mapping:
                        abono_col = column_mapping['abono']
                        if not pd.isna(row[abono_col]):
                            abono = self._parse_bbva_amount(row[abono_col])

                    # Determinar signo e importe
                    if cargo > 0:
                        record_data['signo'] = '-'
                        record_data['importe'] = cargo
                    elif abono > 0:
                        record_data['signo'] = '+'
                        record_data['importe'] = abono
                    else:
                        _logger.debug(f" Fila {index}: Sin importe válido, saltando")
                        continue

                    # ===== SALDO =====
                    if 'saldo' in column_mapping:
                        saldo_col = column_mapping['saldo']
                        if not pd.isna(row[saldo_col]):
                            record_data['saldo'] = self._parse_bbva_amount(row[saldo_col])
                        else:
                            record_data['saldo'] = 0.0
                    else:
                        record_data['saldo'] = 0.0

                    # ===== CAMPOS DEL MODELO =====
                    record_data.update({
                        'currency_id': self.currency_id.id,
                        'numero_cuenta': self.numero_cuenta or '',
                        'hora_movimiento': '0000',
                        'sucursal': '',
                        'referencia': '',
                        'clacon': '',
                        'concepto': record_data['descripcion'][:50],
                        'informacion_adicional': f'BBVA Excel - {self.filename or "extracto.xlsx"}',
                        'codigo_devolucion': '',
                        'causa_devolucion': '',
                        'formato_origen': 'original',
                        'campo_afil': '',
                        'clave_rastreo': '',
                        'banco_participante': 'BBVA',
                        'cuenta_ordenante': '',
                        'nombre_beneficiario': '',
                        'nombre_ordenante': '',
                        'clabe_beneficiario': '',
                        'rfc_receptor': '',
                        'rfc_ordenante': '',
                    })

                    # Metadatos
                    record_data.update({
                        'archivo_origen': self.filename or 'bbva_extracto.xlsx',
                        'fecha_importacion': fields.Datetime.now(),
                        'procesado': 'pendiente',
                    })

                    _logger.debug(f" Fila {index}: {fecha} | {record_data['signo']}{record_data['importe']}")
                    parsed_records.append(record_data)

                except Exception as e:
                    _logger.error(f" Error fila {index}: {str(e)}")
                    continue

            _logger.info(f" Total registros BBVA parseados: {len(parsed_records)}")

            return parsed_records, {
                'total_rows': len(df),
                'columns': list(df.columns),
                'column_mapping': column_mapping,
                'detected_pattern': structure['detected_pattern']
            }

        except Exception as e:
            raise UserError(f'Error al procesar Excel BBVA: {str(e)}')

    def action_import_statements(self):
        """
        Importación BBVA con MANEJO CORRECTO DE TRANSACCIONES ABORTADAS
        """
        if not self.data_file:
            raise UserError('Debe seleccionar un archivo Excel (.xlsx).')

        file_data = base64.b64decode(self.data_file)

        try:
            parsed_records, file_info = self.parse_bbva_xlsx(file_data)
        except Exception as e:
            raise UserError(f'Error al parsear BBVA: {str(e)}')

        if not parsed_records:
            raise UserError('No se encontraron registros válidos en el archivo BBVA.')

        BankStatement = self.env['santander.bank.statement']

        imported_count = 0
        skipped_count = 0
        errors = []

        _logger.info(f" === IMPORTANDO {len(parsed_records)} REGISTROS BBVA CON MANEJO DE TRANSACCIONES ===")

        # PROCESAR CADA REGISTRO EN SU PROPIA TRANSACCIÓN
        for i, record_data in enumerate(parsed_records, 1):
            # CREAR NUEVO CURSOR PARA CADA REGISTRO (TRANSACCIÓN INDEPENDIENTE)
            with self.env.registry.cursor() as new_cr:
                try:
                    # Crear nuevo environment con el cursor limpio
                    new_env = self.env(cr=new_cr)
                    BankStatementNew = new_env['santander.bank.statement']

                    # Filtrar por cuenta si se especifica
                    if self.numero_cuenta and record_data['numero_cuenta'] != self.numero_cuenta:
                        continue

                    # VERIFICACIÓN DE DUPLICADOS con el nuevo cursor
                    existing = BankStatementNew.search([
                        ('fecha_movimiento', '=', record_data['fecha_movimiento']),
                        ('importe', '=', record_data['importe']),
                        ('descripcion', '=', record_data['descripcion']),
                        ('saldo', '=', record_data['saldo']),
                        ('signo', '=', record_data['signo']),
                    ], limit=1)

                    if not existing:
                        # CREAR REGISTRO en transacción limpia
                        new_record = BankStatementNew.create(record_data)

                        # COMMIT inmediato de esta transacción
                        new_cr.commit()

                        imported_count += 1

                        if i % 10 == 0 or i <= 5:
                            _logger.info(f" BBVA creado {i}/{len(parsed_records)}: {record_data['fecha_movimiento']} | {record_data['signo']}{record_data['importe']}")
                    else:
                        skipped_count += 1

                        if skipped_count <= 5:
                            _logger.info(f" BBVA duplicado {i}: {record_data['fecha_movimiento']} | {record_data['signo']}{record_data['importe']} - YA EXISTE")

                except Exception as e:
                    # ROLLBACK automático al salir del contexto
                    error_msg = f'Error registro {i}: {str(e)}'
                    errors.append(error_msg)
                    _logger.error(f" BBVA INDIVIDUAL {error_msg}")
                    # La transacción se aborta automáticamente, no afecta las siguientes

        _logger.info(f"🏁 BBVA COMPLETADO CON TRANSACCIONES INDEPENDIENTES:")
        _logger.info(f"    Importados: {imported_count}")
        _logger.info(f"    Duplicados: {skipped_count}")
        _logger.info(f"    Errores: {len(errors)}")

        message = f'Importación BBVA Excel completada.\n'
        message += f'Registros NUEVOS importados: {imported_count}\n'
        message += f'Registros DUPLICADOS omitidos: {skipped_count}\n'
        message += f'Total procesados: {len(parsed_records)}\n'

        if imported_count > 0:
            message += f'\n {imported_count} registros guardados exitosamente'

        if skipped_count > 0:
            message += f'\n {skipped_count} registros ya existían (duplicados)'

        if errors and len(errors) <= 3:
            message += f'\nErrores: \n' + '\n'.join(errors[:3])
        elif errors:
            message += f'\nErrores: {len(errors)} (ver logs)'

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': ' BBVA Excel Procesado',
                'message': message,
                'type': 'success' if imported_count > 0 else 'info',
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            }
        }
