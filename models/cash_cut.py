from odoo import api, models, fields


class CashCut(models.Model):
    _name = 'contabilidad_kuale.cash_cut'
    _description = 'Cash Cut'

    company_id = fields.Many2one('res.company', string='Empresa',
                                 domain="[('is_branch', '=', False)]", required=True)
    branch_id = fields.Many2one('res.company', string='Sucursal',
                                domain="['|', ('parent_id', '=', company_id), ('id', '=', company_id)]", required=True)
    date = fields.Date(string='Fecha', required=True)

    cash_cut_line_ids = fields.One2many('contabilidad_kuale.cash_cut_line', 'cash_cut_id', string='Líneas de corte')

    cash_total = fields.Float(string='Total efectivo', compute='_compute_totals', store=True, readonly=True)
    card_total = fields.Float(string='Total tarjetas', compute='_compute_totals', store=True, readonly=True)
    total = fields.Float(string='Total general', compute='_compute_totals', store=True, readonly=True)
    cut_total = fields.Float(string='Cuenta Total', compute='_compute_totals', store=True, readonly=True)
    difference = fields.Float(string='Diferencia total', compute='_compute_totals', store=True, readonly=True)

    @api.depends('cash_cut_line_ids.cash_total',
                 'cash_cut_line_ids.card_total',
                 'cash_cut_line_ids.total',
                 'cash_cut_line_ids.difference')
    def _compute_totals(self):
        for record in self:
            record.cash_total = sum(line.cash_total for line in record.cash_cut_line_ids)
            record.card_total = sum(line.card_total for line in record.cash_cut_line_ids)
            record.total = record.cash_total + record.card_total
            record.cut_total = sum(line.total for line in record.cash_cut_line_ids)
            record.difference = sum(line.difference for line in record.cash_cut_line_ids)


class CashCutLine(models.Model):
    _name = 'contabilidad_kuale.cash_cut_line'
    _description = 'Cash Cut Line'

    cash_cut_id = fields.Many2one('contabilidad_kuale.cash_cut', string='Corte de Caja')

    date = fields.Date(string='Fecha', required=True)
    cashier = fields.Many2one('hr.employee', string='Cajero', required=True)
    manager = fields.Many2one('hr.employee', string="Gerente", required=True)
    deposit = fields.Char(string='Número de Depósito')

    # Denominaciones (billetes y monedas)
    coin_1000 = fields.Integer(string='$1000')
    total_coin_1000 = fields.Float(string='Total $1000', compute='_compute_total_coins', store=True, readonly=True)

    coin_500 = fields.Integer(string='$500')
    total_coin_500 = fields.Float(string='Total $500', compute='_compute_total_coins', store=True, readonly=True)

    coin_200 = fields.Integer(string='$200')
    total_coin_200 = fields.Float(string='Total $200', compute='_compute_total_coins', store=True, readonly=True)

    coin_100 = fields.Integer(string='$100')
    total_coin_100 = fields.Float(string='Total $100', compute='_compute_total_coins', store=True, readonly=True)

    coin_50 = fields.Integer(string='$50')
    total_coin_50 = fields.Float(string='Total $50', compute='_compute_total_coins', store=True, readonly=True)

    coin_20 = fields.Integer(string='$20')
    total_coin_20 = fields.Float(string='Total $20', compute='_compute_total_coins', store=True, readonly=True)

    coin_10 = fields.Integer(string='$10')
    total_coin_10 = fields.Float(string='Total $10', compute='_compute_total_coins', store=True, readonly=True)

    coin_5 = fields.Integer(string='$5')
    total_coin_5 = fields.Float(string='Total $5', compute='_compute_total_coins', store=True, readonly=True)

    coin_2 = fields.Integer(string='$2')
    total_coin_2 = fields.Float(string='Total $2', compute='_compute_total_coins', store=True, readonly=True)

    coin_1 = fields.Integer(string='$1')
    total_coin_1 = fields.Float(string='Total $1', compute='_compute_total_coins', store=True, readonly=True)

    coin_050 = fields.Integer(string='$0.50')
    total_coin_050 = fields.Float(string='Total $0.50', compute='_compute_total_coins', store=True, readonly=True)

    coin_010 = fields.Integer(string='$0.10')
    total_coin_010 = fields.Float(string='Total $0.10', compute='_compute_total_coins', store=True, readonly=True)

    # Totales
    cash_total = fields.Float(string='Total efectivo', compute='_compute_cash_total', store=True, readonly=True)
    card_total = fields.Float(string='Total bancarias')
    total = fields.Float(string='Total', compute='_compute_line_total', store=True, readonly=True)
    system_total = fields.Float(string='Total corte sistema')
    difference = fields.Float(string='Diferencia', compute='_compute_difference', store=True, readonly=True)

    @api.depends(
        'coin_1000', 'coin_500', 'coin_200', 'coin_100', 'coin_50', 'coin_20',
        'coin_10', 'coin_5', 'coin_2', 'coin_1', 'coin_050', 'coin_010'
    )
    def _compute_total_coins(self):
        for line in self:
            line.total_coin_1000 = line.coin_1000 * 1000
            line.total_coin_500 = line.coin_500 * 500
            line.total_coin_200 = line.coin_200 * 200
            line.total_coin_100 = line.coin_100 * 100
            line.total_coin_50 = line.coin_50 * 50
            line.total_coin_20 = line.coin_20 * 20
            line.total_coin_10 = line.coin_10 * 10
            line.total_coin_5 = line.coin_5 * 5
            line.total_coin_2 = line.coin_2 * 2
            line.total_coin_1 = line.coin_1 * 1
            line.total_coin_050 = line.coin_050 * 0.50
            line.total_coin_010 = line.coin_010 * 0.10

    @api.depends(
        'total_coin_1000', 'total_coin_500', 'total_coin_200', 'total_coin_100',
        'total_coin_50', 'total_coin_20', 'total_coin_10', 'total_coin_5',
        'total_coin_2', 'total_coin_1', 'total_coin_050', 'total_coin_010'
    )
    def _compute_cash_total(self):
        for line in self:
            line.cash_total = sum([
                line.total_coin_1000, line.total_coin_500, line.total_coin_200,
                line.total_coin_100, line.total_coin_50, line.total_coin_20,
                line.total_coin_10, line.total_coin_5, line.total_coin_2,
                line.total_coin_1, line.total_coin_050, line.total_coin_010
            ])

    @api.depends('cash_total', 'card_total')
    def _compute_line_total(self):
        for line in self:
            line.total = (line.cash_total or 0.0) + (line.card_total or 0.0)

    @api.depends('total', 'system_total')
    def _compute_difference(self):
        for line in self:
            line.difference = (line.total or 0.0) - (line.system_total or 0.0)
