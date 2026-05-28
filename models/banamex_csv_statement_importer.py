# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError
from datetime import datetime
import logging
import base64
import io
import re

_logger = logging.getLogger(__name__)

class BanamexCSVStatementImporter(models.TransientModel):
    _name = 'banamex.csv.statement.importer'
    _description = 'Importador CSV Banamex (Movimientos de Cuenta)'

    data_file = fields.Binary(string='Archivo CSV', required=True)
    filename = fields.Char(string='Nombre del Archivo')

    #  Selector de moneda
    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda del Extracto',
        required=True,
        default=lambda self: self.env.company.currency_id,
        help='Seleccione la moneda del extracto (MXN por defecto)'
    )

    def _parse_banamex_date(self, date_str):
        """Parsear fecha de Banamex en formato DD/MM/YYYY"""
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
            _logger.error(f"Error parseando fecha Banamex: '{date_str}' - {str(e)}")
            return False

    def _parse_banamex_amount(self, amount_str):
        """Parsear monto de Banamex (formato: 100,000.00)"""
        if not amount_str or str(amount_str).strip() == '':
            return 0.0

        try:
            amount_str = str(amount_str).strip()
            # Eliminar comillas si existen
            amount_str = amount_str.replace('"', '')
            # Eliminar comas de miles
            amount_str = amount_str.replace(',', '')
            # Eliminar espacios
            amount_str = amount_str.replace(' ', '')
            # Eliminar símbolo de pesos si existe
            amount_str = amount_str.replace('$', '')

            if amount_str == '':
                return 0.0

            return float(amount_str)
        except Exception as e:
            _logger.error(f"Error parseando monto Banamex: '{amount_str}' - {str(e)}")
            return 0.0

    def _extract_referencias_banamex(self, descripcion):
        """
        Extraer referencias de la descripción de Banamex
        Formato: "DESCRIPCION Referencia Númerica: XXX Autorización: YYY"
        """
        referencia = ''
        autorizacion = ''
        descripcion_limpia = descripcion

        try:
            # Extraer Referencia Numérica
            ref_match = re.search(r'Referencia Númerica:\s*([^\s]+(?:\s+[^\s]+)*?)(?:\s+Autorización|$)', descripcion, re.IGNORECASE)
            if ref_match:
                referencia = ref_match.group(1).strip()

            # Extraer Autorización
            auth_match = re.search(r'Autorización:\s*([^\s]+)', descripcion, re.IGNORECASE)
            if auth_match:
                autorizacion = auth_match.group(1).strip()

            # Limpiar descripción (quitar las referencias al final)
            descripcion_limpia = re.sub(r'Referencia Númerica:.*$', '', descripcion, flags=re.IGNORECASE)
            descripcion_limpia = descripcion_limpia.strip()

        except Exception as e:
            _logger.error(f"Error extrayendo referencias: {str(e)}")

        return descripcion_limpia, referencia, autorizacion

    def parse_banamex_csv(self, file_data):
        """Parser principal para extractos Banamex CSV"""
        try:
            import pandas as pd

            _logger.info(" ===  PARSEO BANAMEX ===")

            # Leer CSV completo
            df = pd.read_csv(
                io.BytesIO(file_data),
                header=None,
                dtype=str,
                encoding='latin-1',  # Banamex suele usar latin-1
                on_bad_lines='skip'
            )

            _logger.info(f" Banamex CSV leído: {len(df)} filas totales")

            # EXTRAER METADATA
            file_info = {}
            numero_cuenta = ''
            tipo_cuenta = ''
            sucursal = ''
            periodo = ''

            # Buscar número de cuenta y metadata en las primeras filas
            for idx in range(min(15, len(df))):
                row = df.iloc[idx]
                row_str = ' '.join([str(cell) for cell in row.values if pd.notna(cell)])

                # Buscar cuenta
                if 'Cuenta' in row_str:
                    for cell in row.values:
                        if pd.notna(cell) and str(cell).isdigit() and len(str(cell)) >= 4:
                            numero_cuenta = str(cell).strip()
                            file_info['numero_cuenta'] = numero_cuenta
                            break

                # Buscar tipo de cuenta
                if 'Tipo de cuenta' in row_str:
                    for cell in row.values:
                        if pd.notna(cell) and 'Cheques' in str(cell):
                            tipo_cuenta = str(cell).strip()
                            file_info['tipo_cuenta'] = tipo_cuenta

                # Buscar sucursal
                if 'Sucursal' in row_str:
                    for cell in row.values:
                        if pd.notna(cell) and str(cell).isdigit() and len(str(cell)) == 3:
                            sucursal = str(cell).strip()
                            file_info['sucursal'] = sucursal

            _logger.info(f" Cuenta detectada: {numero_cuenta}")
            _logger.info(f" Tipo de cuenta: {tipo_cuenta}")

            #  ENCONTRAR FILA DE HEADERS
            header_row_index = None
            for idx, row in df.iterrows():
                row_values = [str(cell).strip().upper() for cell in row.values if pd.notna(cell)]

                # Buscar fila que contiene "FECHA" y "DESCRIPCION"
                if any('FECHA' in val for val in row_values) and any('DESCRIPCION' in val or 'DESCRIPCIÓN' in val for val in row_values):
                    header_row_index = idx
                    _logger.info(f" Headers encontrados en fila {header_row_index}")
                    break

            if header_row_index is None:
                raise UserError('No se encontraron los headers del extracto Banamex.')

            #  LEER DATOS CON HEADERS
            df_data = pd.read_csv(
                io.BytesIO(file_data),
                header=header_row_index,
                dtype=str,
                encoding='latin-1',
                on_bad_lines='skip'
            )

            _logger.info(f" Filas de datos: {len(df_data)}")

            #  PARSEAR REGISTROS
            parsed_records = []

            for index, row in df_data.iterrows():
                try:
                    # Saltar filas vacías
                    if pd.isna(row.get('Fecha')) or str(row.get('Fecha')).strip() == '':
                        continue

                    # Parsear fecha
                    fecha = self._parse_banamex_date(row.get('Fecha'))
                    if not fecha:
                        _logger.warning(f" Fila {index}: Fecha inválida, omitiendo")
                        continue

                    # Parsear montos
                    depositos = self._parse_banamex_amount(row.get('Depósitos', 0))
                    retiros = self._parse_banamex_amount(row.get('Retiros', 0))
                    saldo = self._parse_banamex_amount(row.get('Saldo', 0))

                    # Determinar signo e importe
                    if depositos > 0:
                        signo = '+'
                        importe = depositos
                    elif retiros > 0:
                        signo = '-'
                        importe = retiros
                    else:
                        # Si ambos son 0, saltar
                        continue

                    # Obtener y procesar descripción
                    descripcion_raw = str(row.get('Descripción', '')).strip()

                    # Extraer referencias de la descripción
                    descripcion, referencia, autorizacion = self._extract_referencias_banamex(descripcion_raw)

                    #  CREAR REGISTRO
                    record_data = {
                        'fecha_movimiento': fecha,
                        'descripcion': descripcion[:500],  # Limitar longitud
                        'signo': signo,
                        'importe': abs(importe),
                        'saldo': saldo,
                        'referencia': referencia[:100] if referencia else '',
                        'clave_rastreo': autorizacion[:100] if autorizacion else '',
                        'banco_participante': 'BANAMEX',
                        'numero_cuenta': numero_cuenta,
                        'currency_id': self.currency_id.id,
                        'hora_movimiento': '0000',
                        'archivo_origen': self.filename or 'banamex_extracto.csv',
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
            raise UserError('El módulo pandas no está instalado. Instale con: pip install pandas')
        except Exception as e:
            _logger.error(f" Error parseando Banamex: {str(e)}")
            raise UserError(f'Error al parsear archivo Banamex: {str(e)}')

    def action_import_statements(self):
        """Importar extractos de Banamex"""
        if not self.data_file:
            raise UserError('Debe seleccionar un archivo CSV.')

        if not self.currency_id:
            raise UserError('Debe seleccionar la moneda del extracto.')

        file_data = base64.b64decode(self.data_file)

        try:
            parsed_records, file_info = self.parse_banamex_csv(file_data)
        except Exception as e:
            raise UserError(f'Error al parsear Banamex: {str(e)}')

        if not parsed_records:
            raise UserError('No se encontraron registros válidos en el archivo Banamex.')

        BankStatement = self.env['santander.bank.statement']
        imported_count = 0
        skipped_count = 0
        errors = []

        currency_name = self.currency_id.name
        numero_cuenta = file_info.get('numero_cuenta', 'N/A')

        _logger.info(f" === IMPORTANDO {len(parsed_records)} REGISTROS BANAMEX ===")
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
        message = f' Importación Banamex completada\n'
        message += f' Cuenta: {numero_cuenta}\n'
        message += f' Moneda: {self.currency_id.name} ({self.currency_id.symbol})\n'
        message += f' Registros NUEVOS importados: {imported_count}\n'
        message += f' Registros DUPLICADOS omitidos: {skipped_count}\n'
        message += f' Total procesados: {len(parsed_records)}\n'

        if errors:
            message += f'\n {len(errors)} errores encontrados (ver log)'

        _logger.info(f"🏁 Importación completada: {imported_count} nuevos, {skipped_count} duplicados")

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': f' Banamex Procesado ({currency_name})',
                'message': message,
                'type': 'success' if imported_count > 0 else 'info',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            }
        }