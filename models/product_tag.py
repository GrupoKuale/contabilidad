from odoo import models, fields, api


class ProductTag(models.Model):
    _inherit = 'product.tag'

    # agregar lo de grupo empresarial y el de categoria
    category_id = fields.Many2one('product.category',string='Categoria del producto')
