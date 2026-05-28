

from odoo import api, fields, models


class TicketMonitorAudit(models.Model):
    _name = 'contabilidad_kuale.ticket_monitor_audit'
    _description = 'Gestión y Monitoreo de tickets'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    company_id = fields.Many2one(
        'res.company',
        string='Compañia',
        domain="[('id', 'not in', child_company_ids)]"
    )
    branch_id = fields.Many2one(
        'res.company',
        string='Sucursal',
        domain="['|', ('parent_id', '=', company_id), ('id', '=', company_id)]"
    )

    audit_status = fields.Selection([
        ('sistema', 'En Sistema'),
        ('auditoria', 'En Auditoria'),
        ('iva', 'IVA'),
        ('monto', 'Monto'),
        ('pago', 'Forma dePago'),
        ('descuento', 'Descuento'),
    ], string='Estatus auditoria',default='sistema')
    audit_ticket_status = fields.Selection([
        ('0', 'Cerrado'),
        ('1', 'Abierto'),
        ('2', 'En espera'),
    ], string='Estatus del ticket en auditoria por sistema', default='1')

    motive = fields.Text(string='Motivo')

    ticket_folio = fields.Char(string='Numero de Ticket')
    date = fields.Datetime(string='Fecha del ticket')
    closed_date = fields.Datetime(string='Fecha de cierre del ticket', help='fecha de cierre en el sistema del ticket, si el ticket fue modificado se marca la hora del cierre en auditoria')
    closing_time = fields.Char(string="Tiempo abierto",compute="_compute_closing_time", store=True)
    difference = fields.Float(string='Diferencia',digits=(16, 6))
    # Datos originales de ticket
    ticket_payment_method = fields.Many2one('cfdi.clavemetododepago', string='Metodo de pago del ticket')
    ticket_payment_type = fields.Many2one('cfdi.claveformadepago', string='Forma de pago del ticket')
    ticket_iva = fields.Char(string='IVA')
    ticket_total = fields.Float(string='Total',digits=(16, 6))
    ticket_subtotal = fields.Float(string='Subtotal',digits=(16, 6))
    ticket_discount = fields.Float(string='Descuento',digits=(16, 6))
    ticket_product_line = fields.One2many('contabilidad_kuale.ticket_monitor_line',
                                          'ticket_monitor_audit_id',
                                          string='Productos')

    cashier = fields.Many2one('hr.employee', string='Cajero inicial',
                              help="Empleado asociado que abrio la venta de mostrador")

    ticket_discount_ids = fields.Many2many(
        'contabilidad_kuale.ticket_discount',
        'ticket_audit_discount_rel',  # Nombre corto para evitar error de longitud
        'audit_id', 'discount_id',
        string='Descuentos aplicados',
        domain="[('active', '=', True)]"
    )

    ticket_payments_ids = fields.One2many(
        'contabilidad_kuale.ticket_monitor_payments',
        'ticket_monitor_payment_audit_id',
        string='Desglose de pago'
    )

    ticket_discount_authorized = fields.Many2one(
        'hr.employee',
        string='Autorizó descuento (original)'
    )

    ticket_void_authorized = fields.Many2one('hr.employee', string='Cancelación autorizada por', help="Empleado asociado a la autorización de la cancelacion de un producto en ticket")
    ticket_reprint_number = fields.Integer(string='Numero de reimpresión de ticket', help='Información general (advertencia si el ticket pasa las 2 reimpresiones)')

    # Datos tras auditoria
    audit_payment_type = fields.Many2one('cfdi.claveformadepago', string='Forma de pago')
    audit_payment_method = fields.Many2one('cfdi.clavemetododepago', string='Metodo de pago')
    audit_iva = fields.Float(string='IVA',digits=(16, 6))
    audit_total = fields.Float(string='Total',digits=(16, 6))
    audit_subtotal = fields.Float(string='Subtotal',digits=(16, 6))
    audit_discount = fields.Float(string='Descuento',digits=(16, 6))
    audit_product_line = fields.One2many('contabilidad_kuale.ticket_monitor_line',
                                         'ticket_audit_id',
                                         string='Productos')
    closing_cashier = fields.Many2one('hr.employee', string='Cajero final',
                                      help="Empleado asociado que cerro la venta de mostrador")

    sell_type_code = fields.Char(string='Código Tipo de Venta', compute='_compute_sell_type_code')
    eoi_text = fields.Char(string='EOI', compute='_compute_eoi_text')

    @api.depends('ticket_folio', 'company_id', 'branch_id')
    def _compute_sell_type_code(self):
        for rec in self:
            if rec.ticket_folio and rec.company_id and rec.branch_id:
                ticket = self.env['contabilidad_kuale.ticket_monitor'].sudo().search([
                    ('ticket_folio', '=', rec.ticket_folio),
                    ('company_id', '=', rec.company_id.id),
                    ('branch_id', '=', rec.branch_id.id)
                ], limit=1)
                rec.sell_type_code = ticket.sell_type.clave if ticket and ticket.sell_type else False
            else:
                rec.sell_type_code = False

    def _compute_eoi_text(self):
        for rec in self:
            rec.eoi_text = 'EOI'

    audit_discount_ids = fields.Many2many(
        'contabilidad_kuale.ticket_discount',
        'audit_discount_rel',  # Nombre corto para tabla intermedia
        'audit_id', 'discount_id',
        string='Descuentos aplicados',
        domain="[('active', '=', True)]"
    )
    audit_discount_authorized = fields.Many2one(
        'hr.employee',
        string='Autorizó descuento (auditado)'
    )

    audit_payments_ids = fields.One2many(
        'contabilidad_kuale.ticket_monitor_payments',
        'ticket_payment_audit_id',
        string='Desglose de pago'
    )
    audit_void_authorized = fields.Many2one('hr.employee', string='Cancelación autorizada por',
                                             help="Empleado asociado a la autorización de la cancelacion de un producto en ticket")
    audit_reprint_number = fields.Integer(string='Numero de reimpresión de ticket',
                                           help='Información general (advertencia si el ticket pasa las 2 reimpresiones)')

    def write(self, vals):
        res = super(TicketMonitorAudit, self).write(vals)

        if 'ticket_folio' in vals and 'company_id' in vals and 'branch_id' in vals:
            sudo_env = self.sudo().with_context(allowed_company_ids=[vals['company_id'], vals['branch_id']])
            ticket = sudo_env.env['contabilidad_kuale.ticket_monitor'].search([
                ('ticket_folio', '=', vals['ticket_folio']),
                ('company_id', '=', vals['company_id']),
                ('branch_id', '=', vals['branch_id'])
            ], limit=1)

            if ticket:
                total = self.audit_total
                sudo_env.write({
                    'date': ticket.date,
                    'ticket_payment_method': ticket.payment_method.id,
                    'ticket_payment_type': ticket.payment_type.id,
                    'ticket_iva': ticket.iva,
                    'ticket_total': ticket.total,
                    'ticket_subtotal': ticket.subtotal,
                    'ticket_discount': ticket.discount,
                    'ticket_discount_authorized': ticket.discount_authorized.id if ticket.discount_authorized else None,
                    'cashier': ticket.cashier.id,
                    'ticket_discount_ids': [(6, 0, ticket.discount_ids.ids)] if ticket.discount_ids else [(6, 0, [])],
                    'ticket_void_authorized': ticket.void_authorized.id if ticket.void_authorized else None,
                    'ticket_reprint_number': ticket.reprint_number,
                    'difference': total - ticket.total,
                    'ticket_product_line': [(5, 0, 0)] + [
                        (0, 0, {
                            'third_party_id': prod.third_party_id,
                            'quantity': prod.quantity,
                            'unit_price': prod.unit_price,
                            'discount': prod.discount,
                            'subtotal': prod.subtotal,
                        }) for prod in ticket.product_line
                    ],
                    'ticket_payments_ids': [(5, 0, 0)] + [
                        (0, 0, {
                            'payment_type': pay.payment_type.id,
                            'amount': pay.amount,
                        }) for pay in ticket.payments_ids
                    ],
                })

        return res

    @api.model
    def create(self, vals):
        record = super(TicketMonitorAudit, self).create(vals)
        if 'ticket_folio' in vals and 'company_id' in vals and 'branch_id' in vals:
            sudo_env = record.sudo().with_context(allowed_company_ids=[vals['company_id'], vals['branch_id']])
            ticket = sudo_env.env['contabilidad_kuale.ticket_monitor'].search([
                ('ticket_folio', '=', vals['ticket_folio']),
                ('company_id', '=', vals['company_id']),
                ('branch_id', '=', vals['branch_id'])
            ], limit=1)

            if ticket:
                total = record.audit_total
                ticket_product_lines = [
                    (0, 0, {
                        'third_party_id': prod.third_party_id,
                        'quantity': prod.quantity,
                        'unit_price': prod.unit_price,
                        'discount': prod.discount,
                        'subtotal': prod.subtotal,
                    }) for prod in ticket.product_line
                ]
                ticket_payment_lines = [
                    (0, 0, {
                        'payment_type': pay.payment_type.id,
                        'amount': pay.amount,
                    }) for pay in ticket.payments_ids
                ]
                sudo_env.write({
                    'date': ticket.date,
                    'ticket_payment_method': ticket.payment_method.id,
                    'ticket_payment_type': ticket.payment_type.id,
                    'ticket_discount_authorized': ticket.discount_authorized.id if ticket.discount_authorized else None,
                    'ticket_iva': ticket.iva,
                    'ticket_total': ticket.total,
                    'ticket_subtotal': ticket.subtotal,
                    'ticket_discount': ticket.discount,
                    'cashier': ticket.cashier.id,
                    'ticket_discount_ids': [(6, 0, ticket.discount_ids.ids)] if ticket.discount_ids else [(6, 0, [])],
                    'ticket_void_authorized': ticket.void_authorized.id if ticket.void_authorized else None,
                    'ticket_reprint_number': ticket.reprint_number,
                    'difference': total - ticket.total,
                    'ticket_product_line': [(5, 0, 0)] + ticket_product_lines,
                    'ticket_payments_ids': [(5, 0, 0)] + ticket_payment_lines,
                })

        return record

    @api.depends('date', 'closed_date')
    def _compute_closing_time(self):
        """ Calcula el tiempo en que estuvo abierto el ticket """
        for record in self:
            if record.date and record.closed_date:
                delta = record.closed_date - record.date
                hours, remainder = divmod(delta.total_seconds(), 3600)
                minutes, seconds = divmod(remainder, 60)
                record.closing_time = f"{int(hours)}h {int(minutes)}m {int(seconds)}s"
            else:
                record.closing_time = "En proceso"


    @api.onchange('ticket_folio', 'company_id', 'branch_id')
    def _compute_ticket_information(self):
        for record in self:
            if record.ticket_folio:
                ticket = self.env['contabilidad_kuale.ticket_monitor'].sudo().search([
                    ('ticket_folio', '=', record.ticket_folio),
                    ('company_id', '=', record.company_id.id),
                    ('branch_id', '=', record.branch_id.id)
                ], limit=1)

                if ticket:
                    print('ticket_found')
                    record.date = ticket.date
                    record.ticket_payment_method = ticket.payment_method.id
                    record.ticket_payment_type = ticket.payment_type.id
                    record.ticket_iva = ticket.iva
                    record.ticket_total = ticket.total
                    record.ticket_subtotal = ticket.subtotal
                    record.ticket_discount = ticket.discount
                    record.ticket_product_line = [(5, 0, 0)]  # Elimina las líneas previas
                    record.ticket_product_line = [(0, 0, {
                        'third_party_id': line.third_party_id,
                        'quantity': line.quantity,
                        'unit_price': line.unit_price,
                        'discount': line.discount,
                        'subtotal': line.subtotal,
                        'ticket_monitor_audit_id': record.id
                    }) for line in ticket.product_line]

    @api.onchange('ticket_total', 'audit_total')
    def _compute_difference(self):
        for record in self:
            record.difference = record.audit_total - record.ticket_total

    # Para obtener compañías hijas (de la empresa principal)
    child_company_ids = fields.Many2many(
        'res.company',
        compute='_compute_child_companies',
        store=False
    )

    @api.depends('company_id')
    def _compute_child_companies(self):
        """Obtiene todas las compañías que son hijas de alguna otra."""
        all_child = self.env['res.company'].search([('parent_id', '!=', False)])
        self.child_company_ids = all_child.ids
