from odoo import fields, models, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.osv import expression
import logging
from odoo.fields import Many2one

_logger = logging.getLogger(__name__)

class ProductSupplierInfo(models.Model):
    _inherit = 'product.supplierinfo'
    
    default_packaging_id = fields.Many2one('product.packaging', string='Embalaje predeterminado',
        domain="[('product_id.product_tmpl_id', '=', product_tmpl_id),'|',('partner_id', '=', partner_id),('partner_id', '=', False)]"
        ,help="Embalaje que se aplica automaticamente en linea de compra a este proveedor")
    
    @api.constrains('default_packaging_id', 'product_tmpl_id', 'partner_id')
    def _check_unique_default_packaging(self):
        for rec in self:
            if not rec.default_packaging_id:
                continue
            duplicates = self.search([
                ('id', '!=', rec.id),
                ('partner_id', '=', rec.partner_id.id),
                ('product_tmpl_id', '=', rec.product_tmpl_id.id),
                ('default_packaging_id', '!=', False),
            ])
            if duplicates:
                raise ValidationError(_(
                    "Solo puede existir un 'registro' para el producto '%s' con el proveedor '%s'."
                ) % (rec.product_tmpl_id.display_name, rec.partner_id.display_name))

class ProductSupplierInfoSumUp(models.Model):
    _name= 'product.supplierinfo.sumup'
    _description = 'Product Supplier Info Update sum up'
    
    partner_id = fields.Many2one('res.partner', string='Proveedor')
    name = fields.Char(string='Descripcion del producto')
    product_code = fields.Char(string='Codigo del producto')
    price = fields.Float(string='Precio')
    product_id = fields.Many2one('product.product', string='Producto', help="Producto al que se debe vincular")
    state = fields.Selection([
        ('pending', 'Pendiente'),
        ('done', 'Procesado')
    ], default='pending', string='Estado')
    
    def action_create_supplierinfo(self):
        for rec in self:
            if rec.state == 'done':
                continue
            if not rec.product_id:
                raise UserError("Debe asignar un producto antes de procesar")
            vals={
                'partner_id': rec.partner_id.id,
                'product_tmpl_id': rec.product_id.product_tmpl_id.id,
                'product_code': rec.product_code or False,
                'product_name': rec.name or False,
                'min_qty': 1,
                'price': rec.price or 0.0,
            }
            self.env['product.supplierinfo'].create(vals)
            rec.state = 'done'

class ProductPackaging(models.Model):
    _inherit = 'product.packaging'
    
    company_group = fields.Selection([
        ('hamburguesas', 'Hamburguesas Mafis SA de CV'),
        ('helados', 'Helados Mafis SA de CV'),
        ('sifam', 'Proyectos Sifam SA de CV'),
        ('hidro', 'Hidrológica Kuale SA de CV'),
        ('tinto5', 'Tintocinco SA de CV'),
        ('g_kuale', 'Gente Kuale SA de CV'),
        ('s_kuale', 'Servicios Kuale SA de CV'),
        ('kuale_srl', 'Kuale S de RL de CV'),
        ('gk_llc', 'Grupo Kuale USA LLC '),
        ('erben', 'Inmobiliaria Erben SA de CV'),
        ('mfda', 'Martha Fernanda Deutsch Azcárraga y Copropietarios'),
        ('ppt', 'Publipuentes Tamaulipas SA de CV'),
        ('c_kuale', 'Comercial Kuale SA de CV'),
        ('productora', 'Productora del Golfo SA de CV'),
        ('vdp', 'Video Producciones del Golfo SA de CV'),
        ('mr_motor', 'Mister Motor SA de CV'),
        ('express', 'Express Offshore de Mexico SA de CV'),
        ('ers', 'Especialistas en Reparto Seguro SA de CV'),
        ('operativos', 'Operativos de Franquicias SA de CV'),
        ('blanco_cafe', 'Blanco y Café SA de CV'),
        ('publirex', 'Publirex Mexicali SA de CV'),
        ('impulsora', 'Impulsora Inmobiliaria Tulum SA de CV'),
        ('rush', 'Industrias Cadillo SAPI de CV'),
        ('otro', 'Otro')
    ], string='Grupo Empresarial', default=lambda self: self.env.company.company_group if self.env.company.company_group else self.env.company.parent_id.company_group
    ,help='Marque el grupo empresarial al que pertenece el producto',readonly=True)

