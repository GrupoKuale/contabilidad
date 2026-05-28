from odoo import api, models, fields, _
from odoo.exceptions import UserError
import base64
from lxml import etree
from datetime import datetime
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)

class SalesOrder(models.Model):
    _inherit = 'sale.order'

    # Vendedor: siempre el usuario logueado por default, pero editable
    user_id = fields.Many2one(
        'res.users',
        string='Vendedor',
        default=lambda self: self.env.user,
        tracking=True,
    )

    # Empresa: siempre la empresa actual, no editable
    company_id = fields.Many2one(
        'res.company',
        string='Empresa',
        default=lambda self: self.env.company,
        readonly=True,
    )

    # Diario: default = primer diario de ventas de la empresa
    journal_id = fields.Many2one(
        'account.journal',
        string='Diario de facturación',
        default=lambda self: self.env['account.journal'].search([
            ('type', '=', 'sale'),
            ('company_id', '=', self.env.company.id)
        ], limit=1),
    )

    immediate_product_release = fields.Boolean(string='Salida inmediata del inventario', default=False,
                                               help="Si está activado, el inventario se descontará automáticamente al confirmar la orden de venta.")
    exchange_rate = fields.Float(default=1.0, string='Exchange Rate', store=True,
                                 help='Tipo de cambio actual al momento de la cotización')


    exchange_view = fields.Boolean(
        string="Mostrar Tipo de Cambio", compute="_compute_show_exchange_rate", store=True
    )

    admin_email = fields.Char(compute='_compute_admin_email', string='Emails Administradores')

    def _compute_admin_email(self):
        admin_group = self.env.ref('base.group_system')
        admin_users = admin_group.users

        for order in self:
            email_list = [admin.partner_id.email for admin in admin_users if admin.partner_id.email]
            order.admin_email = ', '.join(email_list)

    @api.depends('pricelist_id')
    def _compute_show_exchange_rate(self):
        for order in self:
            if order.pricelist_id and order.pricelist_id.currency_id:
                order.exchange_view = order.pricelist_id.currency_id != order.company_id.currency_id
            else:
                order.exchange_view = False

    @api.onchange('pricelist_id')
    def _compute_exchange_rate(self):
        for order in self:
            if order.pricelist_id and order.pricelist_id.currency_id:
                company_currency = self.env.user.company_id.currency_id
                pricelist_currency = order.pricelist_id.currency_id
                if pricelist_currency != company_currency:
                    order.exchange_rate = self.env['res.currency']._get_conversion_rate(
                        pricelist_currency, company_currency, order.company_id, fields.Date.today()
                    )
                else:
                    order.exchange_rate = 1.0
            else:
                order.exchange_rate = 0.0

    @api.depends('partner_id')
    def _compute_user_id(self):
        """
        Sobrescribe el compute estándar de Odoo 17 para evitar que al cambiar el
        cliente se sobreescriba el vendedor con el user_id del partner (que puede
        ser un usuario portal con el mismo nombre del cliente).
        Regla: el vendedor siempre es el usuario logueado, salvo que ya haya uno
        asignado explícitamente en un registro guardado (is_new = no tiene _origin.id).
        """
        for order in self:
            if not order._origin.id:
                # Registro nuevo: poner siempre el usuario logueado
                order.user_id = self.env.user
            # Si ya está guardado, no tocamos el vendedor al cambiar el cliente

    @api.onchange('partner_id')
    def _onchange_partner_id_payment_term(self):
        """Carga los términos de pago del contacto al seleccionar cliente."""
        if self.partner_id and self.partner_id.property_payment_term_id:
            self.payment_term_id = self.partner_id.property_payment_term_id

    state = fields.Selection(
        selection_add=[
            ('to_approve', 'Por aprobar'),
            ('approved', 'Aprobado'),
        ]
    )

    requires_authorization = fields.Boolean(
        string="Requiere Autorización",
        compute="_compute_requires_authorization",
        store=True,
    )

    @api.depends('company_id')
    def _compute_requires_authorization(self):
        for order in self:
            order.requires_authorization = order.company_id.requires_sale_authorization

    def action_request_approval(self):
        for order in self:
            if order.requires_authorization:
                order.state = 'to_approve'
                template = self.env.ref('contabilidad_kuale.mail_authorization_request', raise_if_not_found=False)
                if template:
                    template.model = self._name
                    template.send_mail(order.id, force_send=True)
            else:
                raise UserError(_("Esta cotización no requiere autorización."))

    def action_approve(self):
        for order in self:
            if order.state == 'to_approve':
                order.state = 'approved'
            else:
                raise UserError(_("Solo se pueden aprobar cotizaciones en estado 'Por Aprobar'."))


    def _prepare_invoice(self):
        """Override to set the invoice date to today's date automatically."""
        vals = super(SalesOrder, self)._prepare_invoice()
        vals['invoice_date'] = fields.Date.context_today(self)
        return vals

    def action_confirm(self):
        for order in self:
            # Validar si requiere autorizacion
            if order.requires_authorization and order.state != 'approved':
                raise UserError(_("Debe aprobar esta cotización antes de confirmarla."))

            # Validar que no haya productos tipo service fabricables sin salida inmediata
            for line in order.order_line:
                tmpl = line.product_id.product_tmpl_id
                if tmpl.elaborate_ok and tmpl.detailed_type == 'service' and not order.immediate_product_release:
                    raise UserError(_(
                        "No se puede vender el producto fabricado '%s' (tipo servicio) sin activar 'Salida inmediata del inventario'."
                    ) % tmpl.display_name)

        res = super(SalesOrder, self).action_confirm()
        for order in self:
            for line in order.order_line:
                tmpl = line.product_id.product_tmpl_id

                if tmpl.elaborate_ok and tmpl.detailed_type == 'service':
                    if order.immediate_product_release:
                        line._create_bom_inventory_movements()
                elif tmpl.detailed_type == 'product':
                    if order.immediate_product_release:
                        picking = order.picking_ids.filtered(lambda p: p.state not in ['done', 'cancel'])
                        for p in picking:
                            p.action_confirm()
                            p.action_assign()
                            if p.state == 'assigned':
                                p.button_validate()
        return res

    def duplicate_as_quotation(self):
        self.ensure_one()
        new_order = self.copy()

        new_order.write({
            'state': 'draft',
            'name': self.env['ir.sequence'].next_by_code('sale.order') or _('New')
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'view_mode': 'form',
            'res_id': new_order.id,
            'target': 'current',
        }

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _create_bom_inventory_movements(self):
        picking_type = self.env['stock.picking.type'].search([
            ('warehouse_id', '=', self.order_id.warehouse_id.id),
            ('code', '=', 'outgoing')
        ], limit=1)

        if not picking_type:
            raise UserError(_("No se encontró tipo de operación de salida para esta sucursal."))

        picking = self.env['stock.picking'].create({
            'partner_id': self.order_id.partner_id.id,
            'picking_type_id': picking_type.id,
            'location_id': self.order_id.warehouse_id.lot_stock_id.id,
            'location_dest_id': self.order_id.partner_shipping_id.property_stock_customer.id,
            'origin': self.order_id.name,
            'company_id': self.order_id.company_id.id,
        })

        for bom_line in self.product_id.product_tmpl_id.bom_line_ids:
            total_qty = self.product_uom_qty * bom_line.quantity
            component = bom_line.component_id

            if component.qty_available < total_qty:
                raise UserError(
                    _("No hay suficiente stock de %s. Disponible: %s, Requerido: %s") %
                    (component.display_name, component.qty_available, total_qty)
                )

            self.env['stock.move'].sudo().create({
                'name': f"Componente de {self.product_id.display_name}",
                'product_id': component.id,
                'product_uom_qty': total_qty,
                'product_uom': component.uom_id.id,
                'location_id': self.order_id.warehouse_id.lot_stock_id.id,
                'location_dest_id': self.order_id.partner_shipping_id.property_stock_customer.id,
                'picking_id': picking.id,
                'company_id': self.order_id.company_id.id,
            })

        picking.action_confirm()
        picking.action_assign()
        if picking.state == 'assigned':
            picking.button_validate()

    def _validate_outgoing_picking(self):
        picking = self.env['stock.picking'].search([
            ('origin', '=', self.order_id.name),
            ('picking_type_id.code', '=', 'outgoing'),
            ('state', 'not in', ['done', 'cancel'])
        ], limit=1)

        if picking:
            picking.action_confirm()
            picking.action_assign()
            if picking.state == 'assigned':
                picking.button_validate()

class SaleOrderImportXml(models.TransientModel):
    _name = 'sale.order.import.xml'
    _description = 'Importación de XML a Pedido de Venta'

    file = fields.Binary(string="Archivo XML", required=True)
    filename = fields.Char(string="Nombre del Archivo")

    def _get_values_xml(self):
        """ Parsea el XML para extracción de datos de venta """
        if not self.file:
            raise UserError(_("No se ha subido ningún archivo."))
        
        try:
            xml_data = base64.b64decode(self.file)
            if b'encoding=' not in xml_data:
                 xml_string = xml_data.decode('utf-8', errors='ignore')
                 xml_tree = etree.fromstring(xml_string.encode('utf-8'))
            else:
                 xml_tree = etree.fromstring(xml_data)
                 
            ns = {'cfdi': 'http://www.sat.gob.mx/cfd/4'} 
        except Exception as e:
            raise UserError(_("Error al leer el XML. Detalles: %s") % e)

        # Extracción de datos básicos
        folio = xml_tree.get('Folio', '')
        serie = xml_tree.get('Serie', '')
        fecha_str = xml_tree.get('Fecha', '')
        
        # Emisor
        receptor = xml_tree.find('cfdi:Receptor', ns)
        if receptor is None:
             raise UserError("El XML no tiene nodo Receptor.")

        cliente_rfc = receptor.get('Rfc')
        cliente_name = receptor.get('Nombre')
        uso_cfdi = receptor.get('UsoCFDI')
        # Extraer Régimen Fiscal del Receptor para crear cliente
        cliente_regimen = receptor.get('RegimenFiscalReceptor')

        # Productos
        productos = []
        conceptos = xml_tree.findall('.//cfdi:Concepto', ns)
        for c in conceptos:
            impuestos_xml = []
            traslados = c.findall('.//cfdi:Traslado', ns)
            for t in traslados:
                impuestos_xml.append({
                    'impuesto': t.get('Impuesto'),
                    'tasa': float(t.get('TasaOCuota') or 0),
                    'tipo': 'traslado'
                })

            productos.append({
                'clave_sat': c.get('ClaveProdServ'),
                'no_identificacion': c.get('NoIdentificacion'),
                'cantidad': float(c.get('Cantidad') or 0),
                'descripcion': c.get('Descripcion'),
                'valor_unitario': float(c.get('ValorUnitario') or 0),
                'importe': float(c.get('Importe') or 0),
                'descuento': float(c.get('Descuento') or 0),
                'impuestos': impuestos_xml
            })

        return {
            'folio': folio,
            'serie': serie,
            'fecha': fecha_str,
            'cliente_rfc': cliente_rfc,
            'cliente_name': cliente_name,
            'cliente_regimen': cliente_regimen, # Nuevo campo
            'productos': productos,
            'uso_cfdi': uso_cfdi
        }

    def action_process_sale_xml(self):
        """ Proceso principal: Crea la Sale Order """
        data = self._get_values_xml()
        
        # 1. Buscar Cliente (Partner)
        partner = self.env['res.partner'].search([('rfc', '=', data['cliente_rfc'])], limit=1)
        
        # LÓGICA DE CREACIÓN AUTOMÁTICA DE CLIENTE
        if not partner:
            _logger.info(">>> No se encontró cliente, creando nuevo...")
            company = self.env.company
            
            # Validación de cuentas en la compañía
            if not company.account_payable or not company.account_payable.code:
                raise UserError(_(
                    f"La empresa '{company.name}' NO tiene configurada la cuenta por pagar.\n\n"
                    f"Configure en: Contabilidad → Configuración → Parámetros → Cuentas por defecto"
                ))
            
            if not company.account_receivable or not company.account_receivable.code:
                raise UserError(_(
                    f"La empresa '{company.name}' NO tiene configurada la cuenta por cobrar.\n\n"
                    f"Configure en: Contabilidad → Configuración → Parámetros → Cuentas por defecto"
                ))

            try:
                with self.env.cr.savepoint():
                    # Obtener cuentas base
                    base_payable = company.account_payable
                    base_receivable = company.account_receivable
                    
                    # Calcular código cuenta por Pagar 
                    last_child_payable = self.env['account.account'].sudo().search([
                        ('code', 'like', f"{base_payable.code}.%"),
                        ('company_id', '=', company.id)
                    ], order="code desc", limit=1)
                    
                    if last_child_payable:
                        last_seq = int(last_child_payable.code.split('.')[-1])
                        payable_code = f"{base_payable.code}.{last_seq + 1}"
                    else:
                        payable_code = f"{base_payable.code}.1"
                    
                    # Calcular código cuenta por Cobrar 
                    last_child_receivable = self.env['account.account'].sudo().search([
                        ('code', 'like', f"{base_receivable.code}.%"),
                        ('company_id', '=', company.id)
                    ], order="code desc", limit=1)
                    
                    if last_child_receivable:
                        last_seq = int(last_child_receivable.code.split('.')[-1])
                        receivable_code = f"{base_receivable.code}.{last_seq + 1}"
                    else:
                        receivable_code = f"{base_receivable.code}.1"
                    
                    # Crear cuenta por pagar
                    partner_pay_acc = self.env['account.account'].sudo().create({
                        'name': data['cliente_name'],
                        'code': payable_code,
                        'company_id': company.id,
                        'account_type': 'liability_payable',
                        'sat_nivel': getattr(base_payable, 'sat_nivel', None),
                        'naturaleza': getattr(base_payable, 'naturaleza', None),
                    })
                    
                    # Crear cuenta por cobrar
                    partner_rec_acc = self.env['account.account'].sudo().create({
                        'name': data['cliente_name'],
                        'code': receivable_code,
                        'company_id': company.id,
                        'account_type': 'asset_receivable',
                        'sat_nivel': getattr(base_receivable, 'sat_nivel', None),
                        'naturaleza': getattr(base_receivable, 'naturaleza', None),
                    })
                    
                    # Buscar régimen fiscal del cliente
                    regimen_code = data.get('cliente_regimen') or '616' # Default: Sin obligaciones si no viene
                    code = self.env['cfdi.claveregimenfiscal'].sudo().search(
                        [('Clave_regimenFiscal', '=', regimen_code)], limit=1
                    )
                    
                    # Crear partner (Cliente)
                    partner = self.env['res.partner'].sudo().create({
                        'name': data['cliente_name'],
                        'rfc': data['cliente_rfc'],
                        'tax_regime': code.id if code else False,
                        'property_account_payable_id': partner_pay_acc.id,
                        'property_account_receivable_id': partner_rec_acc.id,
                        'customer_rank': 1, # Importante para que Odoo lo trate como cliente
                    })
                    
                    _logger.info(f'Cliente creado automáticamente: {partner.name} (ID: {partner.id})')

            except Exception as e:
                _logger.error(f"Error creando cliente: {str(e)}", exc_info=True)
                raise UserError(_(f"Error al crear el cliente automáticamente: {str(e)}"))

        # 2. Procesar Líneas
        order_lines = []
        errores = []

        for prod in data['productos']:
            # Lógica de búsqueda de producto
            # Primero buscamos por Referencia Interna (default_code)
            product = self.env['product.product'].search([
                ('default_code', '=', prod['no_identificacion']),
                ('sale_ok', '=', True)
            ], limit=1)

            # Si falla, búsqueda difusa por nombre
            if not product:
                product = self.env['product.product'].search([
                    ('name', 'ilike', prod['descripcion']),
                    ('sale_ok', '=', True)
                ], limit=1)

            if not product:
                errores.append(f"Producto no encontrado: {prod['no_identificacion']} - {prod['descripcion']}")
                continue

            # Calcular impuestos
            tax_ids = []
            for imp in prod['impuestos']:
                if imp['impuesto'] == '002' and imp['tasa'] > 0: # IVA
                     # Busca impuesto de Venta 
                     tax = self.env['account.tax'].search([
                         ('type_tax_use', '=', 'sale'),
                         ('amount', '=', imp['tasa'] * 100),
                         ('company_id', '=', self.env.company.id)
                     ], limit=1)
                     if tax:
                         tax_ids.append(tax.id)

            # Crear línea de pedido
            line_vals = {
                'product_id': product.id,
                'name': prod['descripcion'], # Usar descripción del XML
                'product_uom_qty': prod['cantidad'],
                'price_unit': prod['valor_unitario'],
                'tax_id': [(6, 0, tax_ids)] if tax_ids else False,
                'discount': (prod['descuento'] / prod['importe'] * 100) if prod['importe'] > 0 else 0.0
            }
            order_lines.append((0, 0, line_vals))

        if errores:
            raise UserError("\n".join(errores))

        if not order_lines:
            raise UserError("No se pudieron generar líneas para la orden de venta.")

        # 3. Crear Sale Order
        fecha_order = fields.Datetime.now()
        if data['fecha']:
            try:
                fecha_order = datetime.fromisoformat(data['fecha'].replace('T', ' '))
            except:
                pass

        sale_order = self.env['sale.order'].create({
            'partner_id': partner.id,
            'date_order': fecha_order,
            'client_order_ref': f"{data['serie']}-{data['folio']}" if data['folio'] else False,
            'order_line': order_lines,
            'company_id': self.env.company.id,
            'state': 'draft', # Nace como presupuesto
        })

        return sale_order