# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime
import logging

_logger = logging.getLogger(__name__)

class AccountMoveBatchBankInfo(models.Model):
    """Información del movimiento bancario asociado al lote"""
    _name = 'account.move.batch.bank.info'
    _description = 'Información Bancaria del Lote'

    batch_id = fields.Many2one(
        'account.move.batch',
        string='Lote',
        required=True,
        ondelete='cascade'
    )

    # Información del movimiento bancario
    bank_statement_id = fields.Many2one(
        'santander.bank.statement',
        string='Movimiento Bancario',
        related='batch_id.bank_statement_id',
        store=True
    )

    fecha_movimiento = fields.Date(
        string='Fecha Movimiento',
        related='bank_statement_id.fecha_movimiento',
        store=True
    )

    hora_movimiento = fields.Char(
        string='Hora',
        related='bank_statement_id.hora_movimiento',
        store=True
    )

    concepto = fields.Char(
        string='Concepto',
        related='bank_statement_id.concepto',
        store=True
    )

    referencia = fields.Char(
        string='Referencia Bancaria',
        related='bank_statement_id.referencia',
        store=True
    )

    importe = fields.Float(
        string='Importe',
        related='bank_statement_id.importe',
        store=True
    )

    signo = fields.Selection(
        related='bank_statement_id.signo',
        string='Tipo',
        store=True
    )

    numero_cuenta = fields.Char(
        string='Número de Cuenta',
        related='bank_statement_id.numero_cuenta',
        store=True
    )

    sucursal = fields.Char(
        string='Sucursal',
        related='bank_statement_id.sucursal',
        store=True
    )

class AccountMoveBatchLine(models.Model):
    """Líneas de desglose del lote - detalle de cada factura"""
    _name = 'account.move.batch.line'
    _description = 'Desglose de Facturas del Lote'
    _order = 'batch_id, invoice_id, sequence'

    # Relación con el lote
    batch_id = fields.Many2one(
        'account.move.batch',
        string='Lote',
        required=True,
        ondelete='cascade',
        index=True
    )

    sequence = fields.Integer(string='Secuencia', default=10)

    # Información de la factura
    invoice_id = fields.Many2one(
        'account.move',
        string='Factura',
        required=True,
        ondelete='restrict'
    )

    invoice_name = fields.Char(
        string='Número de Factura',
        related='invoice_id.name',
        store=True
    )

    invoice_date = fields.Date(
        string='Fecha Factura',
        related='invoice_id.invoice_date',
        store=True
    )

    # Información del partner
    partner_id = fields.Many2one(
        'res.partner',
        string='Cliente/Proveedor',
        related='invoice_id.partner_id',
        store=True
    )

    # Información del producto/servicio
    product_id = fields.Many2one(
        'product.product',
        string='Producto',
    )

    product_name = fields.Char(string='Descripción')

    quantity = fields.Float(string='Cantidad', digits='Product Unit of Measure')

    price_unit = fields.Float(string='Precio Unitario', digits='Product Price')

    # Montos
    price_subtotal = fields.Monetary(
        string='Subtotal',
        currency_field='currency_id',
        help='Monto antes de impuestos'
    )

    tax_amount = fields.Monetary(
        string='IVA',
        currency_field='currency_id',
        help='Monto de impuestos'
    )

    price_total = fields.Monetary(
        string='Total',
        currency_field='currency_id',
        help='Monto con impuestos incluidos'
    )

    # Información contable
    account_id = fields.Many2one(
        'account.account',
        string='Cuenta Contable'
    )

    account_code = fields.Char(
        string='Código de Cuenta',
        related='account_id.code',
        store=True
    )

    account_name = fields.Char(
        string='Nombre de Cuenta',
        related='account_id.name',
        store=True
    )

    # Tipo de movimiento
    move_type = fields.Selection(
        [
            ('debit', 'Cargo'),
            ('credit', 'Abono')
        ],
        string='Tipo de Movimiento',
        compute='_compute_move_type',
        store=True
    )

    debit = fields.Monetary(
        string='Cargo',
        currency_field='currency_id'
    )

    credit = fields.Monetary(
        string='Abono',
        currency_field='currency_id'
    )

    # Información adicional
    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        related='batch_id.currency_id',
        store=True
    )

    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        related='batch_id.company_id',
        store=True
    )

    # Campos calculados
    tax_ids = fields.Many2many(
        'account.tax',
        string='Impuestos'
    )

    tax_rate = fields.Float(
        string='% Impuesto',
        compute='_compute_tax_rate',
        store=True,
        digits=(12, 2)
    )

    @api.depends('batch_id.partner_type', 'price_total')
    def _compute_move_type(self):
        """Calcula si es cargo o abono según el tipo de partner"""
        for line in self:
            if line.batch_id.partner_type == 'customer':
                line.move_type = 'debit'  # Cargo para clientes
                line.debit = line.price_total
                line.credit = 0
            else:
                line.move_type = 'credit'  # Abono para proveedores
                line.debit = 0
                line.credit = line.price_total

    @api.depends('tax_ids', 'price_subtotal', 'tax_amount')
    def _compute_tax_rate(self):
        """Calcula el porcentaje de impuesto"""
        for line in self:
            if line.price_subtotal and line.tax_amount:
                line.tax_rate = (line.tax_amount / line.price_subtotal) * 100
            elif line.tax_ids:
                line.tax_rate = sum(line.tax_ids.mapped('amount'))
            else:
                line.tax_rate = 0.0

