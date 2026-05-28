from odoo import models,api,fields,_


class PaymentAccountTypes(models.Model):
    _name = 'payment.account.types'
    _description = 'payment account types for account move entry'

    account = fields.Char(string='Numero de cuenta', required=True)
    account_concept = fields.Char(string='Forma de pago', required=True,help='concepto de cuenta en póliza (uber, efectivo, app, descuento, etc.)')
    active = fields.Boolean(string='Activo', default=True)
    description = fields.Char(string='Nombre para asiento contable', help='Información tipo de ingreso o cuenta(etiqueta nombre para poliza)')
