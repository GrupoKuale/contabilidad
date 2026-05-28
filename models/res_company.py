
from odoo import models, fields, api, _
from odoo.exceptions import RedirectWarning


class ResCompany(models.Model):
    _inherit = "res.company"

    requires_sale_authorization = fields.Boolean(string="Requiere Autorización para Cotizaciones de venta",
                                                 default=False)
    requires_purchase_authorization = fields.Boolean(string="Requiere Autorización para Órdenes de Compra",
                                                     default=False
    )
    regimen_fiscal = fields.Many2one('cfdi.claveregimenfiscal',string="Régimen Fiscal")

    trade_name = fields.Char(string='Nombre comercial', help="Nombre comercial de la empresa")

    single_concept = fields.Boolean(string='Concepto único',
                                    help='Marcar si las facturas de clientes 1-1 son de un solo concepto')
    billable = fields.Boolean(string='Factura cliente 1-1', default=False)
    client_serial_number = fields.Char(string='Serial 1-1', help="Numero de serie para facturas a clientes")
    global_serial_number = fields.Char(string='Serial global', help="Numero de serie para facturas globales")
    client_folio_number = fields.Integer(string='Folio 1-1', help="Numero de Folio para facturas a clientes", default=1,
                                         readonly=True)
    global_folio_number = fields.Integer(string='Folio global', help="Numero de Folio para facturas globales",
                                         default=1, readonly=True)
    # SAT CFDI AUTOMATIZATION
    fiel_cert = fields.Binary(string='Fiel .cert')
    fiel_key = fields.Binary(string='Fiel .key')
    fiel_password = fields.Char(string='Fiel contraseña')
    is_branch = fields.Boolean(string="Es Sucursal", compute="_compute_is_branch", store=True)
    company_clave = fields.Char(string='Clave de identificación',
                                help='clave compuesta para identificar las empresas y sucursales')

    # accounts

    account_payable = fields.Many2one('account.group', string='Cuentas por pagar',domain=lambda self: [('company_id','=',self.env.company.id)])
    account_receivable = fields.Many2one('account.group', string='Cuentas por cobrar',domain=lambda self: [('company_id','=',self.env.company.id)])

    # Configuración de Niveles de Aprobación
    po_level_1_active = fields.Boolean(string="Activar Nivel 1 (Director / Final)", default=True)
    po_level_1_users = fields.Many2many('res.users', 'po_l1_users_rel', string="Aprobadores Nivel 1")

    po_level_2_active = fields.Boolean(string="Activar Nivel 2 (Departamento)", default=True)
    po_level_2_users = fields.Many2many('res.users', 'po_l2_users_rel', string="Aprobadores Nivel 2")

    po_level_3_active = fields.Boolean(string="Activar Nivel 3 (Subdepartamento)", default=True)
    po_level_3_users = fields.Many2many('res.users', 'po_l3_users_rel', string="Aprobadores Nivel 3")

    po_level_4_active = fields.Boolean(string="Activar Nivel 4 (Usuarios Base)", default=True)
    po_level_4_users = fields.Many2many('res.users', 'po_l4_users_rel', string="Aprobadores Nivel 4")

    #Limite de aprobacion inmediata
    po_approval_amount_limit = fields.Monetary(
        string="Límite para Aprobación Inmediata",
        currency_field='currency_id',
        default=0.0,
        help="Si el monto de la OC es inferior a este límite, solo requerirá la aprobación del nivel inmediato superior, sin escalar hasta el Nivel 1."
    )

    #Límites de Solicitud por Usuario ---
    po_user_daily_limit = fields.Integer(
        string="Límite Diario de Solicitudes (Cantidad)",
        default=0,
        help="Número máximo de órdenes de compra que un usuario puede solicitar aprobar en un día. 0 = Sin límite."
    )
    po_user_monthly_limit = fields.Integer(
        string="Límite Mensual de Solicitudes (Cantidad)",
        default=0,
        help="Número máximo de órdenes de compra que un usuario puede solicitar aprobar en un mes. 0 = Sin límite."
    )

    # Proveedores de Planta (no requieren autorización)
    po_plant_supplier_ids = fields.Many2many(
        'res.partner',
        'company_plant_supplier_rel',
        'company_id',
        'partner_id',
        string="Proveedores de Planta",
        domain="[('supplier_rank', '>', 0)]",
        help="Proveedores que no requieren pasar por el flujo de autorización. "
             "Al solicitar aprobación, se aprueban automáticamente."
    )

    @api.onchange('id')
    def _onchange_company(self):
        print('self id: ', self.id)
        if self.id:
            return {
                'domain': {
                    'account_payable': [('company_id', '=', self.id)],
                    'account_receivable': [('company_id', '=', self.id)],
                }
            }

    # fabrication inventory
    location_production_id = fields.Many2one(
        "stock.location", string="Ubicación de Producción", readonly=True
    )

    # facturacion
    client_invoice_logo = fields.Binary(string='Logo factura al cliente', help='Este logo es el que se mostrara en el pdf de la factura')
    client_invoice_color = fields.Selection([
        ('1','Dairy Queen'),
        ('2','Tinto5'),
        ('4','Carls Jr'),
        ('3','HidroSk'),
        ('5','Kuale'),
        ('6','MFDA y Copropietario'),
    ], string='Colores factura al cliente')

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
    ], string='Grupo Empresarial',required=True)

    #SAT CSD files
    csd_cert = fields.Binary(string='CSD .cert')
    csd_key = fields.Binary(string='CSD .key')
    csd_password = fields.Char(string='CSD password')

    # Relación para elegir la plantilla de correo específica de cada empresa
    invoice_email_template_id = fields.Many2one(
        'mail.template', 
        string='Plantilla de Correo Facturación',
        domain="[('model_id.model', '=', 'contabilidad_kuale.ticket_monitor')]",
        help="Selecciona la plantilla que se enviará automáticamente al timbrar desde el sitio web."
    )
    
    missing_product_email_template_id = fields.Many2one(
        'mail.template',
        string='Plantilla de Producto Faltante',
        domain="[('model_id.model', '=', 'res.company')]",
        help="Plantilla que se enviará cuando se intente subir un ticket con productos no registrados."
    )
    
    ticket_error_channel_id = fields.Many2one(
        'discuss.channel',
        string='Canal de Alertas de Sistema',
        help="Canal donde se notificarán los errores al intentar subir tickets (ej. productos faltantes)."
    )

    cp_invoice_web = fields.Char(string='CP Facturacion', help="Codigo postal para facturacion Portal Web")

    @api.depends("parent_id")
    def _compute_is_branch(self):
        for company in self:
            company.is_branch = bool(company.parent_id)

    @api.model
    def create_production_locations(self):
        """Crea un almacén y la ubicación de producción para cada empresa si no existen."""
        print('initializing create production_locations')
        for company in self.search([]):
            # Buscar el almacén de la empresa o crearlo si no existe
            warehouse = self.env["stock.warehouse"].sudo().search([("company_id", "=", company.id)], limit=1)
            if not warehouse:
                warehouse = self.env["stock.warehouse"].create({
                    "name": f"Almacén {company.name}",
                    "code": f"WH{company.id}",
                    "company_id": company.id,
                })

            # Usar la ubicación principal del almacén como padre
            location_parent = warehouse.lot_stock_id

            # Si ya tiene una ubicación de producción, saltar
            if company.location_production_id:
                continue

            # Crear la ubicación de producción dentro del almacén
            location = self.env["stock.location"].sudo().create({
                "name": "Área de Producción",
                "usage": "internal",
                "company_id": company.id,
                "location_id": location_parent.id,
            })
            company.location_production_id = location.id

    @api.model
    def create(self, vals):
        company = super().create(vals)
        if company.parent_id:
            company.fiel_cert = company.parent_id.fiel_cert
            company.fiel_key = company.parent_id.fiel_key
            company.fiel_password = company.parent_id.fiel_password

        # Asegúrate de crear almacén y ubicación de producción si no existen
        self.env['res.company'].sudo().browse(company.id).create_production_locations()
        return company

    def _validate_fiscalyear_lock(self, values):
        if values.get('fiscalyear_lock_date'):
            draft_entries = self.env['account.move'].search([
                ('company_id', 'in', self.ids),
                ('state', '=', 'draft'),
                ('date', '<=', values['fiscalyear_lock_date'])])
            if draft_entries:
                error_msg = _('There are still unposted entries in the '
                              'period you want to lock. You should either post '
                              'or delete them.')
                action_error = {
                    'view_mode': 'tree',
                    'name': 'Unposted Entries',
                    'res_model': 'account.move',
                    'type': 'ir.actions.act_window',
                    'domain': [('id', 'in', draft_entries.ids)],
                    'search_view_id': [self.env.ref(
                        'account.view_account_move_filter').id, 'search'],
                    'views': [[self.env.ref(
                        'account.view_move_tree').id, 'list'],
                              [self.env.ref('account.view_move_form').id,
                               'form']],
                }
                raise RedirectWarning(error_msg, action_error,
                                      _('Show unposted entries'))
            unreconciled_statement_lines = self.env[
                'account.bank.statement.line'].search([
                ('company_id', 'in', self.ids),
                ('is_reconciled', '=', False),
                ('date', '<=', values['fiscalyear_lock_date']),
                ('move_id.state', 'in', ('draft', 'posted')),
            ])
            if unreconciled_statement_lines:
                error_msg = _(
                    "There are still unreconciled bank statement lines in the "
                    "period you want to lock."
                    "You should either reconcile or delete them.")
                action_error = {
                    'view_mode': 'tree',
                    'name': 'Unreconciled Transactions',
                    'res_model': 'account.bank.statement.line',
                    'type': 'ir.actions.act_window',
                    'domain': [('id', 'in', unreconciled_statement_lines.ids)],
                    'views': [[self.env.ref(
                        'contabilidad_kuale.view_bank_statement_line_tree').id,
                               'list']]
                }
                raise RedirectWarning(error_msg, action_error,
                                      _('Show Unreconciled Bank'
                                        ' Statement Line'))
