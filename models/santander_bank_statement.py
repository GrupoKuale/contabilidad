# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError
from datetime import datetime
import logging
import csv
import re
from io import StringIO

_logger = logging.getLogger(__name__)

class SantanderBankStatement(models.Model):
    _name = 'santander.bank.statement'
    _description = 'Extracto Bancario Santander'
    _order = 'fecha_movimiento desc, hora_movimiento desc'

    # Campos principales (originales)
    numero_cuenta = fields.Char(string='Número de Cuenta', size=16, required=True)
    fecha_movimiento = fields.Date(string='Fecha del Movimiento', required=True)
    hora_movimiento = fields.Char(string='Hora del Movimiento', size=4)
    sucursal = fields.Char(string='Sucursal', size=4)
    clacon = fields.Char(string='Clacon', size=4)
    descripcion = fields.Char(string='Descripción', size=40)
    signo = fields.Selection([
        ('+', 'Abono'),
        ('-', 'Cargo')
    ], string='Signo del Movimiento', required=True)
    importe = fields.Float(string='Importe', digits=(14, 2), required=True)
    saldo = fields.Float(string='Saldo', digits=(14, 2), required=True)
    referencia = fields.Char(string='Referencia', size=8)

    campo_afil = fields.Char(string='Campo AFIL (Formato Original)', size=50,
                            help='Campo que inicia con AFIL - Solo formato original')

    concepto = fields.Char(string='Concepto', size=40,
                          help='Datos adicionales de la operación / Concepto')

    informacion_adicional = fields.Char(string='Información Adicional', size=50,
                                       help='Información adicional que viene de Captación')

    banco_participante = fields.Char(string='Banco Participante', size=40,
                                    help='Nombre del banco receptor o emisor del pago')

    clabe_beneficiario = fields.Char(string='CLABE Beneficiario', size=20,
                                    help='Cuenta CLABE del beneficiario')

    nombre_beneficiario = fields.Char(string='Nombre Beneficiario', size=40,
                                     help='Nombre del beneficiario')

    cuenta_ordenante = fields.Char(string='Cuenta Ordenante', size=20,
                                  help='Cuenta CLABE de donde salió el pago')

    nombre_ordenante = fields.Char(string='Nombre Ordenante', size=40,
                                  help='Nombre del titular de donde salió el pago')

    codigo_devolucion = fields.Char(string='Código de Devolución', size=5,
                                   help='Código de devolución')

    causa_devolucion = fields.Char(string='Causa de Devolución', size=27,
                                  help='Descripción del código de devolución')

    rfc_receptor = fields.Char(string='RFC Receptor', size=15,
                              help='RFC de quien recibe el pago')

    rfc_ordenante = fields.Char(string='RFC Ordenante', size=15,
                               help='RFC de quien ordena el pago')

    clave_rastreo = fields.Char(string='Clave de Rastreo', size=30,
                               help='Clave de Rastreo')

    fecha_importacion = fields.Datetime(string='Fecha de Importación',
                                       default=fields.Datetime.now)
    archivo_origen = fields.Char(string='Archivo de Origen')
    procesado = fields.Selection([
        ('pendiente', 'Pendiente'),
        ('procesado', 'Procesado')
    ], string='Estado', default='pendiente', required=True)

    formato_origen = fields.Selection([
        ('original', 'Formato Original'),
        ('extendido', 'Formato Extendido (22 campos)')
    ], string='Formato de Origen', help='Formato del extracto de donde proviene este registro')

    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        default=lambda self: self.env.company.currency_id,
        required=True
    )

    descripcion_completa = fields.Text(string='Descripción Completa',
                                      compute='_compute_descripcion_completa',
                                      help='Descripción combinada con concepto e información adicional')

    es_spei = fields.Boolean(string='Es SPEI', compute='_compute_tipo_operacion',
                            help='Indica si es una transferencia SPEI')

    es_devolucion = fields.Boolean(string='Es Devolución', compute='_compute_tipo_operacion',
                                  help='Indica si es una devolución')

    currency_symbol = fields.Char(
        string='Símbolo',
        related='currency_id.symbol',
        readonly=True,
        store=False
    )

    @api.depends('descripcion', 'concepto', 'informacion_adicional')
    def _compute_descripcion_completa(self):
        """Combina descripción, concepto e información adicional para una vista completa"""
        for record in self:
            partes = []
            if record.descripcion:
                partes.append(record.descripcion.strip())
            if record.concepto:
                partes.append(record.concepto.strip())
            if record.informacion_adicional:
                partes.append(record.informacion_adicional.strip())

            record.descripcion_completa = ' | '.join([p for p in partes if p])

    @api.depends('descripcion', 'codigo_devolucion')
    def _compute_tipo_operacion(self):
        """Determina el tipo de operación basándose en la descripción y códigos"""
        for record in self:
            descripcion_upper = (record.descripcion or '').upper()

            # Detectar SPEI
            record.es_spei = 'SPEI' in descripcion_upper

            # Detectar devoluciones
            record.es_devolucion = bool(record.codigo_devolucion and record.codigo_devolucion.strip())

    # Restricción de unicidad actualizada para incluir más campos
    _sql_constraints = [
        ('unique_transaction_extended',
         'UNIQUE(numero_cuenta, fecha_movimiento, hora_movimiento, referencia, importe, clave_rastreo)',
         'Ya existe una transacción con los mismos datos.')
    ]

    def toggle_procesado(self):
        """Método para cambiar el estado de procesado del registro"""
        for record in self:
            if record.procesado == 'pendiente':
                record.procesado = 'procesado'
            else:
                record.procesado = 'pendiente'
        return True

    def action_view_related_documents(self):
        """Acción para ver documentos relacionados basándose en RFC o nombres"""
        self.ensure_one()

        # Buscar facturas relacionadas por RFC
        domain = []
        if self.rfc_receptor:
            domain.append(('partner_id.vat', 'ilike', self.rfc_receptor))
        elif self.rfc_ordenante:
            domain.append(('partner_id.vat', 'ilike', self.rfc_ordenante))
        elif self.nombre_beneficiario:
            domain.append(('partner_id.name', 'ilike', self.nombre_beneficiario))
        elif self.nombre_ordenante:
            domain.append(('partner_id.name', 'ilike', self.nombre_ordenante))

        if not domain:
            raise UserError('No hay información suficiente para buscar documentos relacionados.')

        return {
            'name': 'Documentos Relacionados',
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'tree,form',
            'domain': domain,
            'context': {'create': False}
        }

    @api.model
    def get_statistics_by_period(self, date_from, date_to):
        """Obtiene estadísticas de movimientos por período"""
        domain = [
            ('fecha_movimiento', '>=', date_from),
            ('fecha_movimiento', '<=', date_to)
        ]

        records = self.search(domain)

        return {
            'total_movimientos': len(records),
            'total_abonos': len(records.filtered(lambda r: r.signo == '+')),
            'total_cargos': len(records.filtered(lambda r: r.signo == '-')),
            'total_spei': len(records.filtered('es_spei')),
            'total_devoluciones': len(records.filtered('es_devolucion')),
            'suma_abonos': sum(records.filtered(lambda r: r.signo == '+').mapped('importe')),
            'suma_cargos': sum(records.filtered(lambda r: r.signo == '-').mapped('importe')),
            'bancos_participantes': list(set(records.mapped('banco_participante'))),
            'formatos_origen': records.read_group([], ['formato_origen'], ['formato_origen'])
        }

class SantanderBankStatementBanregioExtension(models.Model):
    _inherit = 'santander.bank.statement'

    # Campos específicos de Banregio
    clabe_cuenta = fields.Char(string='CLABE de la Cuenta', size=18,
                              help='CLABE de la cuenta donde se realizó el movimiento')

    empresa = fields.Char(string='Empresa Titular', size=100,
                         help='Nombre de la empresa titular de la cuenta')

    rfc_empresa = fields.Char(string='RFC Empresa Titular', size=13,
                             help='RFC de la empresa titular')

    clasificacion = fields.Char(string='Clasificación Banregio', size=50,
                               help='Clasificación del movimiento según Banregio')

    tipo_transferencia = fields.Selection([
        ('spei', 'SPEI'),
        ('traspaso', 'Traspaso'),
        ('cheque', 'Cheque'),
        ('comision', 'Comisión'),
        ('otros', 'Otros')
    ], string='Tipo de Transferencia', help='Tipo de transferencia detectado')

    # Sobrescribir el compute para incluir nuevos campos
    @api.depends('descripcion', 'concepto', 'informacion_adicional', 'tipo_transferencia')
    def _compute_tipo_operacion(self):
        """Determina el tipo de operación basándose en la descripción y campos Banregio"""
        for record in self:
            descripcion_upper = (record.descripcion or '').upper()

            # Detectar SPEI (ahora también basándose en tipo_transferencia)
            record.es_spei = ('SPEI' in descripcion_upper or record.tipo_transferencia == 'spei')

            # Detectar devoluciones
            record.es_devolucion = bool(record.codigo_devolucion and record.codigo_devolucion.strip())


class SantanderStatementImporter(models.TransientModel):
    _name = 'santander.statement.importer'
    _description = 'Importador de Extractos Santander'

    data_file = fields.Binary(string='Archivo TXT', required=True)
    filename = fields.Char(string='Nombre del Archivo')
    numero_cuenta = fields.Char(string='Número de Cuenta (Opcional)',
                                help='Si se especifica, solo se importarán movimientos de esta cuenta')
    formato_extracto = fields.Selection([
        ('formato_original', 'Formato Original (Posiciones fijas básicas)'),
        ('formato_extendido', 'Formato Extendido (22 campos con diccionario)'),
        ('auto', 'Detección Automática')
    ], string='Formato de Extracto', default='auto', required=True,
        help='Seleccione el formato del extracto o use detección automática')

    def _detect_format(self, line):
        """Detecta automáticamente el formato del extracto"""
        if not line or len(line) < 50:
            return None

        line_clean = line.strip().replace('\r', '').replace('\n', '')

        # Formato extendido: líneas largas (400+ caracteres)
        if len(line_clean) > 400:
            return 'formato_extendido'
        elif len(line_clean) < 200:
            return 'formato_original'
        else:
            return 'formato_extendido'

    def _extract_concept_intelligent(self, line, start_pos, max_length=41):
        """
        Extrae concepto de manera inteligente, incluyendo espacios iniciales
        pero parando en el primer número consecutivo
        """
        concept_section = line[start_pos:start_pos + max_length + 10]  # Buffer extra

        # Buscar el primer grupo de 4+ dígitos consecutivos para determinar fin
        match = re.search(r'\d{4,}', concept_section)

        if match:
            # El concepto termina antes del primer número significativo
            concept_end = start_pos + match.start()
            concept = line[start_pos:concept_end].strip()
        else:
            # Si no hay números, tomar la longitud máxima esperada
            concept = line[start_pos:start_pos + max_length].strip()

        return concept

    def parse_formato_extendido_correcto(self, line):
        """
        Parser DEFINITIVO basado en el desglose CORREGIDO proporcionado
        Usando indexación Python (posición - 1)
        """
        line_clean = line.strip().replace('\r', '').replace('\n', '')

        _logger.info(f" Parseando línea de {len(line_clean)} caracteres")

        if len(line_clean) < 440:
            _logger.warning(f" Línea posiblemente incompleta: {len(line_clean)} caracteres")

        try:
            data = {}

            data['numero_cuenta'] = line_clean[0:11].strip()
            _logger.info(f" Número cuenta: '{data['numero_cuenta']}'")

            fecha_str = line_clean[16:24].strip()
            _logger.info(f" Fecha raw: '{fecha_str}'")

            data['hora_movimiento'] = line_clean[24:28].strip()
            _logger.info(f" Hora: '{data['hora_movimiento']}'")

            data['sucursal'] = line_clean[28:32].strip()

            data['clacon'] = line_clean[32:36].strip()

            data['descripcion'] = line_clean[36:76].strip()
            _logger.info(f" Descripción: '{data['descripcion']}'")

            data['signo'] = line_clean[76:77].strip()
            _logger.info(f" Signo: '{data['signo']}'")

            importe_str = line_clean[77:91].strip()
            _logger.info(f" Importe raw: '{importe_str}' (longitud: {len(importe_str)})")

            saldo_str = line_clean[92:105].strip()
            _logger.info(f" Saldo raw: '{saldo_str}' (longitud: {len(saldo_str)})")

            data['referencia'] = line_clean[105:113].strip()
            _logger.info(f" Referencia: '{data['referencia']}'")

            data['concepto'] = self._extract_concept_intelligent(line_clean, 113, 41)
            _logger.info(f" Concepto: '{data['concepto']}'")

            data['informacion_adicional'] = line_clean[153:159].strip()

            data['cuenta_ordenante'] = line_clean[161:1179].strip()
            _logger.info(f" CLABE ordenante: '{data['cuenta_ordenante']}'")

            data['banco_participante'] = line_clean[203:214].strip()
            _logger.info(f" Banco: '{data['banco_participante']}'")

            data['clabe_beneficiario'] = line_clean[243:261].strip()
            _logger.info(f" CLABE beneficiario: '{data['clabe_beneficiario']}'")

            data['nombre_beneficiario'] = line_clean[263:285].strip()
            _logger.info(f" Nombre beneficiario: '{data['nombre_beneficiario']}'")

            data['nombre_ordenante'] = line_clean[323:355].strip()
            _logger.info(f" Nombre ordenante: '{data['nombre_ordenante']}'")

            data['rfc_receptor'] = line_clean[395:407].strip()
            _logger.info(f" RFC receptor: '{data['rfc_receptor']}'")

            data['rfc_ordenante'] = line_clean[410:422].strip()
            _logger.info(f" RFC ordenante: '{data['rfc_ordenante']}'")

            data['clave_rastreo'] = line_clean[425:442].strip()
            _logger.info(f" Clave rastreo: '{data['clave_rastreo']}'")

            # ===== PROCESAMIENTO DE DATOS =====

            # Procesar fecha ddMMYYYY
            if len(fecha_str) == 8 and fecha_str.isdigit():
                try:
                    dia = int(fecha_str[0:2])
                    mes = int(fecha_str[2:4])
                    año = int(fecha_str[4:8])
                    data['fecha_movimiento'] = datetime(año, mes, dia).date()
                    _logger.info(f" Fecha procesada: {data['fecha_movimiento']}")
                except ValueError as e:
                    _logger.error(f" Error al convertir fecha {fecha_str}: {str(e)}")
                    return None
            else:
                _logger.error(f" Formato de fecha inválido: '{fecha_str}' (longitud: {len(fecha_str)})")
                return None

            # Procesar importes
            try:
                # Limpiar y procesar importe
                importe_clean = ''.join(c for c in importe_str if c.isdigit())
                if importe_clean and len(importe_clean) > 0:
                    data['importe'] = float(importe_clean) / 100.0
                    _logger.info(f" Importe procesado: {data['importe']} (de '{importe_str}' → '{importe_clean}')")
                else:
                    _logger.error(f" Importe no contiene dígitos válidos: '{importe_str}'")
                    data['importe'] = 0.0

                # Limpiar y procesar saldo
                saldo_clean = ''.join(c for c in saldo_str if c.isdigit())
                if saldo_clean and len(saldo_clean) > 0:
                    data['saldo'] = float(saldo_clean) / 100.0
                    _logger.info(f" Saldo procesado: {data['saldo']} (de '{saldo_str}' → '{saldo_clean}')")
                else:
                    _logger.error(f" Saldo no contiene dígitos válidos: '{saldo_str}'")
                    data['saldo'] = 0.0

            except ValueError as e:
                _logger.error(f" Error crítico al convertir importes: {str(e)}")
                data['importe'] = 0.0
                data['saldo'] = 0.0

            # Validar signo
            if data['signo'] not in ['+', '-']:
                _logger.warning(f" Signo inválido '{data['signo']}', usando '+'")
                data['signo'] = '+'

            # Campos adicionales para el modelo
            data.update({
                'formato_origen': 'extendido',
                'codigo_devolucion': '',
                'causa_devolucion': '',
                'campo_afil': '',
            })

            _logger.info(f" PARSING EXITOSO:")
            _logger.info(f"   Cuenta: {data['numero_cuenta']}")
            _logger.info(f"   Fecha: {data['fecha_movimiento']}")
            _logger.info(f"   Importe: {data['importe']} {data['signo']}")
            _logger.info(f"   Concepto: {data['concepto']}")

            return data

        except Exception as e:
            _logger.error(f" Error crítico al parsear línea: {str(e)}")
            _logger.error(f"   Línea (100 chars): {line_clean[:100]}...")
            return None

    def parse_formato_original(self, line):
        """Parser para formato original (compatibilidad)"""
        if len(line) < 113:
            return None

        try:
            data = {}
            data['numero_cuenta'] = line[0:16].strip()
            fecha_str = line[16:24].strip()
            data['hora_movimiento'] = line[24:28].strip()
            data['sucursal'] = line[28:32].strip()
            data['clacon'] = line[32:36].strip()
            data['descripcion'] = line[36:76].strip()
            data['signo'] = line[76:77].strip()
            importe_str = line[77:91].strip()
            saldo_str = line[91:105].strip()
            data['referencia'] = line[105:113].strip()

            # Campos vacíos para compatibilidad
            data.update({
                'concepto': '',
                'informacion_adicional': '',
                'banco_participante': '',
                'clabe_beneficiario': '',
                'nombre_beneficiario': '',
                'cuenta_ordenante': '',
                'nombre_ordenante': '',
                'codigo_devolucion': '',
                'causa_devolucion': '',
                'rfc_receptor': '',
                'rfc_ordenante': '',
                'clave_rastreo': '',
                'formato_origen': 'original',
                'campo_afil': ''
            })

            # Procesar fecha MMDDAAAA (formato original diferente)
            if len(fecha_str) == 8 and fecha_str.isdigit():
                try:
                    mes = int(fecha_str[0:2])
                    dia = int(fecha_str[2:4])
                    año = int(fecha_str[4:8])
                    data['fecha_movimiento'] = datetime(año, mes, dia).date()
                except ValueError:
                    return None

            # Convertir importes
            try:
                importe_clean = ''.join(c for c in importe_str if c.isdigit())
                saldo_clean = ''.join(c for c in saldo_str if c.isdigit())
                data['importe'] = float(importe_clean) / 100.0 if importe_clean else 0.0
                data['saldo'] = float(saldo_clean) / 100.0 if saldo_clean else 0.0
            except ValueError:
                data['importe'] = 0.0
                data['saldo'] = 0.0

            if data['signo'] not in ['+', '-']:
                data['signo'] = '+'

            return data

        except Exception as e:
            _logger.error(f"Error al parsear línea formato original: {str(e)}")
            return None

    def parse_santander_line(self, line):
        """Método principal de parsing"""
        if not line or len(line.strip()) < 50:
            return None

        line_clean = line.strip()

        # Determinar formato
        if self.formato_extracto == 'auto':
            formato = self._detect_format(line_clean)
        else:
            formato = self.formato_extracto

        _logger.info(f" Parseando con formato: {formato}, línea de {len(line_clean)} chars")

        if formato == 'formato_extendido':
            return self.parse_formato_extendido_correcto(line_clean)
        else:
            return self.parse_formato_original(line_clean)

    def action_import_statements(self):
        """Acción de importación con logging mejorado"""
        if not self.data_file:
            raise UserError('Debe seleccionar un archivo para importar.')

        import base64
        file_data = base64.b64decode(self.data_file)

        try:
            content = None
            for encoding in ['utf-8', 'latin-1', 'cp1252', 'ascii']:
                try:
                    content = file_data.decode(encoding)
                    _logger.info(f" Archivo decodificado con {encoding}")
                    break
                except UnicodeDecodeError:
                    continue

            if not content:
                raise UserError('No se pudo decodificar el archivo.')

        except Exception as e:
            raise UserError(f'Error al leer el archivo: {str(e)}')

        # Procesar líneas
        lines = content.split('\n')
        imported_count = 0
        errors = []

        SantanderStatement = self.env['santander.bank.statement']

        _logger.info(f" === INICIANDO IMPORTACIÓN DE {len(lines)} LÍNEAS ===")

        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            if not line:
                continue

            _logger.info(f"\n --- PROCESANDO LÍNEA {line_num} ---")
            _logger.info(f" Longitud: {len(line)} caracteres")

            parsed_data = self.parse_santander_line(line)

            if not parsed_data:
                error_msg = f'Línea {line_num}: No se pudo parsear'
                errors.append(error_msg)
                _logger.error(f" {error_msg}")
                continue

            # Filtro por cuenta
            if self.numero_cuenta and parsed_data['numero_cuenta'] != self.numero_cuenta:
                _logger.info(f" Línea {line_num} filtrada por número de cuenta")
                continue

            # Metadatos
            parsed_data.update({
                'archivo_origen': self.filename or 'archivo_importado.txt',
                'fecha_importacion': fields.Datetime.now(),
                'procesado': 'pendiente',
            })

            try:
                # Verificar duplicados
                existing = SantanderStatement.search([
                    ('numero_cuenta', '=', parsed_data['numero_cuenta']),
                    ('fecha_movimiento', '=', parsed_data['fecha_movimiento']),
                    ('referencia', '=', parsed_data['referencia']),
                    ('importe', '=', parsed_data['importe']),
                ])

                if not existing:
                    new_record = SantanderStatement.create(parsed_data)
                    imported_count += 1
                    _logger.info(f" LÍNEA {line_num} CREADA")
                    _logger.info(f"    ID: {new_record.id}")
                    _logger.info(f"    Importe: {parsed_data['importe']}")
                    _logger.info(f"    Concepto: {parsed_data['concepto']}")
                else:
                    _logger.info(f" LÍNEA {line_num} - Registro duplicado omitido")

            except Exception as e:
                error_msg = f'Línea {line_num}: Error al crear registro - {str(e)}'
                errors.append(error_msg)
                _logger.error(f" {error_msg}")

        # Resultado final
        _logger.info(f"\n === IMPORTACIÓN COMPLETADA ===")
        _logger.info(f" Total importados: {imported_count}")
        _logger.info(f" Total errores: {len(errors)}")

        message = f'Importación completada con parser DEFINITIVO.\n'
        message += f'Registros importados: {imported_count}\n'
        message += f'Total líneas procesadas: {len([l for l in lines if l.strip()])}\n'

        if errors:
            message += f'\nErrores ({len(errors)}): \n'
            message += '\n'.join(errors[:3])

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Importación Extracto Santander',
                'message': message,
                'type': 'success' if imported_count > 0 else 'warning',
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},

            }
        }