class ProductCategory(models.Model):
    _inherit = 'product.category'
    
    company_group = fields.Selection([
        ('hamburguesas', 'Hamburguesas Mafis SA de CV'),
        ('helados', 'Helados Mafis SA de CV'),
        ('sifam', 'Proyectos Sifam SA de CV'),
        ('hidro', 'Hidrológica Kuale SA de CV'),
        ('tinto5', 'Tintocinco SA de CV'),
        ('g_kuale', 'Gente Kuale SA de CV'),
        ('s_kuale', 'Servicios Kuale SA de CV'),
        ('kuale_srl', 'Kuale S de RL de CV'),
        ('gk_llc', 'Grupo Kuale USA LLC '),
        ('erben', 'Inmobiliaria Erben SA de CV'),
        ('mfda', 'Martha Fernanda Deutsch Azcárraga y Copropietarios'),
        ('ppt', 'Publipuentes Tamaulipas SA de CV'),
        ('c_kuale', 'Comercial Kuale SA de CV'),
        ('productora', 'Productora del Golfo SA de CV'),
        ('vdp', 'Video Producciones del Golfo SA de CV'),
        ('mr_motor', 'Mister Motor SA de CV'),
        ('express', 'Express Offshore de Mexico SA de CV'),
        ('ers', 'Especialistas en Reparto Seguro SA de CV'),
        ('operativos', 'Operativos de Franquicias SA de CV'),
        ('blanco_cafe', 'Blanco y Café SA de CV'),
        ('publirex', 'Publirex Mexicali SA de CV'),
        ('impulsora', 'Impulsora Inmobiliaria Tulum SA de CV'),
        ('rush', 'Industrias Cadillo SAPI de CV'),
        ('otro', 'Otro')
    ], string='Grupo Empresarial'
    ,help='Marque el grupo empresarial al que pertenece el producto',readonly=True)
    
    expense_ok = fields.Boolean(string='Es un gasto', default=False)
    
    # ========== CATEGORÍAS COMPARTIDAS ==========
    is_shared_category = fields.Boolean(
        string='Categoría Compartida',
        default=False,
        help='Si se marca, esta categoría será visible en todos los grupos empresariales. '
             'Si no, solo será visible en el grupo empresarial asignado.'
    )
    
    @api.onchange('is_shared_category')
    def _onchange_is_shared_category(self):
        """Cuando se marca como compartida: limpiar company_group.
        Cuando se desmarca: asignar el company_group de la empresa actual."""
        if self.is_shared_category:
            self.company_group = False
        else:
            company_group = self.env.company.company_group if hasattr(self.env.company, 'company_group') else None
            if not company_group:
                company_group = self.env.company.parent_id.company_group if self.env.company.parent_id else None
            if company_group:
                self.company_group = company_group
    
    @api.model
    def create(self, vals):
        if vals.get('is_shared_category'):
            vals['company_group'] = False
        elif vals.get('expense_ok'):
            vals['company_group'] = False
        else:
            company = self.env.company
            vals['company_group'] = (
                company.company_group 
                or company.parent_id.company_group
            )
        return super().create(vals)
    
    def write(self, vals):
        # Manejar is_shared_category en vals
        if vals.get('is_shared_category'):
            vals['company_group'] = False
        elif 'is_shared_category' in vals and not vals['is_shared_category']:
            # Se desactiva compartido: asignar grupo de la empresa actual
            company = self.env.company
            company_group = (
                company.company_group
                or (company.parent_id.company_group if company.parent_id else None)
            )
            if company_group and ('company_group' not in vals or not vals.get('company_group')):
                vals['company_group'] = company_group
        
        res = super().write(vals)
        company = self.env.company
        default_group = (
            company.company_group 
            or company.parent_id.company_group
        )
        for record in self:
            # No asignar grupo si es compartida
            if record.is_shared_category:
                if record.company_group:
                    record.company_group = False
            elif record.expense_ok:
                if record.company_group:
                    record.company_group = False
            else:
                if not record.company_group:
                    record.company_group = default_group
        return res
    
    # ========== _search PARA CATEGORÍAS COMPARTIDAS ==========
    @api.model
    def _search(self, domain, offset=0, limit=None, order=None):
        """
        Override search para filtrar categorías por company_group automáticamente.
        
        Reglas:
        1. Categorías con is_shared_category=True: visibles en todos los grupos
        2. Categorías sin company_group: visibles en todos los grupos (legacy/gastos)
        3. Categorías con company_group específico: solo visibles en ese grupo
        """
        company = self.env.company
        company_group = (
            company.company_group 
            or (company.parent_id.company_group if company.parent_id else None)
        )
        
        if company_group and not self.env.context.get('show_all_categories'):
            filter_domain = [
                '|', '|',
                ('is_shared_category', '=', True),
                ('company_group', '=', False),
                ('company_group', '=', company_group)
            ]
            domain = expression.AND([domain, filter_domain])
        
        return super(ProductCategory, self)._search(domain, offset=offset, limit=limit, order=order)

class ProductProduct(models.Model):
    _inherit = 'product.product'
    
    ieps_unit_price = fields.Float(string='Costo unitario con IEPs',compute='_compute_ieps_unit_price')
    
    @api.depends('avg_cost','product_tmpl_id.has_ieps')
    def _compute_ieps_unit_price(self):
        for line in self:
            if line.has_ieps:
                line.ieps_unit_price = line.avg_cost * 1.08
            else:
                line.ieps_unit_price = 0
    
    standard_price = fields.Float(
        string='Costo',
        digits=(16, 6)
    )

