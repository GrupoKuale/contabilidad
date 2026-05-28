from odoo import models, fields, api, exceptions, _

class SellTypes(models.Model):
    _name='contabilidad_kuale.ticket_sell_types'
    _description='Contabilidad Kuale Ticket Sell Types'

    name = fields.Char(string='Tipo de Venta ', required=True)
    clave = fields.Char(string='Clave', required=True)

    analytic_account = fields.Many2one('account.analytic.account', string='Cuenta analítica', required=True)