from odoo import api, fields, models, _
from odoo.exceptions import UserError


class InterBranchTransfer(models.Model):
    _name = 'contabilidad_kuale.product_transfer'
    _description = 'Traspaso entre sucursales'

    date = fields.Date(string='Fecha', default=fields.Date.today, required=True)
    company_id = fields.Many2one('res.company', string="Empresa Origen", required=True,
                                 domain="[('parent_id','=',False)]")
    origin_branch_id = fields.Many2one('res.company', string="Sucursal Origen", required=True,
                                       domain="[('parent_id','=',company_id)]")
    dest_branch_id = fields.Many2one('res.company', string="Sucursal Destino", required=True,
                                     domain="[('parent_id','=',company_id)]")
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('transferred', 'Transferido'),
        ('received', 'Recibido'),
        ('cancel', 'Cancelado')
    ], default='draft', string="Estado")

    line_ids = fields.One2many('contabilidad_kuale.product_transfer_line', 'transfer_id',
                               string='Productos a transferir')
    picking_out_id = fields.Many2one('stock.picking', string='Salida Origen')
    picking_in_id = fields.Many2one('stock.picking', string='Entrada Destino')

    def action_transfer(self):
        for transfer in self:
            if transfer.state != 'draft':
                raise UserError("Solo se puede transferir desde estado Borrador.")

            warehouse_out = self.env['stock.warehouse'].sudo().search([('company_id', '=', transfer.origin_branch_id.id)],
                                                               limit=1)
            if not warehouse_out:
                raise UserError("No se encontró almacén en la sucursal origen.")

            customer_location = self.env.ref('stock.stock_location_customers')

            picking_out = self.env['stock.picking'].create({
                'picking_type_id': warehouse_out.out_type_id.id,
                'location_id': warehouse_out.lot_stock_id.id,
                'location_dest_id': customer_location.id,
                'origin': f"Traspaso hacia {transfer.dest_branch_id.name}",
                'company_id': transfer.origin_branch_id.id,
            })

            for line in transfer.line_ids:
                if line.quantity > line.stock_available:
                    raise UserError(f"No hay suficiente stock para '{line.product_id.display_name}' en sucursal origen.")
                self.env['stock.move'].create({
                    'name': f'Traspaso {self.origin_branch_id.name} - {self.dest_branch_id.name} {transfer.date}',
                    'product_id': line.product_id.id,
                    'product_uom_qty': line.quantity,
                    'product_uom': line.product_id.uom_id.id,
                    'location_id': warehouse_out.lot_stock_id.id,
                    'location_dest_id': customer_location.id,
                    'picking_id': picking_out.id,
                    'company_id': transfer.origin_branch_id.id,
                })

            picking_out.action_confirm()
            picking_out.action_assign()
            if picking_out.state in ['assigned']:
                picking_out.button_validate()

            transfer.picking_out_id = picking_out.id
            transfer.state = 'transferred'

    def action_receive(self):
        for transfer in self:
            if transfer.state != 'transferred':
                raise UserError("El traspaso debe estar en estado Transferido antes de recibir.")

            warehouse_in = self.env['stock.warehouse'].sudo().search([('company_id', '=', transfer.dest_branch_id.id)],
                                                              limit=1)
            if not warehouse_in:
                raise UserError("No se encontró almacén en la sucursal destino.")

            customer_location = self.env.ref('stock.stock_location_customers')

            picking_in = self.env['stock.picking'].create({
                'picking_type_id': warehouse_in.in_type_id.id,
                'location_id': customer_location.id,
                'location_dest_id': warehouse_in.lot_stock_id.id,
                'origin': f"Recepción desde {transfer.origin_branch_id.name}",
                'company_id': transfer.dest_branch_id.id,
            })

            for line in transfer.line_ids:
                self.env['stock.move'].create({
                    'name': f'Traspaso {self.origin_branch_id.name} - {self.dest_branch_id.name} {transfer.date}',
                    'product_id': line.product_id.id,
                    'product_uom_qty': line.quantity,
                    'product_uom': line.product_id.uom_id.id,
                    'location_id': customer_location.id,
                    'location_dest_id': warehouse_in.lot_stock_id.id,
                    'picking_id': picking_in.id,
                    'company_id': transfer.dest_branch_id.id,
                })

            picking_in.action_confirm()
            picking_in.action_assign()
            if picking_in.state in ['assigned']:
                picking_in.button_validate()

            transfer.picking_in_id = picking_in.id
            transfer.state = 'received'


class InterBranchTransferLine(models.Model):
    _name = 'contabilidad_kuale.product_transfer_line'
    _description = 'Linea de traspaso entre sucursales'

    transfer_id = fields.Many2one('contabilidad_kuale.product_transfer', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string="Producto", required=True)
    uom = fields.Many2one('uom.uom', string='Udm', compute='_compute_uom', store=False)
    capture_mode = fields.Selection([
        ('unit', 'Unidades'),
        ('package', 'Por empaque'),
    ], string="Modo de captura", default='unit', required=True)
    packaging_id = fields.Many2one('product.packaging', string="Empaque", domain="[('product_id', '=', product_id)]")
    package_qty = fields.Float(string="Cantidad de paquetes")
    unit_qty = fields.Float(string="Cantidad de unidades")
    quantity = fields.Float(string="Cantidad total", compute='_compute_quantity', store=True)
    stock_available = fields.Float(string='Stock disponible', compute='_compute_stock_available')
    stock_after_transfer = fields.Float(string='Stock después del traspaso', compute='_compute_stock_after')

    @api.depends('product_id')
    def _compute_uom(self):
        for line in self:
            line.uom = line.product_id.uom_id.id if line.product_id else ''

    @api.depends('product_id', 'transfer_id.origin_branch_id')
    def _compute_stock_available(self):
        for line in self:
            line.stock_available = 0.0  # Inicializa SIEMPRE
            if not line.product_id or not line.transfer_id or not line.transfer_id.origin_branch_id:
                continue
            warehouse = self.env['stock.warehouse'].sudo().search([
                ('company_id', '=', line.transfer_id.origin_branch_id.id)
            ], limit=1)
            if warehouse:
                quants = self.env['stock.quant'].sudo().search([
                    ('product_id', '=', line.product_id.id),
                    ('location_id', 'child_of', warehouse.lot_stock_id.id)
                ])
                line.stock_available = sum(quants.mapped('quantity'))

    @api.depends('stock_available', 'quantity')
    def _compute_stock_after(self):
        for line in self:
            line.stock_after_transfer = (line.stock_available or 0.0) - (line.quantity or 0.0)

    @api.depends('capture_mode', 'unit_qty', 'package_qty', 'packaging_id')
    def _compute_quantity(self):
        for line in self:
            if line.capture_mode == 'unit':
                line.quantity = line.unit_qty or 0.0
            elif line.capture_mode == 'package' and line.packaging_id:
                line.quantity = line.package_qty * line.packaging_id.qty
            else:
                line.quantity = 0.0