class ProductTemplate(models.Model):
    _inherit = 'product.template'
    
    # Added DW...
    price_increase_percentage = fields.Float(
        string="Porcentaje de Incremento (%)",
        default=10,
        help="Porcentaje de incremento que se aplicará al precio unitario de la última compra o entrada para calcular el precio de venta."
    )
    
    sat_code_id = fields.Many2one('sat.product.codes', string='Clave ProdServ',
        help='Clave de producto o servicio conforme al catalogo de c_ProdServ publicado en el portal del SAT')
    identification_number = fields.Char(string='NoIdentificación',
        help='número de parte,identificador del producto o del servicio, la clave de producto o servicio, SKU (número de referencia) ')
    third_party_id = fields.Char(string='ID de terceros',
        help='Código de vinculación para asociación con ticket de venta')
    unit_clave = fields.Many2one('cfdi.claveunidad', string='Clave unidad',
        help='Clave de unidad de medida estandarizada de conformidad con el catálogo c_ClaveUnidad publicado en el Portal del SAT')
    
    pixl_price_a = fields.Float(string='Precio A',help='precio autorizado por portal pixl', company_dependent=True, digits=(16, 2))
    pixl_price_b = fields.Float(string='Precio B', help='precio autorizado por portal pixl', company_dependent=True, digits=(16, 2))
    pixl_price_c = fields.Float(string='Precio C', help='precio autorizado por portal pixl', company_dependent=True, digits=(16, 2))
    
    asset_category_id = fields.Many2one(
        'account.asset.category', string='Tipo de Activo',
        company_dependent=True, ondelete="restrict")
    deferred_revenue_category_id = fields.Many2one(
        'account.asset.category', string='Tipo de ingresos diferidos',
        company_dependent=True, ondelete="restrict")
    
    #expenses
    general_account_code = fields.Char(
        string='Código cuenta gastos generales',
        help='Ej: 6000 o 600.01, depende de tu PGC')
    admin_account_code = fields.Char(
        string='Código cuenta gastos administrativos',
        help='Ej: 6010')
    sales_account_code = fields.Char(
        string='Código cuenta gastos venta y distribución',
        help='Ej: 6020')
    
    def _resolve_account_by_code(self, code, company):
        if not code or not company:
            return False
        return self.env['account.account'].search([
            ('code', '=', code),
            ('company_id', '=', company.id),
        ], limit=1)
    
    def _get_expense_account_by_center(self, center, company):
        self.ensure_one()
        code = False
        if center == 'general':
            code = self.general_account_code
        elif center == 'admin':
            code = self.admin_account_code
        elif center == 'sales':
            code = self.sales_account_code
        
        acc = self._resolve_account_by_code(code, company) if code else False
        if not acc:
            acc = self.property_account_expense_id or self.categ_id.property_account_expense_categ_id
        
        if acc and company and acc.company_id != company and acc.code:
            same = self._resolve_account_by_code(acc.code, company)
            acc = same or acc
        return acc
    
    # Administracion de empresa
    company_group = fields.Selection([
        ('hamburguesas', 'Hamburguesas Mafis SA de CV'),
        ('helados', 'Helados Mafis SA de CV'),
        ('sifam', 'Proyectos Sifam SA de CV'),
        ('hidro', 'Hidrológica Kuale SA de CV'),
        ('tinto5', 'Tintocinco SA de CV'),
        ('g_kuale', 'Gente Kuale SA de CV'),
        ('s_kuale', 'Servicios Kuale SA de CV'),
        ('kuale_srl', 'Kuale S de RL de CV'),
        ('gk_llc', 'Grupo Kuale USA LLC '),
        ('erben', 'Inmobiliaria Erben SA de CV'),
        ('mfda', 'Martha Fernanda Deutsch Azcárraga y Copropietarios'),
        ('ppt', 'Publipuentes Tamaulipas SA de CV'),
        ('c_kuale', 'Comercial Kuale SA de CV'),
        ('productora', 'Productora del Golfo SA de CV'),
        ('vdp', 'Video Producciones del Golfo SA de CV'),
        ('mr_motor', 'Mister Motor SA de CV'),
        ('express', 'Express Offshore de Mexico SA de CV'),
        ('ers', 'Especialistas en Reparto Seguro SA de CV'),
        ('operativos', 'Operativos de Franquicias SA de CV'),
        ('blanco_cafe', 'Blanco y Café SA de CV'),
        ('publirex', 'Publirex Mexicali SA de CV'),
        ('impulsora', 'Impulsora Inmobiliaria Tulum SA de CV'),
        ('rush', 'Industrias Cadillo SAPI de CV'),
        ('otro', 'Otro')
    ], string='Grupo Empresarial', default=lambda self: self.env.company.company_group if self.env.company.company_group else self.env.company.parent_id.company_group
    ,help='Marque el grupo empresarial al que pertenece el producto',readonly=True)
    
    # ========== PRODUCTOS COMPARTIDOS ==========
    is_shared_product = fields.Boolean(
        string='Producto Compartido',
        default=False,
        help='Si se marca, este producto será visible en todos los grupos empresariales. '
             'Si no, solo será visible en el grupo empresarial asignado.'
    )
    
    #standard_price
    standard_price = fields.Float(string='Costo',digits=(16,6), )
    # utility_percentage = fields.Float(string="Utilidad %", company_dependent=True)
    utility_price = fields.Float(string="Utilidad $", company_dependent=True, compute='_compute_utility_price',store=True)
    tax_object_id = fields.Many2one('cfdi.claveobjetoimp',string='Objeto de impuesto',)
    
    # filtering to products
    is_pxc = fields.Boolean(string='PxC',default=False)
    is_lgp = fields.Boolean(string='LGP',default=False)
    is_dh = fields.Boolean(string='DH',default=False)
    has_ieps = fields.Boolean(string='IEPs',default=False)
    
    product_tag_ids = fields.Many2many(
        string="Product Template Tags",
        comodel_name='product.tag',
        relation='product_tag_product_template_rel',
        domain="['|', ('category_id', '=', categ_id), ('category_id', '=', False)]",
    )
    
    sat_operation_type = Many2one('sat.tipo.operacion',string='Tipo de operacion global SAT',domain="[('supplier', '=', 'global')]")
    nat_sat_operation_type = Many2one('sat.tipo.operacion', string='Tipo de operacion nacional SAT', domain="[('supplier', '=', 'nacional')]")
    int_sat_operation_type = Many2one('sat.tipo.operacion', string='Tipo de operacion internacional SAT', domain="[('supplier', '=', 'extranjero')]")
    
    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        clave_objeto = self.env['cfdi.claveobjetoimp'].search([('Clave_objetoimp', '=', '02')], limit=1)
        if clave_objeto:
            res['tax_object_id'] = clave_objeto.id
        
        if 'categ_id' in res:
            res['categ_id'] = False
        return res
    
    @api.depends('list_price','standard_price')
    def _compute_utility_price(self):
        for product in self:
            if product.standard_price > 0:
                product.utility_price = product.list_price - product.standard_price
    
    @api.onchange('list_price','standard_price','price_increase_percentage')
    def _onchange_utility_price(self):
        for product in self:
            if product.standard_price > 0:
                product.utility_price = product.list_price - product.standard_price
    
    def _get_asset_accounts(self):
        res = super(ProductTemplate, self)._get_asset_accounts()
        if self.asset_category_id:
            res['stock_input'] = self.property_account_expense_id
        if self.deferred_revenue_category_id:
            res['stock_output'] = self.property_account_income_id
        return res
    
    @api.depends('standard_price', 'price_increase_percentage')
    def _compute_list_price(self):
        for product in self:
            if product.standard_price > 0:
                product.list_price = product.standard_price * (1 + (product.price_increase_percentage / 100))
    
    @api.onchange('price_increase_percentage')
    def _onchange_price_increase_percentage(self):
        for product in self:
            if product.price_increase_percentage and product.standard_price:
                product.list_price = product.standard_price * (1 + product.price_increase_percentage / 100)
    
    @api.onchange('list_price')
    def _onchange_list_price(self):
        for product in self:
            if product.list_price and product.standard_price:
                product.price_increase_percentage = ((product.list_price / product.standard_price) - 1) * 100
    
    # ========== PRODUCTOS COMPARTIDOS ==========
    @api.onchange('is_shared_product')
    def _onchange_is_shared_product(self):
        """
        Cuando se marca como compartido: limpiar company_group.
        Cuando se desmarca: asignar el company_group de la empresa actual.
        Si la categoría no está compartida, lanzar wizard de confirmación.
        """
        if self.is_shared_product:
            self.company_group = False
            # Verificar si la categoría está compartida
            if self.categ_id and not self.categ_id.is_shared_category:
                return {
                    'warning': {
                        'title': _('Categoría no compartida'),
                        'message': _(
                            'La categoría "%s" no está marcada como compartida. '
                            'Para que el producto sea accesible desde otros grupos empresariales, '
                            'la categoría también debe ser compartida. '
                            'Guarde el producto para abrir el asistente de confirmación, '
                            'o comparta la categoría manualmente.'
                        ) % self.categ_id.display_name,
                    }
                }
        else:
            # Asignar company_group de la empresa actual
            company_group = self.env.company.company_group if hasattr(self.env.company, 'company_group') else None
            if not company_group:
                company_group = self.env.company.parent_id.company_group if self.env.company.parent_id else None
            if company_group:
                self.company_group = company_group
    
    # ========== CREATE PARA PRODUCTOS COMPARTIDOS ==========
    @api.model
    def create(self, vals):
        if vals.get('is_shared_product'):
            vals['company_group'] = False
        # Si no es compartido y no tiene company_group, asignar el de la empresa actual
        elif not vals.get('is_shared_product'):
            if not vals.get('company_group'):
                company = self.env.company
                company_group = (
                    company.company_group 
                    or (company.parent_id.company_group if company.parent_id else None)
                )
                if company_group:
                    vals['company_group'] = company_group
        
        return super().create(vals)
    
    # ========== WRITE PARA PRODUCTOS COMPARTIDOS ==========
    def write(self, vals):
        tracked_fields = {'pixl_price_a', 'pixl_price_b', 'pixl_price_c'}
        record_changes = []
        for product in self:
            price_old = {
                'pixl_price_a': product.pixl_price_a,
                'pixl_price_b': product.pixl_price_b,
                'pixl_price_c': product.pixl_price_c,
            }
            if any(field in vals for field in tracked_fields):
                record_changes.append((product, price_old))
        
        if vals.get('is_shared_product'):
            vals['company_group'] = False
            # Auto-compartir la categoría si no lo está
            for record in self:
                if record.categ_id and not record.categ_id.is_shared_category:
                    record.categ_id.sudo().write({
                        'is_shared_category': True,
                        'company_group': False,
                    })
        elif 'is_shared_product' in vals and not vals['is_shared_product']:
            for record in self:
                if 'company_group' not in vals or not vals.get('company_group'):
                    company = self.env.company
                    company_group = (
                        company.company_group 
                        or (company.parent_id.company_group if company.parent_id else None)
                    )
                    if company_group:
                        vals['company_group'] = company_group
        
        res = super(ProductTemplate, self).write(vals)
        
        for product, old_vals in record_changes:
            new_vals = {
                'pixl_price_a': product.pixl_price_a,
                'pixl_price_b': product.pixl_price_b,
                'pixl_price_c': product.pixl_price_c,
            }
            if (old_vals['pixl_price_a'] != new_vals['pixl_price_a'] or
                old_vals['pixl_price_b'] != new_vals['pixl_price_b'] or
                old_vals['pixl_price_c'] != new_vals['pixl_price_c']):
                self.env['contabilidad_kuale.pixl_price_history'].sudo().create({
                    'product_id': product.id,
                    'third_party_id': product.third_party_id,
                    'price_a': new_vals['pixl_price_a'],
                    'price_b': new_vals['pixl_price_b'],
                    'price_c': new_vals['pixl_price_c'],
                })
        
        return res
    
    # ========== _search PARA PRODUCTOS COMPARTIDOS ==========
    @api.model
    def _search(self, domain, offset=0, limit=None, order=None):
        """
        Override search para filtrar productos por company_group automáticamente.
        
        Reglas:
        1. Productos con is_shared_product=True: visibles en todos los grupos
        2. Productos sin company_group: visibles en todos los grupos (legacy)
        3. Productos con company_group específico: solo visibles en ese grupo
        """
        company = self.env.company
        company_group = (
            company.company_group 
            or (company.parent_id.company_group if company.parent_id else None)
        )
        
        if company_group and not self.env.context.get('show_all_products'):
            filter_domain = [
                '|', '|',
                ('is_shared_product', '=', True),
                ('company_group', '=', False),
                ('company_group', '=', company_group)
            ]
            domain = expression.AND([domain, filter_domain])
        
        return super(ProductTemplate, self)._search(domain, offset=offset, limit=limit, order=order)
    
    # fabrication
    elaborate_ok = fields.Boolean(string='Se puede fabricar', default=False)
    bom_line_ids = fields.One2many('product.bom.line', 'product_tmpl_id', string='Lista de materiales')
    total_recipe_cost = fields.Float(
        string="Costo total de receta",
        compute="_compute_total_recipe_cost",
        store=False,
        digits=(16, 6)
    )
    
    @api.depends('bom_line_ids')
    def _compute_total_recipe_cost(self):
        for product in self:
            product.total_recipe_cost = sum(line.total_price for line in product.bom_line_ids)
    
    def get_total_recipe_cost(self, company_id=None, visited=None):
        self.ensure_one()
        company_id = company_id or self.env.company.id
        
        if visited is None:
            visited = set()
        
        if self.id in visited:
            _logger.warning(f"Ciclo detectado en BOM de '{self.name}'. Se omite el cálculo recursivo.")
            return 0.0 #puede ser un return None en caso de que afecte numeros reales
        
        visited.add(self.id)
        total = 0.0
        for line in self.bom_line_ids:
            component = line.component_id
            if not component:
                continue
            
            tmpl = component.product_tmpl_id
            if tmpl.elaborate_ok:
                cost = tmpl.get_total_recipe_cost(company_id, visited=visited)
            else:
                cost = component.with_company(company_id).standard_price
            
            total += line.quantity * cost
        
        return total
    
    def update_standard_price_from_recipe(self, company_id=None):
        for product in self:
            if product.elaborate_ok:
                cost = product.get_total_recipe_cost(company_id=company_id or self.env.company.id)
                product.with_company(company_id or self.env.company.id).standard_price = cost
    
    @api.model
    def update_sales_price_from_last_purchase(self):
        companies = self.env['res.company'].sudo().search([])
        products = self.sudo().search([])
        for company in companies:
            for product in products:
                last_purchase_line = self.env['purchase.order.line'].sudo().search([
                    ('product_id.product_tmpl_id', '=', product.id),
                    ('order_id.company_id', '=', company.id),
                    ('order_id.state', 'in', ['purchase', 'done']),
                ], order='create_date desc', limit=1)
                
                if last_purchase_line:
                    product.sudo().with_company(company.id).standard_price = last_purchase_line.price_unit
                    if product.price_increase_percentage:
                        product.sudo().with_company(company.id).list_price = last_purchase_line.price_unit * (
                            1 + product.price_increase_percentage / 100
                        )
                
                if product.elaborate_ok:
                    cost = product.sudo().get_total_recipe_cost(company_id=company.id or self.env.company.id)
                    product.sudo().with_company(company.id or self.env.company.id).standard_price = cost
    
    def _create_cost_history(self):
        companies = self.env['res.company'].search([('parent_id', '!=', False)]) # Solo sucursales
        for branch in companies:
            products = self.search([('elaborate_ok', '=', True)])
            for product in products:
                # Obtener el costo actual en esta sucursal
                recipe_cost = product.get_total_recipe_cost(company_id=branch.id)
                if recipe_cost <= 0:
                    continue
                
                # Buscar último historial para esta sucursal
                last = self.env['product.cost.history'].search([
                    ('product_id', '=', product.id),
                    ('branch_id', '=', branch.id)
                ], order='date desc', limit=1)
                
                if last and round(last.recipe_cost, 6) == round(recipe_cost, 6):
                    continue
                
                # Crear historial
                cost_history = self.env['product.cost.history'].create({
                    'product_id': product.id,
                    'company_id': branch.parent_id.id if branch.parent_id else branch.id,
                    'branch_id': branch.id,
                    'recipe_cost': recipe_cost,
                })
                
                # Agregar detalle de ingredientes
                for line in product.bom_line_ids:
                    cost = 0.0
                    if line.component_id:
                        tmpl = line.component_id.product_tmpl_id
                        if tmpl.elaborate_ok:
                            cost = tmpl.get_total_recipe_cost(company_id=branch.id)
                        else:
                            cost = line.component_id.with_company(branch.id).standard_price
                    
                    self.env['product.cost.history.line'].create({
                        'cost_history_id': cost_history.id,
                        'component_id': line.component_id.id,
                        'quantity': line.quantity,
                        'uom': line.uom.id,
                        'unit_price': cost,
                        'total_price': cost * line.quantity,
                    })
    
    def _scheduler_update_sales_prices(self):
        print("Actualizacion de precios funcionando everything is right")
        self.update_sales_price_from_last_purchase()
        self._create_cost_history()
        for product in self.search([('elaborate_ok', '=', True)]):
            product.update_standard_price_from_recipe()


class ProductBOMLine(models.Model):
    _name = 'product.bom.line'
    _description = 'Linea de lista de productos para fabricacion'
    
    product_tmpl_id = fields.Many2one('product.template', string='Producto')
    currency_id = fields.Many2one('res.currency', string='Moneda', required=True,
                                   default=lambda self: self.env.company.currency_id)
    component_id = fields.Many2one('product.product', string='Componente', required=True, ondelete='cascade')
    qty_available = fields.Float(compute='_compute_availability_qty',digits=(16, 6), string='Cantidad Disponible')
    quantity = fields.Float(string='Cantidad', digits=(16, 6))
    uom = fields.Many2one('uom.uom', string='Udm', compute='_compute_uom', store=False)
    has_ieps = fields.Boolean(string='Aplica IEPs', related='component_id.has_ieps')
    ieps_unit_price = fields.Float(string='Costo unitario con IEPs', compute='_compute_ieps_unit_price', store=False)
    unit_price = fields.Float(
        string="Costo unitario",
        compute="_compute_unit_price",
        digits=(16, 6),
        store=False
    )
    total_price = fields.Monetary(
        string="Precio total",
        compute="_compute_total_price",
        digits=(16, 6),
        store=False
    )
    
    @api.depends('component_id')
    def _compute_availability_qty(self):
        for line in self:
            qty = 0.0
            if line.component_id:
                company = line.product_tmpl_id.env.company
                warehouse = line.env['stock.warehouse'].search([('company_id', '=', company.id)], limit=1)
                if warehouse:
                    stock_location = warehouse.lot_stock_id
                    qty = line.env['stock.quant']._get_available_quantity(
                        line.component_id, stock_location, strict=True
                    )
            line.qty_available = qty
    
    @api.depends('component_id')
    def _compute_uom(self):
        for line in self:
            line.uom = line.component_id.uom_id.id if line.component_id else ''
    
    @api.depends('component_id')
    def _compute_unit_price(self):
        for line in self:
            tmpl = line.component_id.product_tmpl_id
            if tmpl.elaborate_ok:
                line.unit_price = tmpl.get_total_recipe_cost(company_id=self.env.company.id)
            else:
                line.unit_price = line.component_id.with_company(self.env.company).standard_price
    
    @api.depends('quantity', 'unit_price')
    def _compute_total_price(self):
        for line in self:
            if line.has_ieps:
                line.total_price = (line.unit_price * line.quantity) * 1.08
            else:
                line.total_price = line.quantity * line.unit_price
    
    @api.depends('component_id','unit_price')
    def _compute_ieps_unit_price(self):
        for line in self:
            if line.has_ieps:
                line.ieps_unit_price = line.unit_price * 1.08
            else:
                line.ieps_unit_price = line.unit_price

