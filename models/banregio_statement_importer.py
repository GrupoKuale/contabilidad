# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError
from datetime import datetime
import logging
import csv
import re
from io import StringIO

_logger = logging.getLogger(__name__)


class BanregioStatementImporter(models.TransientModel):
    _name = 'banregio.statement.importer'
    _description = 'Importador de Extractos Banregio (CSV)'

    data_file = fields.Binary(string='Archivo CSV', required=True)
    filename = fields.Char(string='Nombre del Archivo')
    numero_cuenta = fields.Char(string='Número de Cuenta (Opcional)',
                                help='Si se especifica, solo se importarán movimientos de esta cuenta')
    skip_initial_balance = fields.Boolean(string='Omitir Saldo Inicial', default=True,
                                          help='No importar la línea de saldo inicial')

    def _extract_account_info_from_header(self, content_lines):
        """Extrae información de la cuenta del header del CSV"""
        account_info = {}

        for line in content_lines[:10]:
            line_clean = line.strip()

            # Buscar número de cuenta
            if 'CUENTA:' in line_clean.upper():
                match = re.search(r'CUENTA:\s*(\d+)', line_clean)
                if match:
                    account_info['numero_cuenta'] = match.group(1)

            # Buscar CLABE
            elif 'CLABE:' in line_clean.upper():
                match = re.search(r'CLABE:\s*(\d+)', line_clean)
                if match:
                    account_info['clabe'] = match.group(1)

            # Buscar RFC
            elif 'RFC:' in line_clean.upper():
                match = re.search(r'RFC:\s*([A-Z0-9]+)', line_clean)
                if match:
                    account_info['rfc'] = match.group(1).strip()

            # Buscar nombre de la empresa
            elif any(word in line_clean.upper() for word in ['S.A.', 'S. DE', 'DE C.V.']):
                clean_name = re.sub(r'^[,\s]*', '', line_clean)
                if clean_name and len(clean_name) > 5:
                    account_info['empresa'] = clean_name.split(',')[0].strip()  # Solo la primera parte

        return account_info

    def _parse_banregio_amount(self, amount_str):
        """Parsea los importes de Banregio que tienen formato '$31,550.00'"""
        if not amount_str or amount_str.strip() == '':
            return 0.0

        clean_amount = amount_str.replace('"', '').replace('$', '').replace(',', '').strip()

        try:
            return float(clean_amount)
        except ValueError:
            _logger.warning(f"No se pudo convertir importe: '{amount_str}' → '{clean_amount}'")
            return 0.0

    def _parse_banregio_date(self, date_str):
        """Parsea fechas de Banregio en formato DD/MM/YYYY"""
        if not date_str or date_str.strip() == '':
            return None

        try:
            return datetime.strptime(date_str.strip(), '%d/%m/%Y').date()
        except ValueError:
            _logger.error(f"Error al parsear fecha: '{date_str}'")
            return None

    def _extract_spei_info_from_description(self, descripcion):
        """Extrae información SPEI básica de la descripción para campos existentes"""
        info = {}

        if not descripcion or 'SPEI' not in descripcion.upper():
            return info

        # Dividir por puntos para analizar
        partes = descripcion.split('.')

        for i, parte in enumerate(partes):
            parte_clean = parte.strip()

            # Banco participante (normalmente después de "SPEI")
            if i == 1 and 'SPEI' not in parte_clean:
                info['banco_participante'] = parte_clean[:50]  # Limitar longitud

            # CLABE (18 dígitos) - usar como cuenta_ordenante (campo existente)
            elif re.match(r'^\d{18}$', parte_clean):
                info['cuenta_ordenante'] = parte_clean

            # Empresas/nombres - usar campos existentes
            elif any(word in parte_clean.upper() for word in ['SA DE CV', 'SOFOM', 'SA CV', 'S DE RL']):
                if not info.get('nombre_beneficiario'):
                    info['nombre_beneficiario'] = parte_clean[:100]
                elif not info.get('nombre_ordenante'):
                    info['nombre_ordenante'] = parte_clean[:100]

        return info

    def parse_banregio_csv(self, content):
        """Parser principal para CSV de Banregio - COMPATIBLE con modelo existente"""
        lines = content.split('\n')

        # Extraer información del header
        account_info = self._extract_account_info_from_header(lines)
        _logger.info(f" Información de cuenta: {account_info}")

        # Buscar header de columnas
        header_line_idx = None
        for i, line in enumerate(lines):
            if 'Fecha' in line and 'Descripción' in line and 'Cargo' in line and 'Abonos' in line:
                header_line_idx = i
                break

        if header_line_idx is None:
            raise UserError('No se encontró el header de columnas')

        _logger.info(f" Header en línea {header_line_idx + 1}")

        # Procesar datos
        data_lines = lines[header_line_idx:]
        csv_content = '\n'.join(data_lines)
        csv_reader = csv.DictReader(StringIO(csv_content))

        parsed_records = []
        line_num = header_line_idx + 1

        for row in csv_reader:
            line_num += 1

            if not row.get('Fecha') or row['Fecha'].strip() == '':
                continue

            # Saltar saldo inicial
            if self.skip_initial_balance and 'Saldo Inicial' in str(row.get('Descripción', '')):
                _logger.info(f" Saldo inicial omitido")
                continue

            try:
                record_data = {}

                # Número de cuenta del header o campo existente
                record_data['numero_cuenta'] = account_info.get('numero_cuenta', '')

                # Fecha
                fecha = self._parse_banregio_date(row.get('Fecha', ''))
                if not fecha:
                    continue
                record_data['fecha_movimiento'] = fecha

                # Descripción (campo existente, limitar longitud)
                descripcion = row.get('Descripción', '').strip()
                record_data['descripcion'] = descripcion[:255]  # Limitar para BD

                # Referencia
                referencia = row.get('Referencia', '').strip()
                if referencia and referencia != '_':
                    record_data['referencia'] = referencia.replace('_', '')[:50]
                else:
                    record_data['referencia'] = ''

                # ===== PROCESAR IMPORTES =====

                cargo = self._parse_banregio_amount(row.get('Cargo', ''))
                abono = self._parse_banregio_amount(row.get('Abonos', ''))
                saldo = self._parse_banregio_amount(row.get('Saldo', ''))

                if cargo > 0:
                    record_data['signo'] = '-'
                    record_data['importe'] = cargo
                elif abono > 0:
                    record_data['signo'] = '+'
                    record_data['importe'] = abono
                else:
                    record_data['signo'] = '+'
                    record_data['importe'] = 0.0

                record_data['saldo'] = saldo

                # ===== INFORMACIÓN ADICIONAL EN CAMPOS EXISTENTES =====

                # Extraer info SPEI usando campos existentes
                spei_info = self._extract_spei_info_from_description(descripcion)
                record_data.update(spei_info)

                # Usar concepto para tipo de operación
                if 'SPEI' in descripcion.upper():
                    record_data['concepto'] = 'SPEI - ' + descripcion[:45]
                elif 'TRASPASO' in descripcion.upper():
                    record_data['concepto'] = 'TRASPASO - ' + descripcion[:40]
                else:
                    record_data['concepto'] = descripcion[:50]

                # Usar informacion_adicional para datos específicos de Banregio
                banregio_info = []
                if account_info.get('empresa'):
                    banregio_info.append(f"Empresa: {account_info['empresa'][:30]}")
                if account_info.get('clabe'):
                    banregio_info.append(f"CLABE: {account_info['clabe']}")
                if row.get('Clasificación'):
                    banregio_info.append(f"Clasificación: {row['Clasificación'][:20]}")

                record_data['informacion_adicional'] = ' | '.join(banregio_info)[:255]

                # ===== CAMPOS REQUERIDOS CON VALORES POR DEFECTO =====

                record_data.update({
                    'hora_movimiento': '0000',
                    'sucursal': '',
                    'clacon': '',
                    'codigo_devolucion': '',
                    'causa_devolucion': '',
                    'formato_origen': 'extendido',
                    'campo_afil': '',
                    'clave_rastreo': '',
                })

                # ===== METADATOS =====

                record_data.update({
                    'archivo_origen': self.filename or 'banregio_extracto.csv',
                    'fecha_importacion': fields.Datetime.now(),
                    'procesado': 'pendiente',
                })

                _logger.info(f" Línea {line_num}: {fecha} | {record_data['signo']}{record_data['importe']}")
                parsed_records.append(record_data)

            except Exception as e:
                _logger.error(f" Error en línea {line_num}: {str(e)}")
                continue

        _logger.info(f" Total parseados: {len(parsed_records)}")
        return parsed_records, account_info

    def action_import_statements(self):
        """Acción principal de importación CON TRANSACCIONES INDEPENDIENTES"""
        if not self.data_file:
            raise UserError('Debe seleccionar un archivo CSV.')

        import base64
        file_data = base64.b64decode(self.data_file)

        try:
            content = None
            for encoding in ['utf-8', 'latin-1', 'cp1252']:
                try:
                    content = file_data.decode(encoding)
                    _logger.info(f"CSV decodificado con {encoding}")
                    break
                except UnicodeDecodeError:
                    continue

            if not content:
                raise UserError('No se pudo decodificar el archivo CSV.')

        except Exception as e:
            raise UserError(f'Error al leer el archivo: {str(e)}')

        # Parsear CSV
        try:
            parsed_records, account_info = self.parse_banregio_csv(content)
        except Exception as e:
            raise UserError(f'Error al parsear CSV: {str(e)}')

        if not parsed_records:
            raise UserError('No se encontraron registros válidos.')

        # ===== CONTADORES =====
        imported_count = 0
        duplicate_count = 0
        error_count = 0
        skipped_count = 0

        _logger.info(f"=== IMPORTANDO {len(parsed_records)} REGISTROS BANREGIO ===")

        # ===== IMPORTACIÓN INDEPENDIENTES =====
        for i, record_data in enumerate(parsed_records, 1):
            # Filtro por cuenta (antes de crear transacción)
            if self.numero_cuenta and record_data.get('numero_cuenta') != self.numero_cuenta:
                skipped_count += 1
                continue

            # Cursor independiente para cada registro
            with self.env.registry.cursor() as new_cr:
                try:
                    # Crear nuevo entorno con el cursor independiente
                    new_env = self.env(cr=new_cr)
                    BankStatementNew = new_env['santander.bank.statement']

                    # Crear registro directamente (sin verificación previa)
                    new_record = BankStatementNew.create(record_data)

                    # COMMIT inmediato de esta transacción
                    new_cr.commit()

                    imported_count += 1
                    _logger.info(
                        f"BANREGIO {i}/{len(parsed_records)}: Creado ID {new_record.id} - {record_data.get('fecha_movimiento')} | {record_data.get('signo', '')}{record_data.get('importe', 0)}")

                except Exception as e:
                    # Rollback automático de esta transacción
                    new_cr.rollback()

                    error_str = str(e).lower()

                    # Detectar duplicados por constraint único
                    if 'duplicate' in error_str or 'unique' in error_str or 'already exists' in error_str:
                        duplicate_count += 1
                        _logger.info(
                            f"BANREGIO {i}/{len(parsed_records)}: Duplicado - {record_data.get('fecha_movimiento')} | {record_data.get('importe', 0)}")
                    else:
                        error_count += 1
                        _logger.error(f"BANREGIO {i}/{len(parsed_records)}: Error - {str(e)}")

        # ===== LOGS FINALES =====
        _logger.info(f"=== BANREGIO COMPLETADO ===")
        _logger.info(f"Importados: {imported_count}")
        _logger.info(f"Duplicados: {duplicate_count}")
        _logger.info(f"Errores: {error_count}")
        _logger.info(f"Omitidos (filtro cuenta): {skipped_count}")

        # ===== MENSAJE AL USUARIO =====
        message = f'Importación Banregio completada\n\n'
        message += f'Cuenta: {account_info.get("numero_cuenta", "No detectada")}\n'
        message += f'Empresa: {account_info.get("empresa", "No detectada")}\n'
        message += f'Total procesados: {len(parsed_records)}\n\n'
        message += f'Registros importados: {imported_count}\n'
        message += f'Duplicados omitidos: {duplicate_count}\n'

        if skipped_count > 0:
            message += f'Omitidos (filtro): {skipped_count}\n'

        if error_count > 0:
            message += f'Errores: {error_count} (revisar logs)\n'

        # Determinar tipo de notificación
        if imported_count > 0:
            notification_type = 'success'
        elif duplicate_count > 0 and error_count == 0:
            notification_type = 'info'
            message += '\nTodos los registros ya existían en la base de datos.'
        else:
            notification_type = 'warning'

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Importación Banregio Completada',
                'message': message,
                'type': notification_type,
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }
