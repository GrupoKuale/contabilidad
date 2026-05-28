# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, timedelta
import logging

_logger = logging.getLogger(__name__)


class BankReconciliation(models.Model):
    _name = 'bank.reconciliation'
    _description = 'Conciliación Bancaria'
    _order = 'fecha_conciliacion desc'

    name = fields.Char(string='Número', required=True, copy=False,
                       readonly=True, default='Nueva')

    fecha_conciliacion = fields.Date(string='Fecha de Conciliación',
                                     default=fields.Date.context_today, required=True)

    estado = fields.Selection([
        ('borrador', 'Borrador'),
        ('procesando', 'Procesando'),
        ('completado', 'Completado'),
        ('cancelado', 'Cancelado')
    ], string='Estado', default='borrador', required=True)

    # Campo empresa necesario para la moneda
    company_id = fields.Many2one('res.company', string='Compañía',
                                 default=lambda self: self.env.company, required=True)

    # Configuración de diarios bancarios para pagos
    journal_id = fields.Many2one('account.journal', string='Diario De Facturas',
                                 help='Diario para filtrar las facturas a conciliar. Puede ser diario de ventas, compras, etc.')

    journal_pago_id = fields.Many2one(
        'account.journal',
        string='Diario Bancario para Pagos',
        domain="[('type', '=', 'bank')]",
        required=True,
        help='Diario bancario donde se registrarán los pagos (debe tener métodos de pago configurados)'
    )

    # Filtro por banco específico
    banco_filtro = fields.Selection([
        ('todos', 'Todos los Bancos'),
        ('santander', 'Santander'),
        ('bbva', 'BBVA'),
        ('banregio', 'Banregio'),
        ('inbursa', 'Inbursa'),
        ('banamex', 'Banamex')
    ], string='Filtrar por Banco', default='todos',
        help='Filtrar extractos por banco específico')

    # Filtros para la conciliación
    fecha_desde = fields.Date(string='Fecha Desde', required=True,
                              default=lambda self: fields.Date.today().replace(day=1))
    fecha_hasta = fields.Date(string='Fecha Hasta', required=True,
                              default=fields.Date.today)

    # Tolerancias específicas
    tolerance_amount = fields.Float(string='Tolerancia de Monto', default=0.01,
                                    help='Tolerancia permitida en la diferencia de montos')
    tolerance_days = fields.Integer(string='Tolerancia de Días', default=3,
                                    help='Días de diferencia permitidos en las fechas')

    # Tolerancias específicas para SPEI
    tolerance_spei_amount = fields.Float(string='Tolerancia SPEI (Monto)', default=0.50,
                                         help='Tolerancia específica para operaciones SPEI')
    tolerance_spei_days = fields.Integer(string='Tolerancia SPEI (Días)', default=1,
                                         help='Días de diferencia para operaciones SPEI (más estricto)')

    #  Opciones de coincidencia mejoradas
    usar_referencias = fields.Boolean(string='Usar Referencias', default=True,
                                      help='Buscar coincidencias usando referencias/claves de rastreo')
    usar_horas = fields.Boolean(string='Considerar Horas', default=False,
                                help='Para BBVA: considerar horas en la coincidencia')

    # Estadísticas
    total_extractos = fields.Integer(string='Total Extractos', compute='_compute_statistics')
    total_asientos = fields.Integer(string='Total Asientos', compute='_compute_statistics')
    total_conciliados_auto = fields.Integer(string='Conciliados Automáticamente',
                                            compute='_compute_statistics')
    total_pendientes = fields.Integer(string='Pendientes Manual', compute='_compute_statistics')
    total_pagos_creados = fields.Integer(string='Pagos Creados', compute='_compute_statistics')

    #  Estadísticas por banco
    total_santander = fields.Integer(string='Extractos Santander', compute='_compute_bank_statistics')
    total_bbva = fields.Integer(string='Extractos BBVA', compute='_compute_bank_statistics')
    total_banregio = fields.Integer(string='Extractos Banregio', compute='_compute_bank_statistics')

    # Líneas de conciliación
    linea_ids = fields.One2many('bank.reconciliation.line', 'reconciliation_id',
                                string='Líneas de Conciliación')

    @api.model
    def create(self, vals):
        if vals.get('name', 'Nueva') == 'Nueva':
            vals['name'] = self.env['ir.sequence'].next_by_code('bank.reconciliation.sequence') or 'CONC/0001'
        return super(BankReconciliation, self).create(vals)

    @api.depends('linea_ids')
    def _compute_statistics(self):
        for record in self:
            lines = record.linea_ids
            record.total_extractos = len(lines.mapped('extracto_id'))
            record.total_asientos = len(lines.mapped('asiento_id'))
            record.total_conciliados_auto = len(lines.filtered('es_automatico'))
            record.total_pendientes = len(lines.filtered(lambda l: not l.conciliado))
            record.total_pagos_creados = len(lines.filtered('payment_id'))

    @api.depends('linea_ids.extracto_id')
    def _compute_bank_statistics(self):
        """ Calcular estadísticas por banco"""
        for record in self:
            extractos = record.linea_ids.mapped('extracto_id')
            record.total_santander = len(extractos.filtered(lambda e: e.banco_participante == 'SANTANDER'))
            record.total_bbva = len(extractos.filtered(lambda e: e.banco_participante == 'BBVA'))
            record.total_banregio = len(extractos.filtered(lambda e: e.banco_participante == 'BANREGIO'))

    def action_buscar_coincidencias(self):
        """ Busca coincidencias con filtros por banco y mejores algoritmos"""
        self.ensure_one()

        #  Construir dominio con filtro de banco
        domain_extractos = [
            ('fecha_movimiento', '>=', self.fecha_desde),
            ('fecha_movimiento', '<=', self.fecha_hasta),
            ('procesado', '=', 'pendiente')
        ]

        #  Aplicar filtro por banco
        if self.banco_filtro != 'todos':
            banco_map = {
                'santander': 'SANTANDER',
                'bbva': 'BBVA',
                'banregio': 'BANREGIO',
                'inbursa': 'INBURSA',
                'banamex': 'BANAMEX',
            }
            if self.banco_filtro in banco_map:
                domain_extractos.append(('banco_participante', '=', banco_map[self.banco_filtro]))

        # Obtener extractos filtrados
        extractos = self.env['santander.bank.statement'].search(domain_extractos)

        _logger.info(f" Conciliación iniciada: {len(extractos)} extractos encontrados")
        _logger.info(f" Rango: {self.fecha_desde} a {self.fecha_hasta}")
        _logger.info(f" Banco filtro: {self.banco_filtro}")

        #  NUEVO: Construir dominio para facturas CON FILTRO POR DIARIO
        fecha_busqueda_desde = self.fecha_desde - timedelta(days=60)
        domain_asientos = [
            ('invoice_date', '>=', fecha_busqueda_desde),
            ('invoice_date', '<=', self.fecha_hasta),
            ('move_type', 'in', ['out_invoice', 'in_invoice', 'out_refund', 'in_refund']),
        ]

        #  FILTRAR POR DIARIO SI ESTÁ CONFIGURADO
        if self.journal_id:
            domain_asientos.append(('journal_id', '=', self.journal_id.id))
            _logger.info(f" Filtrando facturas del diario: {self.journal_id.name}")
        else:
            _logger.info(f" Buscando facturas de TODOS los diarios")

        asientos = self.env['account.move'].search(domain_asientos)
        asientos_pendientes = asientos.filtered(lambda a: a.amount_residual > 0.01)

        _logger.info(f" {len(asientos_pendientes)} facturas pendientes encontradas")

        # Limpiar líneas existentes
        self.linea_ids.unlink()

        coincidencias_encontradas = 0
        coincidencias_por_banco = {'SANTANDER': 0, 'BBVA': 0, 'BANREGIO': 0, 'OTROS': 0}

        for extracto in extractos:
            mejor_coincidencia = None
            menor_diferencia = float('inf')
            tipo_coincidencia_encontrada = 'exacta'

            for asiento in asientos_pendientes:
                #  Algoritmo de coincidencia más inteligente
                resultado_match = self._evaluar_coincidencia(extracto, asiento)

                if resultado_match['es_coincidencia']:
                    if resultado_match['puntuacion'] < menor_diferencia:
                        menor_diferencia = resultado_match['puntuacion']
                        mejor_coincidencia = asiento
                        tipo_coincidencia_encontrada = resultado_match['tipo']

            # Crear línea de conciliación
            vals = {
                'reconciliation_id': self.id,
                'extracto_id': extracto.id,
                'asiento_id': mejor_coincidencia.id if mejor_coincidencia else False,
                'conciliado': bool(mejor_coincidencia),
                'es_automatico': bool(mejor_coincidencia),
                'diferencia_dias': 0,
                'diferencia_monto': 0.0,
                'tipo_coincidencia': 'sin_match',
                'algoritmo_usado': tipo_coincidencia_encontrada if mejor_coincidencia else 'ninguno',  # NUEVO
            }

            if mejor_coincidencia:
                vals.update({
                    'diferencia_dias': abs((extracto.fecha_movimiento - mejor_coincidencia.invoice_date).days),
                    'diferencia_monto': abs(abs(extracto.importe) - abs(mejor_coincidencia.amount_residual)),
                    'tipo_coincidencia': self._determinar_tipo_coincidencia(extracto, mejor_coincidencia),
                })

            self.env['bank.reconciliation.line'].create(vals)

            if mejor_coincidencia:
                coincidencias_encontradas += 1
                banco = extracto.banco_participante or 'OTROS'
                if banco in coincidencias_por_banco:
                    coincidencias_por_banco[banco] += 1
                else:
                    coincidencias_por_banco['OTROS'] += 1

        self.estado = 'procesando'

        #  Mensaje con detalles por banco
        mensaje_detalle = f'Se encontraron {coincidencias_encontradas} coincidencias de {len(extractos)} extractos.\n'
        for banco, count in coincidencias_por_banco.items():
            if count > 0:
                mensaje_detalle += f'{banco}: {count} coincidencias\n'

        _logger.info(f" Conciliación completada: {coincidencias_encontradas} coincidencias")

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Búsqueda Completada',
                'message': mensaje_detalle,
                'type': 'success',
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            }
        }

    def _evaluar_coincidencia(self, extracto, asiento):
        """ Algoritmo mejorado de evaluación de coincidencias"""

        # Verificar compatibilidad de tipos
        if not self._son_compatibles(extracto, asiento):
            return {'es_coincidencia': False, 'puntuacion': float('inf'), 'tipo': 'incompatible'}

        saldo_pendiente = asiento.amount_residual
        monto_extracto = abs(extracto.importe)
        diff_fecha = abs((extracto.fecha_movimiento - asiento.invoice_date).days)
        diff_monto = abs(monto_extracto - saldo_pendiente)

        #  algoritmos según características del extracto

        # COINCIDENCIA POR REFERENCIA/SPEI
        if self.usar_referencias and extracto.clave_rastreo and asiento.ref:
            if extracto.clave_rastreo in asiento.ref or asiento.ref in extracto.descripcion:
                if diff_monto <= self.tolerance_spei_amount:
                    return {
                        'es_coincidencia': True,
                        'puntuacion': diff_monto * 0.1 + diff_fecha * 0.01,
                        'tipo': 'referencia'
                    }

        # COINCIDENCIA SPEI (para operaciones SPEI usar tolerancias específicas)
        es_spei = 'SPEI' in (extracto.descripcion or '').upper()
        if es_spei:
            tolerance_amount = self.tolerance_spei_amount
            tolerance_days = self.tolerance_spei_days
            tipo_match = 'spei'
        else:
            tolerance_amount = self.tolerance_amount
            tolerance_days = self.tolerance_days
            tipo_match = 'normal'

        # COINCIDENCIA POR MONTO Y FECHA
        if diff_fecha <= tolerance_days and diff_monto <= tolerance_amount:
            #  Si es BBVA y se solicita considerar horas
            puntuacion_base = diff_fecha + (diff_monto * 10)

            if self.usar_horas and extracto.banco_participante == 'BBVA' and extracto.hora_movimiento:
                # Bonificación si las horas están en horario bancario
                hora = extracto.hora_movimiento or '0000'
                if '0800' <= hora <= '1800':  # Horario bancario
                    puntuacion_base *= 0.8  # 20% mejor puntuación

            return {
                'es_coincidencia': True,
                'puntuacion': puntuacion_base,
                'tipo': tipo_match
            }

        # COINCIDENCIA EXACTA DE MONTO (tolerancia de fecha más amplia)
        if diff_monto <= 0.01 and diff_fecha <= (tolerance_days * 2):
            return {
                'es_coincidencia': True,
                'puntuacion': diff_fecha * 0.5,  # Prioridad al monto exacto
                'tipo': 'exacta'
            }

        return {'es_coincidencia': False, 'puntuacion': float('inf'), 'tipo': 'sin_match'}

    def _son_compatibles(self, extracto, asiento):
        """Verifica si un extracto y asiento son compatibles para conciliación"""
        # Para abonos (+): facturas de cliente (out_invoice)
        # Para cargos (-): facturas de proveedor (in_invoice)
        if extracto.signo == '+' and asiento.move_type in ['out_invoice', 'out_refund']:
            return True
        elif extracto.signo == '-' and asiento.move_type in ['in_invoice', 'in_refund']:
            return True
        return False

    def _determinar_tipo_coincidencia(self, extracto, asiento):
        """Determina el tipo de coincidencia encontrada"""
        saldo_pendiente = asiento.amount_residual
        monto_extracto = abs(extracto.importe)

        tolerance = self.tolerance_spei_amount if 'SPEI' in (
                    extracto.descripcion or '').upper() else self.tolerance_amount

        if abs(monto_extracto - saldo_pendiente) <= tolerance:
            return 'pago_completo'
        elif monto_extracto < saldo_pendiente:
            return 'pago_parcial'
        else:
            return 'sobrepago'

    def action_confirmar_conciliacion(self):
        """ VERSIÓN MEJORADA - Con mejor manejo de errores y logging"""
        self.ensure_one()

        if not self.linea_ids:
            raise UserError('No hay líneas para conciliar.')

        if not self.journal_id:
            raise UserError('Debe seleccionar un diario bancario para registrar los pagos.')

        lineas_conciliadas = self.linea_ids.filtered('conciliado')

        if not lineas_conciliadas:
            raise UserError('No hay líneas marcadas como conciliadas.')

        _logger.info(f" Iniciando confirmación de conciliación: {len(lineas_conciliadas)} líneas")

        pagos_creados = 0
        pagos_con_error = 0
        pagos_por_banco = {'SANTANDER': 0, 'BBVA': 0, 'BANREGIO': 0, 'OTROS': 0}
        errores = []

        for linea in lineas_conciliadas:
            if linea.asiento_id and linea.extracto_id and not linea.payment_id:
                try:
                    #  Usar el método corregido
                    pago = self._crear_pago_desde_extracto(linea)

                    if pago:
                        linea.payment_id = pago.id
                        linea.extracto_id.procesado = 'procesado'
                        pagos_creados += 1

                        # Estadísticas por banco
                        banco = linea.extracto_id.banco_participante or 'OTROS'
                        pagos_por_banco[banco] = pagos_por_banco.get(banco, 0) + 1

                        _logger.info(f" Pago creado para {banco}: {linea.extracto_id.descripcion}")
                    else:
                        pagos_con_error += 1
                        errores.append(f'Línea {linea.id}: No se pudo crear el pago')

                except Exception as e:
                    pagos_con_error += 1
                    error_msg = str(e)
                    _logger.error(f' Error creando pago para línea {linea.id}: {error_msg}')
                    errores.append(f'Línea {linea.id}: {error_msg}')

        # Actualizar estado según resultado
        if pagos_creados > 0 and pagos_con_error == 0:
            self.estado = 'completado'
            tipo_mensaje = 'success'
        elif pagos_creados > 0 and pagos_con_error > 0:
            self.estado = 'completado'  # Parcialmente completado
            tipo_mensaje = 'warning'
        else:
            tipo_mensaje = 'danger'

        #  Mensaje detallado con estadísticas por banco
        mensaje = f' Se crearon {pagos_creados} pagos exitosamente.'

        if pagos_con_error > 0:
            mensaje += f'  {pagos_con_error} pagos con errores.'

        mensaje += '\n\n Por banco:\n'
        for banco, count in pagos_por_banco.items():
            if count > 0:
                mensaje += f'• {banco}: {count} pagos\n'

        if errores:
            mensaje += f'\n Errores encontrados:\n'
            for error in errores[:5]:  # Solo mostrar primeros 5 errores
                mensaje += f'• {error}\n'
            if len(errores) > 5:
                mensaje += f'• ... y {len(errores) - 5} errores más'

        _logger.info(f"🏁 Conciliación completada: {pagos_creados} pagos creados, {pagos_con_error} errores")

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Conciliación Completada',
                'message': mensaje,
                'type': tipo_mensaje,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            }
        }

    def _crear_pago_desde_extracto(self, linea):
        """ MODIFICADO - Usa journal_pago_id para crear el pago"""
        extracto = linea.extracto_id
        asiento = linea.asiento_id

        # Determinar tipo de pago
        if asiento.move_type in ['out_invoice', 'out_refund']:
            payment_type = 'inbound'
            partner_type = 'customer'
        elif asiento.move_type in ['in_invoice', 'in_refund']:
            payment_type = 'outbound'
            partner_type = 'supplier'
        else:
            raise UserError(f'Tipo de documento no soportado: {asiento.move_type}')

        # Referencia mejorada
        banco_info = f"[{extracto.banco_participante}]" if extracto.banco_participante else ""
        referencia_base = extracto.clave_rastreo or extracto.referencia or ""
        referencia_completa = f'Conciliación {banco_info}: {referencia_base} - {asiento.name}'

        #  VALORES DEL PAGO - USANDO journal_pago_id
        payment_vals = {
            'payment_type': payment_type,
            'partner_type': partner_type,
            'partner_id': asiento.partner_id.id,
            'amount': abs(extracto.importe),
            'currency_id': self.company_id.currency_id.id,
            'journal_id': self.journal_pago_id.id,  # ← USA EL DIARIO BANCARIO
            'payment_method_line_id': self._get_payment_method_line(payment_type),
            'date': extracto.fecha_movimiento,
            'ref': referencia_completa[:255],
        }

        # Campos personalizados
        payment_fields = self.env['account.payment']._fields.keys()
        if 'bank_reference' in payment_fields:
            payment_vals['bank_reference'] = (extracto.clave_rastreo or extracto.referencia or '')[:50]
        if 'effective_date' in payment_fields:
            payment_vals['effective_date'] = extracto.fecha_movimiento

        _logger.info(f'💳 Creando pago en {self.journal_pago_id.name}: ${payment_vals["amount"]}')

        try:
            pago = self.env['account.payment'].create(payment_vals)
            pago.action_post()
            self._reconciliar_pago_con_factura(pago, asiento)
            _logger.info(f' Pago creado exitosamente: {pago.name}')
            return pago
        except Exception as e:
            _logger.error(f' Error creando pago: {str(e)}')
            raise UserError(f'Error al crear pago: {str(e)}')

    def _reconciliar_pago_con_factura(self, pago, asiento):
        """ NUEVO MÉTODO - Reconcilia el pago con la factura usando el workflow correcto"""
        try:
            # Buscar las líneas a reconciliar
            lineas_pago = pago.line_ids.filtered(
                lambda l: l.account_id.account_type in ['asset_receivable', 'liability_payable']
            )

            lineas_factura = asiento.line_ids.filtered(
                lambda l: l.account_id.account_type in ['asset_receivable', 'liability_payable']
                          and l.partner_id == pago.partner_id
            )

            # Verificar que tengamos líneas para reconciliar
            if not lineas_pago or not lineas_factura:
                _logger.warning(
                    f' No se encontraron líneas para reconciliar - Pago: {pago.name}, Factura: {asiento.name}')
                return

            #  RECONCILIAR usando el método correcto
            lineas_a_reconciliar = lineas_pago + lineas_factura

            # Verificar compatibilidad de cuentas
            cuentas = lineas_a_reconciliar.mapped('account_id')
            if len(cuentas) == 1:  # Misma cuenta = se pueden reconciliar
                lineas_a_reconciliar.reconcile()
                _logger.info(f' Reconciliación exitosa: {pago.name} <-> {asiento.name}')
            else:
                _logger.warning(f' Cuentas diferentes, reconciliación manual requerida: {pago.name} <-> {asiento.name}')

        except Exception as e:
            _logger.error(f' Error en reconciliación: {str(e)}')
            # No fallar el proceso completo por error de reconciliación
            pass

    def _get_payment_method_line(self, payment_type):
        """ MODIFICADO - Usa journal_pago_id para obtener métodos de pago"""
        try:
            #  USAR journal_pago_id (diario bancario) para obtener métodos
            if payment_type == 'inbound':
                method_lines = self.journal_pago_id.inbound_payment_method_line_ids
            else:
                method_lines = self.journal_pago_id.outbound_payment_method_line_ids

            if not method_lines:
                raise UserError(
                    f'El diario bancario "{self.journal_pago_id.name}" no tiene métodos de pago '
                    f'configurados para {payment_type}. Configure al menos un método de pago.'
                )

            _logger.info(f' Métodos disponibles en {self.journal_pago_id.name}: '
                         f'{[l.payment_method_id.code for l in method_lines]}')

            # Buscar método preferido
            metodos_preferidos = ['electronic', 'bank_transfer', 'manual', 'check_printing', 'pdc']

            for codigo in metodos_preferidos:
                linea = method_lines.filtered(lambda l: l.payment_method_id.code == codigo)
                if linea:
                    _logger.info(f' Usando método: {codigo}')
                    return linea[0].id

            # Usar primero disponible
            _logger.info(f'🔄 Usando primer método: {method_lines[0].payment_method_id.code}')
            return method_lines[0].id

        except Exception as e:
            _logger.error(f' Error obteniendo método de pago: {str(e)}')
            raise UserError(f'Error obteniendo método de pago: {str(e)}')

    def action_cancelar(self):
        """Cancela la conciliación y resetea los datos"""
        self.ensure_one()

        if self.estado == 'completado':
            raise UserError('No se puede cancelar una conciliación completada.')

        # Verificar si hay pagos creados
        pagos_existentes = self.linea_ids.filtered('payment_id')
        if pagos_existentes:
            raise UserError(
                'No se puede cancelar la conciliación porque ya se crearon pagos. '
                'Cancele primero los pagos asociados.'
            )

        # Resetear líneas de conciliación
        for linea in self.linea_ids:
            linea.conciliado = False
            linea.asiento_id = False
            linea.es_automatico = False
            linea.diferencia_dias = 0
            linea.diferencia_monto = 0.0
            linea.tipo_coincidencia = 'sin_match'
            linea.algoritmo_usado = 'ninguno'

        # Cambiar estado
        self.estado = 'cancelado'

        _logger.info(f" Conciliación {self.name} cancelada")

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Conciliación Cancelada',
                'message': f'La conciliación {self.name} ha sido cancelada.',
                'type': 'warning',
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            }
        }

    def action_resetear_borrador(self):
        """Regresa la conciliación a estado borrador"""
        self.ensure_one()

        if self.estado == 'completado':
            pagos_existentes = self.linea_ids.filtered('payment_id')
            if pagos_existentes:
                raise UserError('No se puede resetear porque hay pagos creados.')

        self.estado = 'borrador'
        self.linea_ids.unlink()  # Limpiar líneas existentes

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Conciliación Reseteada',
                'message': 'La conciliación ha sido regresada a borrador.',
                'type': 'info',
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            }
        }

    def action_ver_extractos(self):
        """Abre la vista de extractos relacionados"""
        self.ensure_one()

        extractos = self.linea_ids.mapped('extracto_id')

        if not extractos:
            raise UserError('No hay extractos asociados a esta conciliación.')

        return {
            'name': f'Extractos - {self.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'santander.bank.statement',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', extractos.ids)],
            'context': {'search_default_fecha_movimiento': 1},
        }

    def action_ver_pagos(self):
        """Abre la vista de pagos creados"""
        self.ensure_one()

        pagos = self.linea_ids.mapped('payment_id').filtered(lambda p: p)

        if not pagos:
            raise UserError('No hay pagos creados para esta conciliación.')

        return {
            'name': f'Pagos - {self.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', pagos.ids)],
            'context': {'search_default_date': 1},
        }


#  Línea de conciliación con campos adicionales
class BankReconciliationLine(models.Model):
    _name = 'bank.reconciliation.line'
    _description = 'Línea de Conciliación Bancaria'

    reconciliation_id = fields.Many2one('bank.reconciliation', string='Conciliación',
                                        required=True, ondelete='cascade')

    # Referencias principales
    extracto_id = fields.Many2one('santander.bank.statement', string='Extracto Bancario',
                                  required=True)
    asiento_id = fields.Many2one('account.move', string='Factura/Asiento Contable')
    payment_id = fields.Many2one('account.payment', string='Pago Creado', readonly=True)

    # Estado de conciliación
    conciliado = fields.Boolean(string='Conciliado', default=False)
    es_automatico = fields.Boolean(string='Conciliación Automática', default=False)

    tipo_coincidencia = fields.Selection([
        ('pago_completo', 'Pago Completo'),
        ('pago_parcial', 'Pago Parcial'),
        ('sobrepago', 'Sobrepago'),
        ('sin_match', 'Sin Coincidencia')
    ], string='Tipo de Coincidencia', default='sin_match')

    #  Algoritmo usado para la coincidencia
    algoritmo_usado = fields.Selection([
        ('exacta', 'Coincidencia Exacta'),
        ('spei', 'Operación SPEI'),
        ('referencia', 'Por Referencia'),
        ('normal', 'Monto y Fecha'),
        ('ninguno', 'Sin Algoritmo')
    ], string='Algoritmo', default='ninguno', help='Algoritmo usado para encontrar la coincidencia')

    # Datos del extracto (para mostrar en vista)
    fecha_extracto = fields.Date(string='Fecha Extracto', related='extracto_id.fecha_movimiento')
    monto_extracto = fields.Float(string='Monto Extracto', related='extracto_id.importe')
    signo_extracto = fields.Selection(string='Tipo', related='extracto_id.signo')
    descripcion_extracto = fields.Char(string='Descripción', related='extracto_id.descripcion')
    referencia_extracto = fields.Char(string='Referencia', related='extracto_id.referencia')

    #  Campo banco para mejor vista
    banco_extracto = fields.Char(string='Banco', related='extracto_id.banco_participante')
    hora_extracto = fields.Char(string='Hora', related='extracto_id.hora_movimiento')

    # Datos del asiento - computed fields mejorados
    fecha_asiento = fields.Date(string='Fecha Factura', compute='_compute_asiento_data', store=True)
    monto_asiento = fields.Float(string='Total Factura', compute='_compute_asiento_data', store=True)
    saldo_pendiente = fields.Float(string='Saldo Pendiente', compute='_compute_asiento_data', store=True)
    numero_asiento = fields.Char(string='Número', compute='_compute_asiento_data', store=True)
    cliente_asiento = fields.Char(string='Cliente/Proveedor', compute='_compute_asiento_data', store=True)
    tipo_documento = fields.Selection([
        ('out_invoice', 'Factura Cliente'),
        ('in_invoice', 'Factura Proveedor'),
        ('out_refund', 'Nota Crédito Cliente'),
        ('in_refund', 'Nota Crédito Proveedor')
    ], string='Tipo Documento', compute='_compute_asiento_data', store=True)

    # Diferencias calculadas
    diferencia_dias = fields.Integer(string='Diferencia Días')
    diferencia_monto = fields.Float(string='Diferencia Monto')

    # Datos del pago creado
    numero_pago = fields.Char(string='Número Pago', compute='_compute_payment_data', store=True)
    estado_pago = fields.Selection([
        ('draft', 'Borrador'),
        ('posted', 'Validado'),
        ('sent', 'Enviado'),
        ('reconciled', 'Reconciliado'),
        ('cancelled', 'Cancelado')
    ], string='Estado Pago', compute='_compute_payment_data', store=True)

    # Comentarios
    notas = fields.Text(string='Notas')

    @api.depends('asiento_id')
    def _compute_asiento_data(self):
        """Calcula los datos del asiento contable"""
        for record in self:
            if record.asiento_id:
                record.fecha_asiento = record.asiento_id.invoice_date
                record.monto_asiento = float(record.asiento_id.amount_total) if record.asiento_id.amount_total else 0.0
                record.saldo_pendiente = float(
                    record.asiento_id.amount_residual) if record.asiento_id.amount_residual else 0.0
                record.numero_asiento = record.asiento_id.name or ''
                record.cliente_asiento = record.asiento_id.partner_id.name if record.asiento_id.partner_id else ''
                record.tipo_documento = record.asiento_id.move_type
            else:
                record.fecha_asiento = False
                record.monto_asiento = 0.0
                record.saldo_pendiente = 0.0
                record.numero_asiento = ''
                record.cliente_asiento = ''
                record.tipo_documento = False

    @api.depends('payment_id')
    def _compute_payment_data(self):
        """Calcula los datos del pago"""
        for record in self:
            if record.payment_id:
                record.numero_pago = f"PAGO-{record.payment_id.id}"
                record.estado_pago = record.payment_id.state or 'draft'
            else:
                record.numero_pago = ''
                record.estado_pago = False

    def action_conciliar_manual(self):
        """ Conciliación manual con mejor validación"""
        self.ensure_one()

        if not self.asiento_id:
            raise UserError('Debe seleccionar una factura/asiento contable antes de conciliar.')

        # Verificar compatibilidad
        if not self.reconciliation_id._son_compatibles(self.extracto_id, self.asiento_id):
            raise UserError('El tipo de extracto no es compatible con el tipo de documento seleccionado.')

        # Recalcular diferencias y tipo de coincidencia
        if self.asiento_id and self.extracto_id:
            self.diferencia_dias = abs((self.extracto_id.fecha_movimiento - self.asiento_id.invoice_date).days)
            self.diferencia_monto = abs(abs(self.extracto_id.importe) - abs(self.asiento_id.amount_residual))
            self.tipo_coincidencia = self.reconciliation_id._determinar_tipo_coincidencia(self.extracto_id,
                                                                                          self.asiento_id)

        self.conciliado = True
        self.es_automatico = False
        self.algoritmo_usado = 'manual'

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Conciliación Manual',
                'message': f'La línea ha sido marcada como conciliada manualmente.\nDiferencia: ${self.diferencia_monto:.2f} - {self.diferencia_dias} días',
                'type': 'success',
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            }
        }

    def action_deshacer_conciliacion(self):
        """Deshace la conciliación de la línea"""
        self.ensure_one()

        if self.payment_id:
            raise UserError(
                'Esta línea ya tiene un pago asociado. Para deshacer la conciliación debe cancelar primero el pago.')

        self.conciliado = False
        self.asiento_id = False
        self.es_automatico = False
        self.diferencia_dias = 0
        self.diferencia_monto = 0.0
        self.tipo_coincidencia = 'sin_match'
        self.algoritmo_usado = 'ninguno'

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Conciliación Deshecha',
                'message': 'La conciliación ha sido deshecha.',
                'type': 'info',
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            }
        }

    def action_ver_pago(self):
        """Abre el pago creado"""
        self.ensure_one()

        if not self.payment_id:
            raise UserError('No hay pago asociado a esta línea.')

        return {
            'name': 'Pago',
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment',
            'view_mode': 'form',
            'res_id': self.payment_id.id,
            'target': 'current',
        }

    def action_abrir_extracto(self):
        """Abre el extracto bancario asociado"""
        self.ensure_one()

        if not self.extracto_id:
            raise UserError('No hay extracto asociado a esta línea.')

        return {
            'name': 'Extracto Bancario',
            'type': 'ir.actions.act_window',
            'res_model': 'santander.bank.statement',
            'view_mode': 'form',
            'res_id': self.extracto_id.id,
            'target': 'current',
        }

    def action_abrir_factura(self):
        """Abre la factura asociada"""
        self.ensure_one()

        if not self.asiento_id:
            raise UserError('No hay factura asociada a esta línea.')

        return {
            'name': 'Factura/Asiento',
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.asiento_id.id,
            'target': 'current',
        }