class ProductCostHistory(models.Model):
    _name = 'product.cost.history'
    _description = 'Historial de costo de producto fabricado'
    
    product_id = fields.Many2one('product.template', string='Producto', required=True)
    company_id = fields.Many2one('res.company', string='Compañía', required=True, default=lambda self: self.env.company)
    branch_id = fields.Many2one('res.company', string='Sucursal', required=True, default=lambda self: self.env.company)
    date = fields.Date(string='Fecha', required=True, default=fields.Date.context_today)
    recipe_cost = fields.Float(string='Costo Total de Receta', required=True,digits=(16, 6))
    cost_line_ids = fields.One2many('product.cost.history.line', 'cost_history_id', string='Detalles de Ingredientes')

class ProductCostHistoryLine(models.Model):
    _name = 'product.cost.history.line'
    _description = 'Detalle de Costo de Ingrediente en Fabricación'
    
    cost_history_id = fields.Many2one('product.cost.history', string='Historial de Costo', required=True,
                                       ondelete="cascade")
    component_id = fields.Many2one('product.product', string='Componente', required=True)
    quantity = fields.Float(string='Cantidad', required=True)
    uom = fields.Many2one('uom.uom', string='Udm')
    unit_price = fields.Float(string='Costo Unitario', required=True,digits=(16, 6))
    total_price = fields.Float(string='Costo Total', required=True,digits=(16, 6))