class AccountMoveBatch(models.Model):
    """Modelo para lotes de asientos contables"""
    _name = 'account.move.batch'
    _description = 'Lote de Asientos Contables'
    _order = 'create_date desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Número de Lote',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('Nuevo')
    )

    partner_id = fields.Many2one(
        'res.partner',
        string='Proveedor/Cliente',
        required=True,
        readonly=True,
        states={'draft': [('readonly', False)]},
        tracking=True
    )

    partner_type = fields.Selection(
        [('customer', 'Cliente'), ('supplier', 'Proveedor')],
        string='Tipo',
        required=True,
        readonly=True,
        states={'draft': [('readonly', False)]}
    )

    move_ids = fields.Many2many(
        'account.move',
        'account_move_batch_rel',
        'batch_id',
        'move_id',
        string='Facturas',
        domain="[('partner_id', '=', partner_id), ('state', '=', 'posted'), ('payment_state', 'in', ['not_paid', 'partial'])]",
        readonly=True,
        states={'draft': [('readonly', False)]}
    )

    move_count = fields.Integer(
        string='# Facturas',
        compute='_compute_move_count',
        store=True
    )

    amount_total = fields.Monetary(
        string='Total del Lote',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id'
    )

    amount_residual = fields.Monetary(
        string='Saldo Pendiente',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id'
    )

    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        default=lambda self: self.env.company.currency_id,
        required=True
    )

    state = fields.Selection(
        [
            ('draft', 'Borrador'),
            ('confirmed', 'Confirmado'),
            ('paid', 'Pagado'),
            ('cancelled', 'Cancelado')
        ],
        string='Estado',
        default='draft',
        required=True,
        tracking=True
    )

    payment_mode = fields.Selection(
        [
            ('immediate', 'Liquidación Inmediata'),
            ('scheduled', 'Liquidación Programada')
        ],
        string='Modo de Pago',
        required=True,
        readonly=True,
        states={'draft': [('readonly', False)]},
        default='immediate'
    )

    bank_statement_id = fields.Many2one(
        'santander.bank.statement',
        string='Movimiento Bancario',
        domain="[('procesado', '=', 'pendiente')]",
        readonly=True,
        states={'draft': [('readonly', False)]}
    )

    scheduled_payment_date = fields.Date(
        string='Fecha de Pago Programada',
        readonly=True,
        states={'draft': [('readonly', False)]}
    )

    payment_id = fields.Many2one(
        'account.payment',
        string='Pago Generado',
        readonly=True,
        copy=False
    )

    notes = fields.Text(string='Notas')

    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        required=True,
        default=lambda self: self.env.company
    )

    # CAMPOS para desglose
    batch_line_ids = fields.One2many(
        'account.move.batch.line',
        'batch_id',
        string='Desglose de Facturas',
        readonly=True
    )

    bank_info_id = fields.One2many(
        'account.move.batch.bank.info',
        'batch_id',
        string='Información Bancaria'
    )

    # Totales calculados del desglose
    total_subtotal = fields.Monetary(
        string='Total sin IVA',
        compute='_compute_breakdown_totals',
        store=True,
        currency_field='currency_id'
    )

    total_tax = fields.Monetary(
        string='Total IVA',
        compute='_compute_breakdown_totals',
        store=True,
        currency_field='currency_id'
    )

    total_with_tax = fields.Monetary(
        string='Total con IVA',
        compute='_compute_breakdown_totals',
        store=True,
        currency_field='currency_id'
    )

    # Campo para IDs de movimientos bancarios filtrados
    matching_bank_statement_ids = fields.Many2many(
        'santander.bank.statement',
        'account_batch_matching_bank_rel',
        'batch_id',
        'statement_id',
        string='Movimientos Coincidentes',
        compute='_compute_matching_bank_statements',
        store=False
    )

    @api.depends('amount_residual', 'move_ids')
    def _compute_matching_bank_statements(self):
        """Calcula los movimientos bancarios que coinciden con el total del lote"""
        for batch in self:
            if not batch.amount_residual:
                batch.matching_bank_statement_ids = False
                continue

            target_amount = abs(batch.amount_residual)
            tolerance = 0.01

            BankStatement = self.env['santander.bank.statement']

            # Buscar movimientos coincidentes
            domain = [
                ('procesado', '=', 'pendiente'),
                '|',
                '&',
                ('importe', '>=', target_amount - tolerance),
                ('importe', '<=', target_amount + tolerance),
                '&',
                ('importe', '>=', -target_amount - tolerance),
                ('importe', '<=', -target_amount + tolerance),
            ]

            matching = BankStatement.search(domain)
            batch.matching_bank_statement_ids = matching

    @api.model
    def create(self, vals):
        """Genera secuencia automática para el lote"""
        if vals.get('name', _('Nuevo')) == _('Nuevo'):
            vals['name'] = self.env['ir.sequence'].next_by_code('account.move.batch') or _('Nuevo')
        return super(AccountMoveBatch, self).create(vals)

    @api.depends('move_ids')
    def _compute_move_count(self):
        """Calcula el número de facturas en el lote"""
        for batch in self:
            batch.move_count = len(batch.move_ids)

    @api.depends('move_ids', 'move_ids.amount_total', 'move_ids.amount_residual')
    def _compute_amounts(self):
        """Calcula montos totales del lote"""
        for batch in self:
            batch.amount_total = sum(batch.move_ids.mapped('amount_total'))
            batch.amount_residual = sum(batch.move_ids.mapped('amount_residual'))

    @api.depends('batch_line_ids', 'batch_line_ids.price_subtotal',
                 'batch_line_ids.tax_amount', 'batch_line_ids.price_total')
    def _compute_breakdown_totals(self):
        """Calcula los totales del desglose"""
        for batch in self:
            batch.total_subtotal = sum(batch.batch_line_ids.mapped('price_subtotal'))
            batch.total_tax = sum(batch.batch_line_ids.mapped('tax_amount'))
            batch.total_with_tax = sum(batch.batch_line_ids.mapped('price_total'))

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        """Limpia las facturas cuando cambia el partner"""
        if self.partner_id:
            self.move_ids = [(5, 0, 0)]

    @api.onchange('payment_mode')
    def _onchange_payment_mode(self):
        """Limpia campos según el modo de pago"""
        if self.payment_mode == 'immediate':
            self.scheduled_payment_date = False
        else:
            self.bank_statement_id = False

    @api.constrains('move_ids')
    def _check_moves_same_partner(self):
        """Valida que todas las facturas pertenezcan al mismo partner"""
        for batch in self:
            if batch.move_ids:
                partners = batch.move_ids.mapped('partner_id')
                if len(partners) > 1:
                    raise ValidationError(
                        _('Todas las facturas deben pertenecer al mismo proveedor/cliente.\n'
                          'Partner actual: %s\n'
                          'Partners encontrados: %s') % (
                            batch.partner_id.name,
                            ', '.join(partners.mapped('name'))
                        )
                    )

                if partners and partners[0] != batch.partner_id:
                    raise ValidationError(
                        _('Las facturas seleccionadas no pertenecen al partner del lote.\n'
                          'Partner del lote: %s\n'
                          'Partner de las facturas: %s') % (
                            batch.partner_id.name,
                            partners[0].name
                        )
                    )

    @api.constrains('move_ids')
    def _check_moves_not_empty(self):
        """Valida que el lote tenga al menos una factura"""
        for batch in self:
            if batch.state != 'draft' and not batch.move_ids:
                raise ValidationError(_('El lote debe contener al menos una factura.'))

    @api.constrains('payment_mode', 'bank_statement_id', 'scheduled_payment_date')
    def _check_payment_mode_fields(self):
        """Valida campos requeridos según el modo de pago"""
        for batch in self:
            if batch.state != 'draft':
                if batch.payment_mode == 'immediate' and not batch.bank_statement_id:
                    raise ValidationError(
                        _('Para liquidación inmediata debe seleccionar un movimiento bancario.')
                    )
                elif batch.payment_mode == 'scheduled' and not batch.scheduled_payment_date:
                    raise ValidationError(
                        _('Para liquidación programada debe especificar una fecha de pago.')
                    )

    def action_confirm(self):
        """Confirma el lote - NO crea facturas, solo desglose"""
        for batch in self:
            if not batch.move_ids:
                raise UserError(_('Debe agregar al menos una factura al lote.'))

            # Validar modo de pago
            if batch.payment_mode == 'immediate' and not batch.bank_statement_id:
                raise UserError(_('Debe seleccionar un movimiento bancario para liquidación inmediata.'))
            elif batch.payment_mode == 'scheduled' and not batch.scheduled_payment_date:
                raise UserError(_('Debe especificar una fecha de pago para liquidación programada.'))

            # Crear desglose detallado
            batch._create_batch_breakdown()

            # Crear información bancaria
            if batch.bank_statement_id:
                batch._create_bank_info()

            # Si es liquidación inmediata, crear el pago automáticamente
            if batch.payment_mode == 'immediate':
                batch.action_create_payment()
            else:
                batch.state = 'confirmed'
                batch.message_post(body=_('Lote confirmado con %s facturas por un total de %s') % (
                    batch.move_count,
                    batch.amount_total
                ))

    def _create_batch_breakdown(self):
        """Crea el desglose detallado de todas las facturas del lote"""
        self.ensure_one()

        _logger.info('=== Creando desglose para lote %s con %s facturas ===' % (
            self.name, len(self.move_ids)
        ))

        # Limpiar desglose anterior si existe
        if self.batch_line_ids:
            self.batch_line_ids.unlink()

        BatchLine = self.env['account.move.batch.line']
        sequence = 10
        lines_created = 0

        for invoice in self.move_ids:
            _logger.info('Procesando factura: %s' % invoice.name)

            # Procesar cada línea de la factura
            for inv_line in invoice.invoice_line_ids:
                # Calcular montos
                price_subtotal = inv_line.price_subtotal
                tax_amount = inv_line.price_total - inv_line.price_subtotal
                price_total = inv_line.price_total

                # Obtener nombre de la línea de forma segura
                line_name = inv_line.name or ''
                if inv_line.product_id:
                    line_name = line_name or inv_line.product_id.name or 'Sin descripción'
                else:
                    line_name = line_name or 'Sin descripción'

                _logger.info('  Línea: %s | Subtotal: %s | IVA: %s | Total: %s' % (
                    line_name[:50] if line_name else 'Sin nombre',
                    price_subtotal,
                    tax_amount,
                    price_total
                ))

                # Crear línea de desglose
                try:
                    BatchLine.create({
                        'batch_id': self.id,
                        'sequence': sequence,
                        'invoice_id': invoice.id,
                        'product_id': inv_line.product_id.id if inv_line.product_id else False,
                        'product_name': line_name,
                        'quantity': inv_line.quantity,
                        'price_unit': inv_line.price_unit,
                        'price_subtotal': price_subtotal,
                        'tax_amount': tax_amount,
                        'price_total': price_total,
                        'account_id': inv_line.account_id.id,
                        'tax_ids': [(6, 0, inv_line.tax_ids.ids)],
                    })

                    sequence += 10
                    lines_created += 1

                except Exception as e:
                    _logger.error('Error al crear línea de desglose: %s' % str(e))
                    continue

        _logger.info('=== Desglose completado: %s líneas creadas ===' % lines_created)

        # Verificar que se crearon líneas
        if lines_created == 0:
            raise UserError(_('No se pudieron crear líneas de desglose. Revise los logs del servidor.'))

    def _create_bank_info(self):
        """Crea el registro de información bancaria"""
        self.ensure_one()

        if not self.bank_statement_id:
            return

        # Limpiar info anterior si existe
        if self.bank_info_id:
            self.bank_info_id.unlink()

        self.env['account.move.batch.bank.info'].create({
            'batch_id': self.id,
        })

        _logger.info('Información bancaria creada para lote %s' % self.name)

    def action_create_payment(self):
        """Crea el pago y lo aplica directamente a las facturas originales"""
        self.ensure_one()

        if self.state == 'paid':
            raise UserError(_('El lote ya tiene un pago registrado.'))

        payment_vals = self._prepare_payment_vals()
        payment = self.env['account.payment'].create(payment_vals)

        # Confirmar el pago
        payment.action_post()

        self.payment_id = payment.id

        # Si es liquidación inmediata con movimiento bancario, marcar como procesado
        if self.payment_mode == 'immediate' and self.bank_statement_id:
            self.bank_statement_id.write({
                'procesado': 'procesado',
            })

        # Conciliar las facturas originales con el pago
        self._reconcile_original_invoices()

        self.state = 'paid'

        # Verificar cuántas facturas se pagaron
        paid_invoices = self.move_ids.filtered(lambda m: m.payment_state in ['paid', 'in_payment'])

        self.message_post(body=_('Pago creado: %s por %s %s.<br/>Facturas pagadas: %s de %s') % (
            payment.name,
            payment.amount,
            payment.currency_id.symbol,
            len(paid_invoices),
            len(self.move_ids)
        ))

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment',
            'res_id': payment.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _prepare_payment_vals(self):
        """Prepara los valores para crear el pago"""
        self.ensure_one()

        payment_type = 'inbound' if self.partner_type == 'customer' else 'outbound'
        partner_type = self.partner_type

        # Usar la fecha del movimiento bancario si existe, sino la fecha programada o hoy
        if self.bank_statement_id and self.bank_statement_id.fecha_movimiento:
            payment_date = self.bank_statement_id.fecha_movimiento
        elif self.scheduled_payment_date:
            payment_date = self.scheduled_payment_date
        else:
            payment_date = fields.Date.today()

        # Obtener el monto del movimiento bancario o del total del lote
        if self.bank_statement_id and self.bank_statement_id.importe:
            amount = abs(self.bank_statement_id.importe)
        else:
            amount = self.amount_residual

        # Obtener diario bancario
        journal = self._get_payment_journal()

        payment_vals = {
            'payment_type': payment_type,
            'partner_type': partner_type,
            'partner_id': self.partner_id.id,
            'amount': amount,
            'currency_id': self.currency_id.id,
            'date': payment_date,
            'ref': _('Pago Lote %s') % self.name,
            'journal_id': journal.id,
        }

        # Si hay movimiento bancario, agregar la referencia
        if self.bank_statement_id:
            payment_vals['bank_reference'] = self.bank_statement_id.referencia or ''

        return payment_vals

    def _get_payment_journal(self):
        """Obtiene el diario de pago"""
        journal = self.env['account.journal'].search([
            ('type', '=', 'bank'),
            ('company_id', '=', self.company_id.id)
        ], limit=1)

        if not journal:
            raise UserError(_('No se encontró un diario bancario. Configure uno primero.'))

        return journal

    def _reconcile_original_invoices(self):
        """Concilia las facturas originales del lote con el pago existente"""
        self.ensure_one()

        if not self.payment_id:
            _logger.warning('No hay pago asociado para conciliar')
            return

        # Obtener la cuenta por cobrar/pagar
        if self.partner_type == 'customer':
            account = self.partner_id.property_account_receivable_id
        else:
            account = self.partner_id.property_account_payable_id

        # Obtener asiento del pago
        payment_move = self.payment_id.move_id
        if not payment_move:
            _logger.error('El pago no tiene asiento contable asociado')
            return

        payment_lines = payment_move.line_ids.filtered(
            lambda l: l.account_id == account and not l.reconciled
        )

        if not payment_lines:
            _logger.warning('No hay líneas de pago disponibles para conciliar')
            return

        _logger.info('Líneas de pago encontradas: %s' % len(payment_lines))

        # Para cada factura original, conciliar con el pago
        for invoice in self.move_ids:
            if invoice.payment_state in ['paid', 'in_payment']:
                _logger.info('Factura %s ya está pagada' % invoice.name)
                continue

            invoice_lines = invoice.line_ids.filtered(
                lambda l: l.account_id == account and not l.reconciled
            )

            if not invoice_lines:
                _logger.warning('No hay líneas pendientes en factura %s' % invoice.name)
                continue

            try:
                lines_to_reconcile = payment_lines | invoice_lines
                lines_to_reconcile.reconcile()

                invoice.invalidate_recordset(['payment_state', 'amount_residual'])

                _logger.info('✓ Factura %s conciliada. Estado: %s' % (
                    invoice.name, invoice.payment_state
                ))

            except Exception as e:
                _logger.error('✗ Error al conciliar factura %s: %s' % (invoice.name, str(e)))
                continue

    def action_cancel(self):
        """Cancela el lote"""
        for batch in self:
            if batch.payment_id and batch.payment_id.state == 'posted':
                raise UserError(_('No se puede cancelar un lote con pago confirmado. Cancele primero el pago.'))

            # Eliminar el pago si existe y está en borrador
            if batch.payment_id and batch.payment_id.state == 'draft':
                batch.payment_id.unlink()

            # Eliminar desglose
            if batch.batch_line_ids:
                batch.batch_line_ids.unlink()

            # Eliminar info bancaria
            if batch.bank_info_id:
                batch.bank_info_id.unlink()

            # Si había movimiento bancario, regresarlo a pendiente
            if batch.bank_statement_id and batch.bank_statement_id.procesado == 'procesado':
                batch.bank_statement_id.write({'procesado': 'pendiente'})

            batch.state = 'cancelled'

    def action_reset_to_draft(self):
        """Regresa el lote a borrador"""
        for batch in self:
            if batch.payment_id:
                raise UserError(_('No se puede regresar a borrador un lote con pago generado.'))
            batch.state = 'draft'

    def action_view_moves(self):
        """Abre vista de facturas del lote"""
        self.ensure_one()
        return {
            'name': _('Facturas del Lote'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', self.move_ids.ids)],
            'context': {'create': False},
        }

    def action_view_payment(self):
        """Abre vista del pago"""
        self.ensure_one()
        if not self.payment_id:
            raise UserError(_('No hay pago asociado a este lote.'))

        return {
            'name': _('Pago del Lote'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment',
            'res_id': self.payment_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_find_matching_bank_statement(self):
        """Busca automáticamente un movimiento bancario que coincida con el total del lote"""
        self.ensure_one()

        if not self.amount_residual:
            raise UserError(_('El lote no tiene facturas agregadas o el monto es 0.'))

        # Buscar movimiento bancario con importe que coincida con el total del lote
        target_amount = abs(self.amount_residual)

        # Buscar con tolerancia de 0.01 para manejar redondeos
        tolerance = 0.01

        BankStatement = self.env['santander.bank.statement']

        # Construir dominio de búsqueda
        domain = [
            ('procesado', '=', 'pendiente'),
            ('importe', '>=', target_amount - tolerance),
            ('importe', '<=', target_amount + tolerance),
        ]

        # Buscar movimientos coincidentes
        matching_statements = BankStatement.search(domain, order='fecha_movimiento desc')

        # Si no encuentra, intentar con valor negativo
        if not matching_statements:
            domain_negative = [
                ('procesado', '=', 'pendiente'),
                ('importe', '>=', -target_amount - tolerance),
                ('importe', '<=', -target_amount + tolerance),
            ]
            matching_statements = BankStatement.search(domain_negative, order='fecha_movimiento desc')

        # CASO 1: No se encontró ningún movimiento
        if not matching_statements:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('No se encontró coincidencia'),
                    'message': _(
                        'No hay movimientos bancarios pendientes que coincidan con %s %s. Por favor, búsquelo manualmente.') % (
                                   target_amount, self.currency_id.symbol
                               ),
                    'type': 'warning',
                    'sticky': False,
                    'next': {'type': 'ir.actions.act_window_close'},
                }
            }

        # CASO 2: Se encontró exactamente 1 movimiento - Asignar automáticamente
        elif len(matching_statements) == 1:
            self.bank_statement_id = matching_statements[0]

            self.message_post(body=_(
                '✓ Movimiento bancario asignado automáticamente:<br/>'
                '• Fecha: %s<br/>'
                '• Concepto: %s<br/>'
                '• Importe: %s %s<br/>'
                '• Referencia: %s'
            ) % (
                                       matching_statements[0].fecha_movimiento or '',
                                       matching_statements[0].concepto or '',
                                       matching_statements[0].importe,
                                       self.currency_id.symbol,
                                       matching_statements[0].referencia or ''
                                   ))

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('✓ Movimiento Encontrado'),
                    'message': _('Se asignó automáticamente el movimiento bancario de %s %s del %s') % (
                        matching_statements[0].importe,
                        self.currency_id.symbol,
                        matching_statements[0].fecha_movimiento or ''
                    ),
                    'type': 'success',
                    'sticky': False,
                }
            }

        # CASO 3: Se encontraron múltiples movimientos - Filtrar el combobox
        else:
            # Actualizar el dominio del campo para mostrar solo los coincidentes
            self.write({
                'bank_statement_id': False,  # Limpiar selección actual
            })

            # Crear mensaje informativo
            self.message_post(body=_(
                '🔍 Se encontraron %s movimientos bancarios coincidentes con %s %s.<br/>'
                'El selector ha sido filtrado para mostrar solo estas opciones.'
            ) % (len(matching_statements), target_amount, self.currency_id.symbol))

            # Retornar acción que actualiza la vista con el filtro aplicado
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('🔍 Múltiples Coincidencias'),
                    'message': _('Se encontraron %s movimientos. Seleccione uno del combobox filtrado.') % len(
                        matching_statements),
                    'type': 'info',
                    'sticky': True,
                }
            }

