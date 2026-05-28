# models/quant_package_wizard.py

from odoo import models, fields, api
from datetime import date

from odoo.exceptions import UserError


class QuantPackageWizardLine(models.TransientModel):
    _name = 'quant.package.wizard.line'
    _description = 'Línea de empaque para conteo físico'

    wizard_id = fields.Many2one('quant.package.wizard', required=True, ondelete='cascade')
    packaging_id = fields.Many2one('product.packaging', string="Empaque", required=True)
    package_qty = fields.Float(string="Cantidad de paquetes", required=True)
    units = fields.Float(string="Unidades", compute="_compute_units", store=True)

    @api.depends('packaging_id', 'package_qty')
    def _compute_units(self):
        for rec in self:
            rec.units = rec.packaging_id.qty * rec.package_qty if rec.packaging_id else 0


class QuantPackageWizard(models.TransientModel):
    _name = 'quant.package.wizard'
    _description = 'Wizard de conteo por empaques'

    quant_id = fields.Many2one('stock.quant', required=True)
    product_id = fields.Many2one('product.product',related='quant_id.product_id', readonly=True, store=True, string='Producto')
    location_id = fields.Many2one('stock.location',related='quant_id.location_id', readonly=True, store=True, string='Ubicación')
    lot_id = fields.Many2one('stock.lot',related='quant_id.lot_id', readonly=True, store=True, string='Numero de lote')
    last_count_date = fields.Date(related='quant_id.last_count_date', readonly=True, store=True, string='Ultima fecha de conteo')
    available_quantity = fields.Float(related='quant_id.available_quantity', readonly=True, store=True, string='Cantidad disponible')
    quantity = fields.Float(related='quant_id.quantity', readonly=True, store=True, string='Cantidad disponible')
    product_uom_id = fields.Many2one('uom.uom', related='quant_id.product_uom_id', readonly=True, store=True, String='Unidad de medida')
    accounting_date = fields.Date(related='quant_id.accounting_date', readonly=True, store=True, String='Fecha contable')
    difference = fields.Float(string='Diferencia', compute="_compute_difference", store=True)



    line_ids = fields.One2many('quant.package.wizard.line', 'wizard_id', string="Líneas de empaque")

    total_units = fields.Float(string="Total en unidades", compute="_compute_total_units", store=True)


    @api.depends('line_ids.units')
    def _compute_total_units(self):
        for wizard in self:
            wizard.total_units = sum(wizard.line_ids.mapped('units'))

    @api.depends('total_units', 'quantity')
    def _compute_difference(self):
        for wizard in self:
            wizard.difference = wizard.total_units - wizard.quantity

    def action_confirm(self):
        self.ensure_one()
        self.quant_id.inventory_quantity = self.total_units
        self.quant_id.last_count_date = date.today()
        return {'type': 'ir.actions.act_window_close'}


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    def action_open_package_wizard(self):
        wizard = self.env['quant.package.wizard'].create({
            'quant_id':self.id
        })
        return{
            'name':'Conteo por empaques',
            'type': 'ir.actions.act_window',
            'res_model': 'quant.package.wizard',
            'view_mode': 'form',
            'res_id': wizard.id,
            'target': 'new',
        }