class ProductFabricationBatch(models.Model):
    _name = 'product.fabrication.batch'
    _description = 'Lote de fabricacion de productos'
    
    date = fields.Datetime(string='Fecha', required=True, default=fields.Date.context_today)
    company_id = fields.Many2one('res.company',string='Empresa', domain="[('is_branch', '=', False)]",
                                  required=True)
    branch_id = fields.Many2one('res.company', string='Sucursal',
                                 domain="['|', ('parent_id', '=', company_id), ('id', '=', company_id)]", required=True)
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('done', 'Fabricado'),
        ('cancel', 'Cancelado'),
    ],string='Estado',default='draft')
    line_ids = fields.One2many('product.fabrication.batch.line', 'batch_id', string='Productos a fabricar')
    
    def _validate_stock_availability(self):
        for batch in self:
            company = batch.branch_id
            warehouse = self.env['stock.warehouse'].search([('company_id', '=', company.id)], limit=1)
            if not warehouse:
                raise UserError(f"No se encontró almacén para la sucursal {company.name}")
            
            stock_location = warehouse.lot_stock_id
            for line in batch.line_ids:
                product = line.product_id
                if not product.elaborate_ok:
                    continue
                
                for bom_line in product.bom_line_ids:
                    component = bom_line.component_id
                    if not component:
                        continue
                    
                    required_qty = bom_line.quantity * line.quantity
                    
                    # Obtener disponibilidad en la ubicación de stock
                    qty_available = self.env['stock.quant']._get_available_quantity(
                        component, stock_location, strict=True
                    )
                    
                    if qty_available < required_qty:
                        body_msg = (
                            f"Problemas de stock"
                            f"No hay suficiente producto para fabricacion en sucursal {self.branch_id}"
                            f"Revisar stock de {component.display_name}"
                        )
                        self._notify_out_stock(body_msg)
                        raise UserError(
                            f"No hay suficiente stock de '{component.display_name}' en {company.name}.\n"
                            f"Disponible: {qty_available}, Requerido: {required_qty} para fabricar {product.name}"
                        )
    
    def _notify_out_stock(self,msg):
        odoodbot_partner = self.env['res.partner'].search([('name', '=', 'OdooBot')], limit=1)
        # Buscar usuarios administradores relacionados a la empresa o sucursal
        admin_users = self.env['res.users'].search([
            '|',
            ('company_id', '=', self.company_id.id),
            ('company_ids', 'in', [self.branch_id.id]),
            ('groups_id', 'in', self.env.ref('base.group_system').id),
        ])
        
        if not admin_users:
            return # O podrías loggear o notificar que no se encontraron admins
        
        # Crear el mensaje como OdooBot
        message = self.env['mail.message'].create({
            'model': 'res.users',
            'res_id': self.env.user.id, # no afecta realmente aquí
            'message_type': 'notification',
            'subtype_id': self.env.ref('mail.mt_note').id,
            'body': msg,
            'subject': "Falta de productos para fabricacion",
            'author_id': odoodbot_partner.id,
        })
        
        # Crear una notificación para cada administrador
        notifications = []
        for user in admin_users:
            if user.partner_id:
                notifications.append({
                    'mail_message_id': message.id,
                    'res_partner_id': user.partner_id.id,
                    'notification_type': 'inbox',
                    'notification_status': 'sent',
                })
        
        if notifications:
            self.env['mail.notification'].create(notifications)
    
    def fabricate_products(self):
        self._validate_stock_availability()
        for batch in self:
            if batch.state != 'draft':
                continue
            
            company = batch.branch_id
            warehouse = self.env['stock.warehouse'].search([('company_id', '=', company.id)], limit=1)
            if not warehouse:
                raise UserError(f"No se encontró almacén para la sucursal {company.name}")
            
            stock_location = warehouse.lot_stock_id
            customer_location = self.env.ref('stock.stock_location_customers') # ubicación ficticia
            
            # Preparar listas de movimientos
            pickings = []
            for line in batch.line_ids:
                product = line.product_id
                if not product.elaborate_ok:
                    continue
                
                # 1. Picking de salida: descontar componentes
                picking_out = self.env['stock.picking'].create({
                    'picking_type_id': warehouse.out_type_id.id,
                    'location_id': stock_location.id,
                    'location_dest_id': customer_location.id,
                    'origin': f'Fabricación: {product.name}',
                    'company_id': company.id,
                })
                
                for bom_line in product.bom_line_ids:
                    self.env['stock.move'].create({
                        'name': bom_line.component_id.name,
                        'product_id': bom_line.component_id.id,
                        'product_uom_qty': bom_line.quantity * line.quantity,
                        'product_uom': bom_line.component_id.uom_id.id,
                        'location_id': stock_location.id,
                        'location_dest_id': customer_location.id,
                        'picking_id': picking_out.id,
                        'company_id': company.id,
                    })
                
                picking_out.action_confirm()
                picking_out.action_assign()
                if picking_out.state in ['assigned']:
                    picking_out.button_validate()
                
                # 2. Picking de entrada: ingresar producto terminado
                picking_in = self.env['stock.picking'].create({
                    'picking_type_id': warehouse.in_type_id.id,
                    'location_id': customer_location.id,
                    'location_dest_id': stock_location.id,
                    'origin': f'Fabricación: {product.name}',
                    'company_id': company.id,
                })
                
                self.env['stock.move'].create({
                    'name': product.name,
                    'product_id': product.product_variant_id.id,
                    'product_uom_qty': line.quantity,
                    'product_uom': product.uom_id.id,
                    'location_id': customer_location.id,
                    'location_dest_id': stock_location.id,
                    'picking_id': picking_in.id,
                    'company_id': company.id,
                })
                
                picking_in.action_confirm()
                picking_in.action_assign()
                if picking_in.state in ['assigned']:
                    picking_in.button_validate()
            
            batch.state = 'done'
    
    def unlink(self):
        for record in self:
            if record.state in ['done','cancel']:
                raise ValidationError("No se puede eliminar un registro cuyo estatus sea 'hecho' o 'cancelado'")
        return super(ProductFabricationBatch,self).unlink()

class ProductFabricationBatchLine(models.Model):
    _name = 'product.fabrication.batch.line'
    _description = 'Línea de producto a fabricar'
    
    batch_id = fields.Many2one('product.fabrication.batch', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.template', required=True,
                                  domain="[('elaborate_ok', '=', True)]", string="Producto a fabricar")
    quantity = fields.Float(string="Cantidad a fabricar", required=True)
    uom = fields.Many2one('uom.uom',string='Unidad de medida',compute='_compute_uom',store=True)
    
    @api.depends('product_id')
    def _compute_uom(self):
        for line in self:
            line.uom = line.product_id.uom_po_id.id if line.product_id.uom_id else None

class PixlPriceHistory(models.Model):
    _name = 'contabilidad_kuale.pixl_price_history'
    _description = 'Histórico de Precios PIXL'
    _order = 'date desc'
    
    date = fields.Datetime(string='Fecha', default=fields.Datetime.now, required=True)
    product_id = fields.Many2one('product.template', string='Producto', required=True, ondelete='cascade')
    third_party_id = fields.Char(string='Clave PIXL')
    price_a = fields.Float(string='Precio A')
    price_b = fields.Float(string='Precio B')
    price_c = fields.Float(string='Precio C')
