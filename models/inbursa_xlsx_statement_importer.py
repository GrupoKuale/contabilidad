# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError
from datetime import datetime
import logging
import base64
import io

_logger = logging.getLogger(__name__)

class InbursaXLSXStatementImporter(models.TransientModel):
    _name = 'inbursa.xlsx.statement.importer'
    _description = 'Importador XLSX Inbursa (Estado de Cuenta)'

    data_file = fields.Binary(string='Archivo XLSX', required=True)
    filename = fields.Char(string='Nombre del Archivo')

    #  Selector de moneda
    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda del Extracto',
        required=True,
        default=lambda self: self.env.company.currency_id,
        help='Seleccione la moneda del extracto (MXN por defecto)'
    )

    # Opciones de parseo
    sheet_name = fields.Char(
        string='Nombre de Hoja',
        default='PPTINBURSA',
        help='Nombre de la hoja de Excel a importar'
    )

    def _parse_inbursa_date(self, date_str):
        """Parsear fecha de Inbursa en formato DD/MM/YYYY"""
        if not date_str or str(date_str).strip() == '':
            return False

        try:
            date_str = str(date_str).strip()

            # Formato: DD/MM/YYYY
            if '/' in date_str:
                date_obj = datetime.strptime(date_str, '%d/%m/%Y')
                return date_obj.date()

            return False
        except Exception as e:
            _logger.error(f"Error parseando fecha Inbursa: '{date_str}' - {str(e)}")
            return False

    def _parse_inbursa_amount(self, amount_str):
        """Parsear monto de Inbursa"""
        if not amount_str or str(amount_str).strip() == '':
            return 0.0

        try:
            amount_str = str(amount_str).strip()
            # Eliminar espacios y convertir a float
            amount_str = amount_str.replace(' ', '').replace(',', '')
            return float(amount_str)
        except Exception as e:
            _logger.error(f"Error parseando monto Inbursa: '{amount_str}' - {str(e)}")
            return 0.0

    def parse_inbursa_xlsx(self, file_data):
        """Parser principal para extractos Inbursa XLSX"""
        try:
            import pandas as pd


            # Leer Excel
            df = pd.read_excel(
                io.BytesIO(file_data),
                sheet_name=self.sheet_name,
                header=None,
                dtype=str
            )

            _logger.info(f" Inbursa Excel leído: {len(df)} filas totales")

            #  EXTRAER METADATA DEL HEADER
            file_info = {}
            numero_cuenta = ''
            razon_social = ''
            tipo_cuenta = ''

            # Buscar información en las primeras filas
            for idx in range(min(10, len(df))):
                row_str = ' '.join([str(cell) for cell in df.iloc[idx].values if pd.notna(cell)])

                if 'Razón social:' in row_str or 'Razon social:' in row_str:
                    razon_social = row_str.split(':', 1)[1].strip() if ':' in row_str else ''
                    file_info['razon_social'] = razon_social

                if 'Cuenta:' in row_str:
                    numero_cuenta = row_str.split(':', 1)[1].strip() if ':' in row_str else ''
                    file_info['numero_cuenta'] = numero_cuenta

                if 'Tipo de cuenta:' in row_str:
                    tipo_cuenta = row_str.split(':', 1)[1].strip() if ':' in row_str else ''
                    file_info['tipo_cuenta'] = tipo_cuenta

            _logger.info(f" Cuenta detectada: {numero_cuenta}")
            _logger.info(f" Razón social: {razon_social}")

            #  ENCONTRAR FILA DE HEADERS
            header_row_index = None
            for idx, row in df.iterrows():
                row_values = [str(cell).strip().upper() for cell in row.values if pd.notna(cell)]

                # Buscar fila que contiene "FECHA" y "MOVIMIENTO"
                if any('FECHA' in val for val in row_values) and any('MOVIMIENTO' in val for val in row_values):
                    header_row_index = idx
                    _logger.info(f" Headers encontrados en fila {header_row_index}")
                    break

            if header_row_index is None:
                raise UserError('No se encontraron los headers del extracto Inbursa.')

            #  LEER DATOS CON HEADERS
            df_data = pd.read_excel(
                io.BytesIO(file_data),
                sheet_name=self.sheet_name,
                header=header_row_index,
                dtype=str
            )

            _logger.info(f" Filas de datos: {len(df_data)}")

            #  PARSEAR REGISTROS
            parsed_records = []

            for index, row in df_data.iterrows():
                try:
                    # Saltar filas vacías
                    if pd.isna(row.get('Fecha')) or str(row.get('Fecha')).strip() == '':
                        continue

                    # Saltar SALDO INICIAL
                    movimiento = str(row.get('Movimiento', '')).strip().upper()
                    if 'SALDO INICIAL' in movimiento:
                        continue

                    # Saltar TOTALES
                    if 'TOTALES' in movimiento or 'TOTAL' in movimiento:
                        continue

                    # Parsear fecha
                    fecha = self._parse_inbursa_date(row.get('Fecha'))
                    if not fecha:
                        _logger.warning(f" Fila {index}: Fecha inválida, omitiendo")
                        continue

                    # Parsear montos
                    cargo = self._parse_inbursa_amount(row.get('Cargo', 0))
                    abono = self._parse_inbursa_amount(row.get('Abono', 0))
                    saldo = self._parse_inbursa_amount(row.get('Saldo', 0))

                    # Determinar signo e importe
                    if abono > 0:
                        signo = '+'
                        importe = abono
                    elif cargo > 0:
                        signo = '-'
                        importe = cargo
                    else:
                        # Si ambos son 0, saltar
                        continue

                    # Obtener descripción y referencias
                    descripcion = str(row.get('Movimiento', '')).strip()
                    referencia = str(row.get('Referencia', '')).strip()
                    ref_externa = str(row.get('Ref. Externa', '')).strip()
                    ref_leyenda = str(row.get('Referencia Leyenda', '')).strip()
                    clave_rastreo = str(row.get('Clave de Rastreo', '')).strip()
                    ordenante = str(row.get('Ordenante', '')).strip()

                    # Construir referencia compuesta
                    referencias = [ref for ref in [referencia, ref_externa, ref_leyenda] if ref and ref != 'nan']
                    referencia_final = ' | '.join(referencias) if referencias else ''

                    #  CREAR REGISTRO
                    record_data = {
                        'fecha_movimiento': fecha,
                        'descripcion': descripcion[:500],  # Limitar longitud
                        'signo': signo,
                        'importe': abs(importe),
                        'saldo': saldo,
                        'referencia': referencia_final[:100],
                        'clave_rastreo': clave_rastreo[:100] if clave_rastreo != 'nan' else '',
                        'banco_participante': ordenante[:200] if ordenante != 'nan' else 'INBURSA',
                        'numero_cuenta': numero_cuenta,
                        'currency_id': self.currency_id.id,
                        'hora_movimiento': '0000',
                        'archivo_origen': self.filename or 'inbursa_extracto.xlsx',
                        'fecha_importacion': fields.Datetime.now(),
                        'procesado': 'pendiente',
                    }

                    parsed_records.append(record_data)

                except Exception as e:
                    _logger.error(f" Error en fila {index}: {str(e)}")
                    continue

            _logger.info(f" {len(parsed_records)} registros parseados exitosamente")

            return parsed_records, file_info

        except ImportError:
            raise UserError('El módulo pandas no está instalado. Instale con: pip install pandas openpyxl')
        except Exception as e:
            _logger.error(f" Error parseando Inbursa: {str(e)}")
            raise UserError(f'Error al parsear archivo Inbursa: {str(e)}')

    def action_import_statements(self):
        """Importar extractos de Inbursa"""
        if not self.data_file:
            raise UserError('Debe seleccionar un archivo Excel (.xlsx).')

        if not self.currency_id:
            raise UserError('Debe seleccionar la moneda del extracto.')

        file_data = base64.b64decode(self.data_file)

        try:
            parsed_records, file_info = self.parse_inbursa_xlsx(file_data)
        except Exception as e:
            raise UserError(f'Error al parsear Inbursa: {str(e)}')

        if not parsed_records:
            raise UserError('No se encontraron registros válidos en el archivo Inbursa.')

        BankStatement = self.env['santander.bank.statement']
        imported_count = 0
        skipped_count = 0
        errors = []

        currency_name = self.currency_id.name
        numero_cuenta = file_info.get('numero_cuenta', 'N/A')

        _logger.info(f" === IMPORTANDO {len(parsed_records)} REGISTROS INBURSA ===")
        _logger.info(f" Moneda: {currency_name}")
        _logger.info(f" Cuenta: {numero_cuenta}")

        for record_data in parsed_records:
            try:
                # Buscar duplicados
                existing = BankStatement.search([
                    ('fecha_movimiento', '=', record_data['fecha_movimiento']),
                    ('importe', '=', record_data['importe']),
                    ('descripcion', '=', record_data['descripcion']),
                    ('numero_cuenta', '=', record_data['numero_cuenta']),
                ], limit=1)

                if existing:
                    skipped_count += 1
                    _logger.debug(f" Duplicado: {record_data['fecha_movimiento']} - {record_data['descripcion']}")
                else:
                    BankStatement.create(record_data)
                    imported_count += 1
                    _logger.info(f" {record_data['fecha_movimiento']} - {record_data['descripcion'][:50]}")

            except Exception as e:
                error_msg = f"Fecha: {record_data.get('fecha_movimiento')} - Error: {str(e)}"
                errors.append(error_msg)
                _logger.error(f" {error_msg}")

        # Mensaje de resultado
        message = f' Importación Inbursa completada\n'
        message += f' Cuenta: {numero_cuenta}\n'
        message += f' Moneda: {self.currency_id.name} ({self.currency_id.symbol})\n'
        message += f' Registros NUEVOS importados: {imported_count}\n'
        message += f' Registros DUPLICADOS omitidos: {skipped_count}\n'
        message += f' Total procesados: {len(parsed_records)}\n'

        if errors:
            message += f'\n {len(errors)} errores encontrados (ver log)'

        _logger.info(f" Importación completada: {imported_count} nuevos, {skipped_count} duplicados")

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': f' Inbursa Procesado ({currency_name})',
                'message': message,
                'type': 'success' if imported_count > 0 else 'info',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            }
        }