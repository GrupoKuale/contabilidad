from odoo import api, fields, models


class ProductPackaging(models.Model):
    _inherit = 'product.packaging'

    partner_id = fields.Many2one('res.partner', string='Proveedor')