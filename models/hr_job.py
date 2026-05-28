from odoo import models, fields


class HrJob(models.Model):
    _inherit='hr.job'

    product_template_id = fields.Many2one(
        string="Producto",
        comodel_name='product.template',
        compute='_compute_product_template_id',
        readonly=False,
        required=True,
        search='_search_product_template_id',
        # previously related='product_id.product_tmpl_id'
        # not anymore since the field must be considered editable for product configurator logic
        # without modifying the related product_id when updated.
        domain=[('sale_ok', '=', True), ('is_lgp', '=', True)])