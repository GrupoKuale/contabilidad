from odoo import models, fields, api, _
from odoo.exceptions import UserError

class SatXmlMatchWizard(models.TransientModel):
    _name = 'sat.xml.match.wizard'
    _description = 'Asistente de Conciliación de Productos XML'

    import_xml_id = fields.Many2one('purchase.order.import.xml', string="Origen")
    partner_id = fields.Many2one('res.partner', string="Proveedor", required=True)
    line_ids = fields.One2many('sat.xml.match.line', 'wizard_id', string="Líneas a Conciliar")

    def action_confirm(self):
        """
        Procesa las líneas: Crea productos con la categoría seleccionada o vincula existentes.
        """
        SupplierInfo = self.env['product.supplierinfo']
        Product = self.env['product.product']

        for line in self.line_ids:
            if line.action_type == 'ignore':
                continue

            product = line.selected_product_id

            # --- CREAR PRODUCTO NUEVO ---
            if line.action_type == 'create_new':
                # Validar que tenga categoría para evitar el error SQL
                if not line.categ_id:
                    raise UserError(_("La línea '%s' no tiene categoría asignada. Por favor selecciónala.") % line.xml_description)

                vals = {
                    'name': line.xml_description,
                    'standard_price': line.xml_price,
                    'list_price': line.xml_price, 
                    'detailed_type': 'product',
                    'purchase_ok': True,
                    'sale_ok': True,
                    'categ_id': line.categ_id.id, 
                    'uom_id': line.xml_uom_id.id or self.env.ref('uom.product_uom_unit').id,
                    'uom_po_id': line.xml_uom_id.id or self.env.ref('uom.product_uom_unit').id,
                }
                product = Product.create(vals)
            
            # --- VINCULAR EXISTENTE ---
            elif line.action_type == 'link_existing':
                if not product:
                    raise UserError(_("Debes seleccionar un producto existente para la línea: %s") % line.xml_description)

            # Verificar duplicados
            exists = SupplierInfo.search([
                ('partner_id', '=', self.partner_id.id),
                ('product_tmpl_id', '=', product.product_tmpl_id.id),
                ('product_code', '=', line.xml_code)
            ], limit=1)

            if not exists:
                SupplierInfo.create({
                    'partner_id': self.partner_id.id,
                    'product_tmpl_id': product.product_tmpl_id.id,
                    'product_name': line.xml_description,
                    'product_code': line.xml_code,
                    'min_qty': 1,
                    'price': line.xml_price,
                })

        # Reintentar el proceso original de la OC
        return self.import_xml_id.action_process_massive_xml()


class SatXmlMatchLine(models.TransientModel):
    _name = 'sat.xml.match.line'
    _description = 'Línea de Conciliación XML'

    wizard_id = fields.Many2one('sat.xml.match.wizard')
    
    xml_code = fields.Char(string="Código XML", readonly=True)
    xml_description = fields.Char(string="Descripción XML", readonly=True)
    xml_quantity = fields.Float(string="Cant.", readonly=True)
    xml_price = fields.Float(string="Precio", readonly=True)
    xml_uom_id = fields.Many2one('uom.uom', string="UdM")

    action_type = fields.Selection([
        ('link_existing', 'Vincular'),
        ('create_new', 'Crear Nuevo'),
        ('ignore', 'Ignorar')
    ], string="Acción", default='create_new', required=True)

    selected_product_id = fields.Many2one('product.product', string="Producto Odoo", 
        domain="[('purchase_ok', '=', True)]")
    
    categ_id = fields.Many2one('product.category', string="Categoría", 
        default=lambda self: self.env.ref('product.product_category_all', raise_if_not_found=False))

    @api.onchange('action_type')
    def _onchange_action_type(self):
        if self.action_type == 'create_new':
            self.selected_product_id = False

    def action_open_create_form(self):
        """
        Abre la vista formulario de producto pre-rellenada
        """
        self.ensure_one()
        return {
            'name': _('Crear Producto desde XML'),
            'type': 'ir.actions.act_window',
            'res_model': 'product.product',
            'view_mode': 'form',
            'target': 'new', 
            'context': {
                'default_name': self.xml_description,
                'default_default_code': self.xml_code,
                'default_standard_price': self.xml_price,
                'default_list_price': self.xml_price,
                'default_uom_id': self.xml_uom_id.id,
                'default_uom_po_id': self.xml_uom_id.id,
                'default_detailed_type': 'product',
                'default_purchase_ok': True,
                'default_categ_id': self.categ_id.id, 
            }
        }