class AccountMoveBatchWizard(models.TransientModel):
    _name = 'account.move.batch.wizard'
    _description = 'Asistente para Crear Lote de Facturas'

    partner_id = fields.Many2one(
        'res.partner',
        string='Proveedor/Cliente',
        required=True
    )

    partner_type = fields.Selection(
        [('customer', 'Cliente'), ('supplier', 'Proveedor')],
        string='Tipo',
        required=True
    )

    move_ids = fields.Many2many(
        'account.move',
        string='Facturas Seleccionadas',
        required=True
    )

    payment_mode = fields.Selection(
        [
            ('immediate', 'Liquidación Inmediata'),
            ('scheduled', 'Liquidación Programada')
        ],
        string='Modo de Pago',
        required=True,
        default='immediate'
    )

    bank_statement_id = fields.Many2one(
        'santander.bank.statement',
        string='Movimiento Bancario',
        domain="[('procesado', '=', 'pendiente')]"
    )

    scheduled_payment_date = fields.Date(string='Fecha de Pago Programada')

    @api.model
    def default_get(self, fields_list):
        """Obtiene facturas seleccionadas desde el contexto"""
        res = super(AccountMoveBatchWizard, self).default_get(fields_list)

        active_ids = self.env.context.get('active_ids', [])
        moves = self.env['account.move'].browse(active_ids)

        if not moves:
            raise UserError(_('Debe seleccionar al menos una factura.'))

        # Validar que todas sean del mismo partner
        partners = moves.mapped('partner_id')
        if len(partners) > 1:
            raise UserError(
                _('Todas las facturas deben ser del mismo proveedor/cliente.\n'
                  'Partners encontrados: %s') % ', '.join(partners.mapped('name'))
            )

        # Validar que estén confirmadas y no pagadas
        invalid_moves = moves.filtered(
            lambda m: m.state != 'posted' or m.payment_state not in ['not_paid', 'partial']
        )
        if invalid_moves:
            raise UserError(
                _('Solo se pueden incluir facturas confirmadas y no pagadas completamente.')
            )

        res.update({
            'partner_id': partners[0].id,
            'partner_type': 'customer' if moves[0].move_type == 'out_invoice' else 'supplier',
            'move_ids': [(6, 0, moves.ids)],
        })

        return res

    def action_create_batch(self):
        """Crea el lote con las facturas seleccionadas"""
        self.ensure_one()

        batch_vals = {
            'partner_id': self.partner_id.id,
            'partner_type': self.partner_type,
            'move_ids': [(6, 0, self.move_ids.ids)],
            'payment_mode': self.payment_mode,
            'bank_statement_id': self.bank_statement_id.id if self.bank_statement_id else False,
            'scheduled_payment_date': self.scheduled_payment_date,
        }

        batch = self.env['account.move.batch'].create(batch_vals)

        return {
            'name': _('Lote de Facturas'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move.batch',
            'res_id': batch.id,
            'view_mode': 'form',
            'target': 'current',
        }