class SantanderCSVStatementImporter(models.TransientModel):
    _name = 'santander.csv.statement.importer'
    _description = 'Importador CSV Santander (Formato Específico)'

    data_file = fields.Binary(string='Archivo CSV', required=True)
    filename = fields.Char(string='Nombre del Archivo')
    numero_cuenta = fields.Char(string='Número de Cuenta (Opcional)',
                                help='Si se especifica, solo se importarán movimientos de esta cuenta')
    skip_header_lines = fields.Integer(string='Saltar Líneas de Header', default=0,
                                     help='Líneas adicionales a saltar después de detectar el header')

    def _extract_account_info_from_santander_csv(self, content_lines):
        """
        Extrae información de cuenta de los metadatos del CSV Santander
        """
        account_info = {}

        for line in content_lines[:10]:
            line_clean = line.strip()

            # Extraer número de cuenta
            if 'Cuenta:' in line_clean:
                match = re.search(r'Cuenta:\s*(\d+)', line_clean)
                if match:
                    account_info['numero_cuenta'] = match.group(1)

            # Extraer contrato/empresa
            elif 'Contrato:' in line_clean:
                parts = line_clean.split(' ', 2)
                if len(parts) > 2:
                    account_info['empresa'] = parts[2].strip()

            # Extraer periodo
            elif 'Periodo de:' in line_clean:
                account_info['periodo'] = line_clean.replace('Periodo de:', '').strip()

            # Extraer usuario
            elif 'Usuario:' in line_clean:
                parts = line_clean.split(',', 2)
                if len(parts) > 1:
                    account_info['usuario'] = parts[1].strip()

        _logger.info(f" Información extraída: {account_info}")
        return account_info

    def _detect_santander_csv_structure(self, content_lines):
        """
        Detecta estructura específica del CSV Santander
        """
        structure_info = {}

        # Buscar el header específico de Santander
        header_found = False
        header_line_idx = None

        for i, line in enumerate(content_lines):
            line_clean = line.strip().lower()

            # El header típico de Santander
            santander_headers = ['fecha', 'hora', 'sucursal', 'descripcion', 'importe cargo', 'importe abono', 'saldo']

            # Verificar si esta línea contiene los headers de Santander
            if all(header in line_clean for header in ['fecha', 'descripcion', 'saldo']):
                header_line_idx = i
                header_found = True
                _logger.info(f" Header Santander detectado en línea {i + 1}")
                break

        if header_found:
            header_line = content_lines[header_line_idx].strip()
            structure_info['header_line'] = header_line_idx
            structure_info['header_content'] = header_line
            structure_info['delimiter'] = ','

            # Headers específicos de Santander (orden fijo)
            structure_info['columns'] = [
                'Fecha', 'Hora', 'Sucursal', 'Descripcion',
                'Importe Cargo', 'Importe Abono', 'Saldo', 'Referencia', 'Concepto'
            ]
            structure_info['total_columns'] = 9

            _logger.info(f" Estructura Santander detectada: {structure_info['columns']}")
        else:
            raise UserError('No se pudo detectar el formato de CSV de Santander. Verifique que el archivo sea correcto.')

        return structure_info

    def _parse_santander_date(self, date_str):
        """
        Parsea fechas específicas de Santander: '01092025'
        """
        if not date_str or date_str.strip() == '':
            return None

        # Limpiar comillas simples y espacios
        date_clean = date_str.strip().replace("'", "").replace('"', '')

        # Formato específico de Santander: DDMMYYYY (01092025)
        if len(date_clean) == 8 and date_clean.isdigit():
            try:
                return datetime.strptime(date_clean, '%d%m%Y').date()
            except ValueError:
                pass

        _logger.error(f" Error al parsear fecha Santander: '{date_str}'")
        return None

    def _parse_santander_amount(self, amount_str):
        """
        Parsea importes específicos de Santander con formato "1,234.56"
        """
        if not amount_str or str(amount_str).strip() == '' or str(amount_str).strip() == '0':
            return 0.0

        # Limpiar formato específico de Santander
        clean_amount = str(amount_str).strip()
        clean_amount = clean_amount.replace('"', '').replace("'", "")
        clean_amount = clean_amount.replace(',', '')
        clean_amount = clean_amount.strip()

        if not clean_amount:
            return 0.0

        try:
            return float(clean_amount)
        except ValueError:
            _logger.warning(f"No se pudo convertir importe Santander: '{amount_str}' → '{clean_amount}'")
            return 0.0

    def _parse_santander_time(self, time_str):
        """
        Parsea hora específica de Santander: 04:05
        """
        if not time_str:
            return '0000'

        time_clean = str(time_str).strip().replace("'", "").replace('"', '')

        # Formato HH:MM → HHMM
        if ':' in time_clean and len(time_clean) == 5:
            return time_clean.replace(':', '')

        return '0000'

    def parse_santander_csv(self, content):
        """
        Parser ESPECÍFICO para CSV Santander
        """
        lines = content.split('\n')

        # Extraer información de cuenta
        account_info = self._extract_account_info_from_santander_csv(lines)

        # Detectar estructura
        structure = self._detect_santander_csv_structure(lines)

        # Línea de inicio de datos (después del header + skip adicional)
        data_start_line = structure['header_line'] + 1 + self.skip_header_lines
        data_lines = lines[data_start_line:]

        # Filtrar líneas vacías
        data_lines = [line for line in data_lines if line.strip()]

        parsed_records = []
        line_num = data_start_line

        _logger.info(f" Procesando {len(data_lines)} líneas de datos Santander")

        for line in data_lines:
            line_num += 1

            try:
                # Usar CSV reader para manejar comillas correctamente
                csv_reader = csv.reader([line])
                row = next(csv_reader)

                # Validar que tenga al menos 6 columnas (mínimo para procesar)
                if len(row) < 6:
                    _logger.debug(f" Línea {line_num}: Muy pocas columnas ({len(row)}), saltando")
                    continue

                record_data = {}

                # Posiciones fijas según el formato detectado:

                # FECHA (posición 0)
                fecha = self._parse_santander_date(row[0])
                if not fecha:
                    _logger.debug(f" Línea {line_num}: Fecha inválida '{row[0]}', saltando")
                    continue
                record_data['fecha_movimiento'] = fecha

                # HORA (posición 1)
                record_data['hora_movimiento'] = self._parse_santander_time(row[1])

                # SUCURSAL (posición 2)
                sucursal = str(row[2]).strip().replace("'", "").replace('"', '') if len(row) > 2 else ''
                record_data['sucursal'] = sucursal[:10]

                # DESCRIPCIÓN (posición 3)
                descripcion = str(row[3]).strip() if len(row) > 3 else ''
                record_data['descripcion'] = descripcion[:255]

                # IMPORTES (posiciones 4 y 5)
                cargo = self._parse_santander_amount(row[4]) if len(row) > 4 else 0.0
                abono = self._parse_santander_amount(row[5]) if len(row) > 5 else 0.0

                # Determinar signo e importe
                if cargo > 0:
                    record_data['signo'] = '-'
                    record_data['importe'] = cargo
                elif abono > 0:
                    record_data['signo'] = '+'
                    record_data['importe'] = abono
                else:
                    # Saltar transacciones sin importe
                    _logger.debug(f" Línea {line_num}: Sin importe válido, saltando")
                    continue

                # SALDO (posición 6)
                saldo = self._parse_santander_amount(row[6]) if len(row) > 6 else 0.0
                record_data['saldo'] = saldo

                # REFERENCIA (posición 7)
                referencia = str(row[7]).strip() if len(row) > 7 else ''
                record_data['referencia'] = referencia[:50]

                # CONCEPTO (posición 8)
                concepto = str(row[8]).strip() if len(row) > 8 else ''
                record_data['concepto'] = concepto[:100] if concepto else descripcion[:50]

                # ===== CAMPOS ADICIONALES DEL MODELO =====

                # Usar información extraída
                record_data['numero_cuenta'] = self.numero_cuenta or account_info.get('numero_cuenta', '')

                # Campos requeridos del modelo
                record_data.update({
                    'clacon': '',
                    'informacion_adicional': f'Santander CSV - Usuario: {account_info.get("usuario", "N/A")}',
                    'codigo_devolucion': '',
                    'causa_devolucion': '',
                    'formato_origen': 'original',
                    'campo_afil': '',
                    'clave_rastreo': referencia[:50] if referencia else '',
                    'banco_participante': 'SANTANDER',
                    'cuenta_ordenante': '',
                    'nombre_beneficiario': '',
                    'nombre_ordenante': '',
                    'clabe_beneficiario': '',
                    'rfc_receptor': '',
                    'rfc_ordenante': '',
                })

                # Metadatos
                record_data.update({
                    'archivo_origen': self.filename or 'santander.csv',
                    'fecha_importacion': fields.Datetime.now(),
                    'procesado': 'pendiente',
                })

                _logger.debug(f" Línea {line_num}: {fecha} {record_data['hora_movimiento']} | {record_data['signo']}{record_data['importe']}")
                parsed_records.append(record_data)

            except Exception as e:
                _logger.error(f" Error procesando línea {line_num}: {str(e)}")
                _logger.error(f"    Contenido: {line[:200]}")
                continue

        _logger.info(f" Total registros Santander parseados: {len(parsed_records)}")
        return parsed_records, structure, account_info

    def action_import_statements(self):
        """
        Importación principal CSV Santander
        """
        if not self.data_file:
            raise UserError('Debe seleccionar un archivo CSV.')

        import base64
        file_data = base64.b64decode(self.data_file)

        try:
            # Decodificar con encodings típicos de Santander
            content = None
            for encoding in ['utf-8', 'latin-1', 'cp1252', 'utf-8-sig']:
                try:
                    content = file_data.decode(encoding)
                    _logger.info(f" CSV Santander decodificado con {encoding}")
                    break
                except UnicodeDecodeError:
                    continue

            if not content:
                raise UserError('No se pudo decodificar el archivo CSV.')

        except Exception as e:
            raise UserError(f'Error al leer el archivo: {str(e)}')

        # Parsear CSV específico de Santander
        try:
            parsed_records, structure, account_info = self.parse_santander_csv(content)
        except Exception as e:
            raise UserError(f'Error al parsear CSV Santander: {str(e)}')

        if not parsed_records:
            raise UserError('No se encontraron registros válidos en el CSV de Santander. Verifique el formato.')

        # Importar usando modelo existente con manejo de transacciones
        BankStatement = self.env['santander.bank.statement']

        imported_count = 0
        errors = []

        _logger.info(f" === IMPORTANDO {len(parsed_records)} REGISTROS SANTANDER ===")

        # Procesar en lotes más pequeños para evitar problemas de memoria
        batch_size = 50

        for batch_start in range(0, len(parsed_records), batch_size):
            batch_end = min(batch_start + batch_size, len(parsed_records))
            batch = parsed_records[batch_start:batch_end]

            # Usar savepoint para manejo de errores por lotes
            with self.env.cr.savepoint():
                for i, record_data in enumerate(batch, batch_start + 1):
                    try:
                        # Filtrar por cuenta si se especifica
                        if self.numero_cuenta and record_data['numero_cuenta'] != self.numero_cuenta:
                            continue

                        # Verificar duplicados más específico
                        existing = BankStatement.search([
                            ('numero_cuenta', '=', record_data['numero_cuenta']),
                            ('fecha_movimiento', '=', record_data['fecha_movimiento']),
                            ('hora_movimiento', '=', record_data['hora_movimiento']),
                            ('importe', '=', record_data['importe']),
                            ('descripcion', '=', record_data['descripcion']),
                        ])

                        if not existing:
                            new_record = BankStatement.create(record_data)
                            imported_count += 1
                            if i % 10 == 0:  # Log cada 10 registros
                                _logger.info(f" Procesados: {i}/{len(parsed_records)}")
                        else:
                            _logger.debug(f" Registro {i} duplicado - omitido")

                    except Exception as e:
                        error_msg = f'Registro {i}: {str(e)}'
                        errors.append(error_msg)
                        _logger.error(f" {error_msg}")

        # Resultado final
        _logger.info(f" === IMPORTACIÓN SANTANDER CSV COMPLETADA ===")
        _logger.info(f" Importados: {imported_count}")
        _logger.info(f" Errores: {len(errors)}")

        message = f'Importación CSV Santander completada.\n'
        message += f'Cuenta: {account_info.get("numero_cuenta", "No detectada")}\n'
        message += f'Empresa: {account_info.get("empresa", "No detectada")}\n'
        message += f'Periodo: {account_info.get("periodo", "No detectado")}\n'
        message += f'Registros importados: {imported_count}\n'
        message += f'Total procesados: {len(parsed_records)}\n'

        if errors and len(errors) <= 5:
            message += f'\nErrores: \n' + '\n'.join(errors[:5])
        elif errors:
            message += f'\nErrores: {len(errors)} (ver logs para detalles)'

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': ' CSV Santander Importado',
                'message': message,
                'type': 'success' if imported_count > 0 else 'warning',
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            }
        }
