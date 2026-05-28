from odoo import fields, models, api, _


class ShareCategoryConfirmWizard(models.TransientModel):
    _name = 'share.category.confirm.wizard'
    _description = 'Asistente para confirmar compartir categoría junto con el producto'

    product_id = fields.Many2one(
        'product.template', string='Producto',
        required=True, readonly=True,
    )
    category_id = fields.Many2one(
        'product.category', string='Categoría',
        required=True, readonly=True,
    )
    message = fields.Text(
        string='Mensaje', readonly=True,
    )

    def action_confirm(self):
        """Comparte la categoría y el producto."""
        self.ensure_one()
        # Compartir la categoría
        self.category_id.sudo().write({
            'is_shared_category': True,
            'company_group': False,
        })
        # Compartir el producto
        self.product_id.write({
            'is_shared_product': True,
            'company_group': False,
        })
        return {'type': 'ir.actions.act_window_close'}

    def action_cancel(self):
        """Revierte: no compartir el producto."""
        self.ensure_one()
        self.product_id.write({
            'is_shared_product': False,
        })
        return {'type': 'ir.actions.act_window_close'}
