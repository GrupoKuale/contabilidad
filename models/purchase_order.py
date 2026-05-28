import re
import logging
from datetime import datetime
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.osv import expression
from odoo.tools.float_utils import float_compare, float_is_zero
from datetime import datetime, time
from dateutil.relativedelta import relativedelta

from lxml import etree
import base64

_logger = logging.getLogger(__name__)

class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    def _get_branch_domain(self):
        company = self.env.company
        if company.is_branch:
            return [('parent_id', '=', company.parent_id.id)]
        else:
            return [('is_branch', '=', True), ('parent_id', '=', company.id)]

    admin_email = fields.Char(compute='_compute_admin_email', string='Emails Administradores')

    additional_files = fields.One2many('contabilidad_kuale.additional_file',
                                       'purchase_order_id', string='Archivos digitales')

    # MarkUP
    has_markup = fields.Boolean(string='Aplica Markup', default=False)
    factor = fields.Float(string='Factor', digits=(16, 6))

    markup_total = fields.Float(string='Markup Total', digits=(16, 2), compute='_compute_markup_total')
    markup_total_iva = fields.Float(string='Markup Total (IVA)', compute='_compute_markup_total_iva', digits=(16, 2))

    # UUID
    uuid = fields.Char(string='UUID factura')
    invoice_folio = fields.Char(string='Folio de factura')

    # CFDI data del XML
    cfdi_metodo_pago = fields.Char(string='Método Pago CFDI', help='Clave MetodoPago del XML (ej: PUE, PPD)')
    cfdi_forma_pago = fields.Char(string='Forma Pago CFDI', help='Clave FormaPago del XML (ej: 01, 02, 99)')
    cfdi_moneda = fields.Char(string='Moneda CFDI', help='Clave Moneda del XML (ej: MXN, USD)')

    # sell_note
    sale_note_total = fields.Float(string="Total de nota de venta")
    invoice_date = fields.Date(string='Fecha de Factura')

    # Override fields to support 6 decimals
    product_packaging_qty = fields.Float(
        digits=(16, 6),  # 6 decimales
        string='Cantidad de embalaje'
    )

    product_qty = fields.Float(digits=(16, 6), string='Cantidad')

    account_move_ids = fields.One2many('account.move.line', 'purchase_id', string='Apuntes contables')

    # seccion de gastos
    branch_id = fields.Many2one('res.company', string='Sucursal', domain=lambda self: self._get_branch_domain())
    diot_ids = fields.One2many('purchase.order.diot', 'order_id', string='DIOT')
    fiscal_ids = fields.One2many('purchase.order.fiscal', 'order_id', string='Fiscal')

    #Control de aprobaciones
    approval_level = fields.Selection([
        ('4', 'Nivel 4 (Base)'),
        ('3', 'Nivel 3 (Subdepartamento)'),
        ('2', 'Nivel 2 (Departamento)'),
        ('1', 'Nivel 1 (Dirección)'),
        ('done', 'Aprobado')
    ], string="Nivel Pendiente", tracking=True, copy=False)

    can_approve = fields.Boolean(compute='_compute_can_approve', string="Puede Aprobar")

    pre_policy_id = fields.Many2one('account.move', string="Pre-Póliza Contable", readonly=True, copy=False)

    @api.depends('order_line.mark_up', 'order_line.product_packaging_id', 'order_line.product_qty')
    def _compute_markup_total(self):
        for order in self:
            total = 0.0
            for line in order.order_line:
                if line.is_markup_line:
                    continue  # ignorar línea de markup
                if line.product_packaging_id:
                    total += line.mark_up
                else:
                    total += line.mark_up * line.product_qty
            order.markup_total = total

    @api.depends('markup_total')
    def _compute_markup_total_iva(self):
        iva_rate = 0.16  # 16%
        for order in self:
            order.markup_total_iva = order.markup_total * iva_rate

    def _compute_admin_email(self):
        admin_group = self.env.ref('base.group_system')
        admin_users = admin_group.users

        for order in self:
            email_list = [admin.partner_id.email for admin in admin_users if admin.partner_id.email]
            order.admin_email = ', '.join(email_list)

    state = fields.Selection(selection_add=[
        ('to_approve', 'Por Aprobar'),
        ('approved', 'Aprobado'),
    ])


    requires_authorization = fields.Boolean(
        string="Requiere Autorización",
        compute="_compute_requires_authorization",
        store=True,
    )

    # datos de proveedor
    comercial_name = fields.Char(string='Nombre Comercial', related='partner_id.comercial_name')
    rfc = fields.Char(string='RFC', related='partner_id.rfc')
    account_number = fields.Char(string='Numero de cuenta')
    branch_account = fields.Many2one('res.company', string='Sucursal', domain=[('is_branch', '=', True)])
    clabe = fields.Char(string='Clabe')
    bank = fields.Char(string='Banco')
    email = fields.Char(string='Correo', related='partner_id.email')
    phone = fields.Char(string='Telefono', related='partner_id.phone')

    @api.depends('partner_id')
    def _compute_partner_information(self):
        for order in self:
            default_bank = order.partner_id.bank_ids.filtered(lambda b: b.is_default)
            if default_bank:
                order.clabe = default_bank.l10n_mx_edi_clabe
                order.bank = default_bank.bank_id.name
                order.account_number = default_bank.acc_number

    @api.depends('company_id')
    def _compute_requires_authorization(self):
        for order in self:
            order.requires_authorization = order.company_id.requires_purchase_authorization

    def action_see_invoice(self):
        if self.uuid:
            invoice = self.env['sat.xml.invoices'].sudo().search([('tfd_uuid', '=', self.uuid)], limit=1)

            return {
                'type': 'ir.actions.act_window',
                'name': 'factura',
                'res_model': 'sat.xml.invoices',
                'view_mode': 'form',
                'res_id': invoice.id,
                'target': 'new',
            }
        else:
            raise ValidationError('No se ah establecido ninguna factura valida')

    def action_request_approval(self):
        for order in self:
            _logger.info(
                '>>> action_request_approval: %s | state=%s | requires_auth=%s',
                order.name, order.state, order.requires_authorization
            )

            # ========== VALIDACIÓN DE MONTOS (nota vs factura) ==========
            if order.sale_note_total and float_compare(
                order.sale_note_total, order.amount_total, precision_digits=2
            ) != 0:
                raise UserError(_(
                    "Discrepancia de Montos\n\n"
                    "El total de la nota de venta (%.2f) no coincide con el "
                    "total de la orden de compra (%.2f).\n\n"
                    "Ajusta los montos antes de solicitar autorización."
                ) % (order.sale_note_total, order.amount_total))

            # ========== CREAR PRE-PÓLIZA (en borrador) ==========
            if not order.pre_policy_id:
                order.create_pre_policy()

            order.message_post(
                body=_(
                    'Solicitud de Autorización\n'
                    'Iniciada por: %s\n'
                    'Monto total: %.2f'
                ) % (self.env.user.name, order.amount_total)
            )

            if not order.requires_authorization:
                order.message_post(
                    body=_('Esta orden no requiere flujo de autorización. Auto-aprobada.')
                )
                order.write({'approval_level': 'done'})
                return

            # ========== PROVEEDOR DE PLANTA (sin autorización) ==========
            plant_suppliers = order.company_id.po_plant_supplier_ids
            if order.partner_id in plant_suppliers:
                order.write({'approval_level': 'done'})
                order.message_post(body=_(
                    'Proveedor de Planta\n\n'
                    'El proveedor %s está configurado como '
                    'proveedor de planta.\n'
                    'La orden se aprueba automáticamente sin pasar por '
                    'los niveles de autorización.\n\n'
                    'Siguiente paso: Haz clic en '
                    'Confirmar Orden.'
                ) % order.partner_id.name)
                return

            user_level = order._get_user_level(self.env.user)
            company = order.company_id

            # ========== VERIFICAR APROBACIÓN INMEDIATA ==========
            can_use_immediate = order.check_user_request_limits()
            limit = company.po_approval_amount_limit
            is_immediate = (
                can_use_immediate
                and limit > 0
                and order.amount_total < limit
            )

            # ========== DETERMINAR SIGUIENTE NIVEL ==========
            if is_immediate:
                # Solo necesita el nivel inmediato superior
                next_level = 'done'
                for l in ['4', '3', '2', '1']:
                    is_active = getattr(company, 'po_level_%s_active' % l, False)
                    if is_active and int(l) < user_level:
                        next_level = l
                        break

                if next_level == 'done':
                    # El usuario ya es del nivel más alto activo
                    order.write({'approval_level': 'done'})
                    order.message_post(
                        body=_(
                            'Orden Auto-Aprobada\n'
                            'El usuario tiene el nivel más alto activo. '
                            'La Pre-Póliza permanece en Borrador '
                            'hasta recibir los productos.'
                        )
                    )
                else:
                    next_level_label = dict(
                        order._fields['approval_level'].selection
                    ).get(next_level, next_level)

                    order.write({
                        'state': 'to_approve',
                        'approval_level': next_level,
                    })
                    order.message_post(
                        body=_(
                            'Aprobación Inmediata\n'
                            'Monto (%.2f) menor al límite de aprobación '
                            'inmediata (%.2f).\n'
                            'Solo requiere aprobación de: %s\n'
                            'La Pre-Póliza permanece en Borrador '
                            'hasta recibir los productos.'
                        ) % (order.amount_total, limit, next_level_label)
                    )
            else:
                # Debe pasar por TODOS los niveles activos
                next_level = 'done'
                for l in ['4', '3', '2', '1']:
                    is_active = getattr(company, 'po_level_%s_active' % l, False)
                    if is_active and int(l) < user_level:
                        next_level = l
                        break

                if next_level == 'done':
                    order.write({'approval_level': 'done'})
                    order.message_post(
                        body=_(
                            'Orden Auto-Aprobada\n'
                            'La Pre-Póliza permanece en Borrador '
                            'hasta recibir los productos.'
                        )
                    )
                else:
                    reason = ''
                    if not can_use_immediate and limit > 0 and order.amount_total < limit:
                        reason = (
                            'Se agotó el límite diario de aprobaciones '
                            'inmediatas. '
                        )
                    elif limit > 0 and order.amount_total >= limit:
                        reason = (
                            'Monto (%.2f) supera el límite de aprobación '
                            'inmediata (%.2f). '
                        ) % (order.amount_total, limit)

                    order.write({
                        'state': 'to_approve',
                        'approval_level': next_level,
                    })
                    order.message_post(
                        body=_(
                            'Escalamiento Completo\n'
                            '%s'
                            'Debe pasar por todos los niveles de aprobación.\n'
                            'La Pre-Póliza permanece en Borrador '
                            'hasta recibir los productos.'
                        ) % reason
                    )

            # Enviar correo de notificación si queda pendiente
            if order.state == 'to_approve':
                template = self.env.ref(
                    'contabilidad_kuale.mail_authorization_request',
                    raise_if_not_found=False
                )
                if template:
                    template.send_mail(order.id, force_send=True)



    


    def button_confirm(self):
        """
        Override de button_confirm para validar aprobaciones antes de confirmar.
        FLUJO:
        1. Valida que el usuario no sea solo guía en entrenamiento
        2. Valida aprobación (approval_level = 'done')
        3. Llama al super() para crear pickings y cambiar a 'purchase'
        4. Vincula picking con la orden
        """
        user = self.env.user
        is_entrenamiento = user.has_group('reclutamiento__kuale.group_guias_entrenamiento')
        can_confirm = (
            user.has_group('reclutamiento__kuale.group_guias_generales') or
            user.has_group('reclutamiento__kuale.group_guias_foraneos') or
            user.has_group('reclutamiento__kuale.group_dh_access') or
            user.has_group('base.group_system')
        )
        if is_entrenamiento and not can_confirm:
            raise UserError(_(
                'Los guías en entrenamiento no pueden confirmar órdenes de compra directamente.\n\n'
                'Acción requerida: usa el botón "Solicitar Autorización" para que un Guía General '
                'o DH autorice la orden.'
            ))

        for order in self:
            _logger.info(
                'BUTTON_CONFIRM: %s | state=%s | requires_auth=%s | approval=%s',
                order.name, order.state, order.requires_authorization, order.approval_level
            )

            # ========== 1. VALIDACIÓN DE APROBACIONES ==========
            if order.requires_authorization:
                if order.approval_level != 'done':
                    current_level_label = dict(
                        order._fields['approval_level'].selection
                    ).get(order.approval_level, 'Solicitud no iniciada')

                    raise UserError(_(
                        "Orden No Aprobada\n\n"
                        "No se puede confirmar la orden de compra porque "
                        "aún no ha sido aprobada completamente.\n\n"
                        "Nivel actual pendiente: %s\n\n"
                        "Acción requerida:\n"
                        "  • Si no has solicitado aprobación, haz clic en "
                        "'Solicitar Autorización'\n"
                        "  • Si ya la solicitaste, espera a que los niveles "
                        "superiores aprueben"
                    ) % current_level_label)

                _logger.info(
                    'Validación pasada: Orden %s aprobada (approval_level=done)',
                    order.name
                )

        # ========== 2. LLAMAR AL SUPER (Crea pickings, cambia state a 'purchase') ==========
        res = super(PurchaseOrder, self).button_confirm()

        # ========== 3. POST-CONFIRMACIÓN ==========
        for order in self:
            picking_count = len(order.picking_ids)
            _logger.info(
                'Post-confirmación: %s | state=%s | pickings=%s',
                order.name, order.state, picking_count
            )

            if picking_count > 0:
                order.message_post(body=_(
                    'Orden Confirmada\n\n'
                    'La orden ha sido confirmada.\n'
                    'Recepciones creadas: %s\n'
                    'Siguiente paso: Haz clic en '
                    '"Recibir Productos" para validar las recepciones.'
                ) % picking_count)

        return res


    def _check_all_pickings_done(self):
        """
        Verifica si todos los pickings están en estado 'done'.
        Si es así:
          - Cambia la orden a 'approved'
          - Valida la Pre-Póliza (pasa de borrador a póliza válida)

        Se llama automáticamente desde stock.picking.button_validate()
        """
        for order in self:
            if order.state != 'purchase' or not order.picking_ids:
                continue

            total_pickings = len(order.picking_ids)
            done_pickings = len([
                p for p in order.picking_ids if p.state == 'done'
            ])

            _logger.info(
                'Orden %s: %s/%s pickings completados',
                order.name, done_pickings, total_pickings
            )

            if not all(pick.state == 'done' for pick in order.picking_ids):
                _logger.info(
                    'Orden %s: aún tiene %s pickings pendientes',
                    order.name, total_pickings - done_pickings
                )
                continue

            # ========== TODOS LOS PRODUCTOS RECIBIDOS ==========
            order.write({'state': 'approved'})

            order.message_post(body=_(
                'Productos Recibidos Completamente\n\n'
                'Todos los productos han sido recibidos y validados.\n'
                'Pickings completados: %s/%s\n'
                'Estado actualizado: Aprobado\n\n'
                'Siguiente paso: Haz clic en '
                'Abrir Póliza Contable para registrar el pago '
                'y validar la póliza.'
            ) % (done_pickings, total_pickings))

            _logger.info(
                'Orden %s cambiada a approved', order.name
            )

    def action_create_invoice_from_picking(self):
        """
        Abre la póliza contable después de recibir los productos.
        Si la pre-póliza aún está en borrador, la valida.
        """
        for order in self:
            if not all(pick.state == 'done' for pick in order.picking_ids):
                raise UserError(_(
                    "Productos No Recibidos\n\n"
                    "No se puede abrir la póliza contable porque aún hay "
                    "recepciones pendientes.\n\n"
                    "Acción requerida: Valida todas las recepciones de "
                    "productos primero."
                ))

            if not order.pre_policy_id:
                raise UserError(_(
                    "No se encontró una Pre-Póliza asociada a esta orden."
                ))

            # Validar la Pre-Póliza si aún está en borrador
            if order.pre_policy_id.state == 'draft':
                order.pre_policy_id.action_post()
                order.message_post(body=_(
                    'Póliza Contable Validada\n\n'
                    'La Pre-Póliza ha sido validada y convertida en '
                    'Póliza Contable.\n'
                    'Póliza: %s\n'
                    'Monto Total: %.2f\n\n'
                    'Siguiente paso: Registra el pago desde el '
                    'módulo de Contabilidad.'
                ) % (order.pre_policy_id.name, order.amount_total))

            return {
                'type': 'ir.actions.act_window',
                'name': _('Póliza Contable'),
                'res_model': 'account.move',
                'view_mode': 'form',
                'res_id': order.pre_policy_id.id,
                'target': 'current',
            }


    
    # test
    @api.onchange('has_markup', 'factor', 'order_line.price_unit', 'order_line.mark_up', 'order.product_id',
                  'markup_total')
    def _onchange_markup_dynamic_line(self):
        print('onchange markup dynamic line')
        product_markup = self.env.ref('contabilidad_kuale.product_markup', raise_if_not_found=False)
        if not product_markup:
            raise UserError(_("No se encontró el producto de markup con ID XML 'contabilidad_kuale.product_markup'"))

        for order in self:
            # Eliminar cualquier línea que ya tenga ese producto de markup
            markup_lines = order.order_line.filtered(
                lambda l: l.product_id and l.product_id.id == product_markup.id
            )
            order.order_line -= markup_lines

            if not order.has_markup or order.factor <= 0:
                continue

            # Calcular el total del markup acumulado
            total_markup = sum(
                line.mark_up for line in order.order_line
                if not line.display_type and line.product_id.id != product_markup.id
            )

            if total_markup <= 0:
                continue

            # Crear la línea de markup dinámicamente
            markup_line = self.env['purchase.order.line'].new({
                'product_id': product_markup.id,
                'name': 'Gasto de markup',
                'product_qty': 1,
                'price_unit': total_markup,
                'taxes_id': product_markup.supplier_taxes_id.ids,
                'date_planned': fields.Datetime.now(),
                'is_markup_line': True,
            })
            order.order_line += markup_line

    def action_import_invoice_xml(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Importar XML de Factura',
            'res_model': 'purchase.order.import.xml',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_order_id': self.id,
            }
        }

    def _get_branch_receipt_type_and_dest(self, branch_company):
        warehouse = self.env['stock.warehouse']
        wh = warehouse.search([('company_id', '=', branch_company.id)], limit=1)
        if not wh:
            raise UserError(_("La sucursal %s no tiene almacén configurado.") % (branch_company.display_name,))
        if not wh.in_type_id:
            raise UserError(
                _("El almacén %s no tiene tipo de picking de Recepciones configurado.") % (wh.display_name,))
        if not wh.lot_stock_id:
            raise UserError(_("El almacén %s no tiene ubicación de stock configurada.") % (wh.display_name,))
        return wh.in_type_id, wh.lot_stock_id

    def _get_branch_receipt_type_and_locs(self, branch_company):
        Warehouse = self.env['stock.warehouse']
        wh = Warehouse.search([('company_id', '=', branch_company.id)], limit=1)
        if not wh:
            raise UserError(_("La sucursal %s no tiene almacén configurado.") % (branch_company.display_name,))
        if not wh.in_type_id:
            raise UserError(
                _("El almacén %s no tiene tipo de picking de Recepciones configurado.") % (wh.display_name,))
        if not wh.lot_stock_id:
            raise UserError(_("El almacén %s no tiene ubicación de stock configurada.") % (wh.display_name,))

        in_type = wh.in_type_id
        dest_loc = wh.lot_stock_id

        # Fallback para ORIGEN: default del picking, si no el location de Proveedores
        src_loc = in_type.default_location_src_id \
                  or self.env.ref('stock.stock_location_suppliers', raise_if_not_found=False) \
                  or self.env['stock.location'].search(
            [('usage', '=', 'supplier'), ('company_id', 'in', [branch_company.id, False])],
            limit=1
        )

        if not src_loc:
            raise UserError(_(
                "No se encontró ubicación origen para recepciones en %s. "
                "Configura la ubicación de proveedores o el 'Location Source' del picking de Recepciones."
            ) % (branch_company.display_name,))

        return in_type, src_loc, dest_loc

    def _create_branch_picking(self):
        self.ensure_one()
        Move = self.env['stock.move']
        Picking = self.env['stock.picking']
        Group = self.env['procurement.group']

        group = Group.create({
            'name': self.name,
            'move_type': 'one',
            'partner_id': self.partner_id.id,
        })

        pickings_by_branch = {}

        def _get_or_create_picking_for_branch(branch_company, scheduled_date):
            picking = pickings_by_branch.get(branch_company.id)
            if picking:
                return picking
            in_type, src_loc, dest_loc = self._get_branch_receipt_type_and_locs(branch_company)
            picking = Picking.create({
                'picking_type_id': in_type.id,
                'partner_id': self.partner_id.id,
                'origin': self.name,
                'company_id': branch_company.id,
                'location_id': src_loc.id,  # <-- AHORA SIEMPRE SE PONE ORIGEN
                'location_dest_id': dest_loc.id,  # destino: stock de la sucursal
                'scheduled_date': scheduled_date or fields.Datetime.now(),
                'group_id': group.id,
            })
            pickings_by_branch[branch_company.id] = picking
            return picking

        for line in self.order_line:
            if line.display_type or not line.product_id or line.product_id.type not in ('product', 'consu'):
                continue
            if line.branch_split_ids:
                for split in line.branch_split_ids:
                    if float_is_zero(split.qty, precision_rounding=line.product_uom.rounding):
                        continue
                    picking = _get_or_create_picking_for_branch(split.branch_id, line.date_planned)
                    Move.create({
                        'name': line.name or line.product_id.display_name,
                        'product_id': line.product_id.id,
                        'product_uom_qty': split.qty,
                        'product_uom': line.product_uom.id,
                        'picking_id': picking.id,
                        'partner_id': self.partner_id.id,
                        'purchase_line_id': line.id,
                        'company_id': split.branch_id.id,
                        'location_id': picking.location_id.id,
                        'location_dest_id': picking.location_dest_id.id,
                        'date': line.date_planned or fields.Datetime.now(),
                        'date_deadline': line.date_planned or fields.Datetime.now(),
                    })
            else:
                target_company = self.branch_id or self.company_id
                picking = _get_or_create_picking_for_branch(target_company, line.date_planned)
                Move.create({
                    'name': line.name or line.product_id.display_name,
                    'product_id': line.product_id.id,
                    'product_uom_qty': line.product_qty,
                    'product_uom': line.product_uom.id,
                    'picking_id': picking.id,
                    'partner_id': self.partner_id.id,
                    'purchase_line_id': line.id,
                    'company_id': target_company.id,
                    'location_id': picking.location_id.id,
                    'location_dest_id': picking.location_dest_id.id,
                    'date': line.date_planned or fields.Datetime.now(),
                    'date_deadline': line.date_planned or fields.Datetime.now(),
                })
        pickings = self.env['stock.picking'].browse([p.id for p in pickings_by_branch.values()])
        pickings.action_confirm()

        return pickings

    def _create_picking(self):
        """
        Override de _create_picking.
        La validación de la pre-póliza se maneja en _check_all_pickings_done()
        que se llama desde stock.picking.button_validate().
        """
        return super(PurchaseOrder, self)._create_picking()

    

    def check_user_request_limits(self):
        """
        Verifica si el usuario puede usar aprobación inmediata.
        Retorna True si puede, False si ha agotado su cuota diaria.
        NO bloquea la solicitud, solo determina si debe escalar.
        """
        self.ensure_one()
        order = self
        user = self.env.user
        company = order.company_id
        limit_daily = company.po_user_daily_limit
        approval_amount_limit = company.po_approval_amount_limit

        # Si no hay límite diario configurado (0), siempre puede usar inmediata
        if limit_daily <= 0:
            return True

        # Si no hay límite de monto configurado, no aplica aprobación inmediata
        if approval_amount_limit <= 0:
            return True

        now = fields.Datetime.now()
        today_start = datetime.combine(now.date(), time.min)
        today_end = datetime.combine(now.date(), time.max)

        # Contar solicitudes de aprobación inmediata del día
        # (órdenes con monto menor al límite de aprobación inmediata)
        states_to_check = ['to_approve', 'approved', 'purchase', 'done']

        daily_immediate_orders = self.search([
            ('user_id', '=', user.id),
            ('state', 'in', states_to_check),
            ('date_order', '>=', today_start),
            ('date_order', '<=', today_end),
            ('id', '!=', order.id),
        ])

        # Filtrar solo las que fueron aprobación inmediata (monto < límite)
        daily_immediate_count = len([
            o for o in daily_immediate_orders
            if o.amount_total < approval_amount_limit
        ])

        if daily_immediate_count >= limit_daily:
            _logger.info(
                'Usuario %s agotó su límite diario de aprobaciones '
                'inmediatas (%s/%s). La solicitud escalará por '
                'todos los niveles.',
                user.name, daily_immediate_count, limit_daily
            )
            return False

        return True
                

    def _get_user_level(self, user):
        """
        Retorna el nivel más alto (el número menor) al que pertenece el usuario.
        Si no está en ninguna lista, retorna 5 (Usuario sin poder de aprobación).
        """
        company = self.company_id or self.env.company
        if company.po_level_1_active and user in company.po_level_1_users: return 1
        if company.po_level_2_active and user in company.po_level_2_users: return 2
        if company.po_level_3_active and user in company.po_level_3_users: return 3
        if company.po_level_4_active and user in company.po_level_4_users: return 4
        return 5

    @api.depends('approval_level', 'state')
    def _compute_can_approve(self):
        """
        Muestra el botón de aprobar si el usuario tiene el nivel requerido o SUPERIOR.
        """
        for order in self:
            can_approve = False
            
            # ✅ AGREGAR LOG TEMPORAL
            _logger.info(f"""
            >>> DEBUG _compute_can_approve para OC {order.name}:
                - state: {order.state}
                - approval_level: {order.approval_level}
                - requires_authorization: {order.requires_authorization}
            """)
            
            if order.state == 'to_approve' and order.approval_level and order.approval_level != 'done':
                user_level = order._get_user_level(self.env.user)
                
                # ✅ MÁS LOGS
                _logger.info(f"""
                    - user_level: {user_level}
                    - Puede aprobar: {1 <= user_level <= 4 and user_level <= int(order.approval_level)}
                """)
                
                if 1 <= user_level <= 4 and user_level <= int(order.approval_level):
                    can_approve = True
            
            order.can_approve = can_approve
            _logger.info(f"    - RESULTADO: can_approve = {can_approve}")



    
    def action_approve(self):
        for order in self:
            if order.state != 'to_approve':
                raise UserError(_(
                    'Solo se pueden aprobar órdenes en estado "Por Aprobar".'
                ))
            if not order.can_approve:
                raise UserError(_(
                    'No tienes permisos para aprobar en este nivel.'
                ))

            username = self.env.user.name
            current_level_label = dict(
                order._fields['approval_level'].selection
            ).get(order.approval_level, order.approval_level)

            company = order.company_id
            current_idx = int(order.approval_level)

            # Determinar siguiente nivel
            next_level = 'done'
            for l in range(current_idx - 1, 0, -1):
                if getattr(company, 'po_level_%s_active' % l, False):
                    next_level = str(l)
                    break

            # Verificar si califica para saltar niveles por monto
            skipped_by_amount = False
            limit = company.po_approval_amount_limit
            if limit > 0 and order.amount_total < limit:
                next_level = 'done'
                skipped_by_amount = True

            if next_level == 'done':
                # ========== APROBACIÓN FINAL ==========
                # NO cambiar state a 'draft'. Se mantiene en 'to_approve'
                # para que el usuario haga click en "Confirmar Orden".
                order.write({'approval_level': 'done'})

                msg = _(
                    'Aprobación Final\n\n'
                    'Aprobado por %s (%s).'
                ) % (username, current_level_label)

                if skipped_by_amount:
                    msg += _(
                        '\nNiveles superiores omitidos (monto %.2f '
                        'menor al límite %.2f).'
                    ) % (order.amount_total, limit)

                msg += _(
                    '\n\nSiguiente paso: Haz clic en '
                    'Confirmar Orden para generar las recepciones.\n'
                    'La Pre-Póliza se validará automáticamente al '
                    'recibir todos los productos.'
                )
                order.message_post(body=msg)

            else:
                # ========== ESCALAR AL SIGUIENTE NIVEL ==========
                next_level_label = dict(
                    order._fields['approval_level'].selection
                ).get(next_level, next_level)

                order.write({'approval_level': next_level})
                order.message_post(body=_(
                    'Aprobado por %s (%s)\n'
                    'Escalando a: %s\n'
                    'La Pre-Póliza permanece en Borrador hasta '
                    'recibir los productos.'
                ) % (username, current_level_label, next_level_label))

                template = self.env.ref(
                    'contabilidad_kuale.mail_authorization_request',
                    raise_if_not_found=False
                )
                if template:
                    template.send_mail(order.id, force_send=True)



    def create_pre_policy(self):
        for order in self:
            if order.pre_policy_id:
                _logger.info('[PRE-POLIZA] Ya existe para %s: %s', order.name, order.pre_policy_id.name)
                continue

            _logger.info('[PRE-POLIZA] Iniciando creacion para %s | Total: %s', order.name, order.amount_total)

            journal = self.env['account.journal'].search([
                ('type', '=', 'purchase'),
                ('company_id', '=', order.company_id.id),
            ], limit=1)

            if not journal:
                raise UserError(_(
                    'No se encontro un diario de tipo Compra para "%s".\n'
                    'Ve a Contabilidad > Configuracion > Diarios.'
                ) % order.company_id.name)

            _logger.info('[PRE-POLIZA] Usando diario: %s', journal.name)

            move_lines = []

            for line in order.order_line:
                if line.display_type:
                    continue
                account = (
                    line.product_id.property_account_expense_id
                    or line.product_id.categ_id.property_account_expense_categ_id
                )
                if not account:
                    raise UserError(_(
                        'El producto "%s" no tiene cuenta de gastos configurada.\n'
                        'Configurala en el producto o en su categoria.'
                    ) % line.product_id.name)

                _logger.info('[PRE-POLIZA] Debito gasto: %s | %s', account.name, line.price_subtotal)
                move_lines.append((0, 0, {
                    'name': '%s - %s' % (order.name, line.name or line.product_id.display_name),
                    'account_id': account.id,
                    'partner_id': order.partner_id.id,
                    'product_id': line.product_id.id,
                    'debit': line.price_subtotal,
                    'credit': 0.0,
                    'analytic_distribution': line.analytic_distribution or {},
                }))

            if order.amount_tax > 0:
                tax_account = False
                lines_with_tax = order.order_line.filtered(lambda l: l.taxes_id)
                if lines_with_tax:
                    first_tax = lines_with_tax[0].taxes_id[0]
                    repartition = first_tax.invoice_repartition_line_ids.filtered(
                        lambda r: r.repartition_type == 'tax' and r.account_id
                    )
                    if repartition:
                        tax_account = repartition[0].account_id
                if not tax_account:
                    tax_account = journal.default_account_id
                if not tax_account:
                    raise UserError(_(
                        'No se pudo determinar la cuenta de IVA por Acreditar.\n'
                        'Verifica los impuestos o el diario de compras.'
                    ))
                _logger.info('[PRE-POLIZA] Debito IVA: %s | %s', tax_account.name, order.amount_tax)
                move_lines.append((0, 0, {
                    'name': '%s - IVA por Acreditar' % order.name,
                    'account_id': tax_account.id,
                    'partner_id': order.partner_id.id,
                    'debit': order.amount_tax,
                    'credit': 0.0,
                }))

            payable_account = order.partner_id.property_account_payable_id
            if not payable_account:
                raise UserError(_(
                    'El proveedor "%s" no tiene cuenta por pagar configurada.'
                ) % order.partner_id.name)

            _logger.info('[PRE-POLIZA] Credito proveedor: %s | %s', payable_account.name, order.amount_total)
            move_lines.append((0, 0, {
                'name': '%s - Provision de Compra' % order.name,
                'account_id': payable_account.id,
                'partner_id': order.partner_id.id,
                'debit': 0.0,
                'credit': order.amount_total,
            }))

            # ---- Buscar datos CFDI para pre-rellenar la póliza ----
            sat_invoice = False
            cfdi_payment_method = False
            cfdi_payment_type = False
            cfdi_coin_type = False
            cfdi_invoice_date = False

            if order.uuid:
                sat_invoice = self.env['sat.xml.invoices'].sudo().search(
                    [('tfd_uuid', '=', order.uuid)], limit=1
                )

            if sat_invoice:
                cfdi_invoice_date = sat_invoice.factura_fecha

            # Buscar método de pago en catálogo
            metodo_code = order.cfdi_metodo_pago or (sat_invoice.factura_metodo_pago if sat_invoice else False)
            if metodo_code:
                cfdi_payment_method = self.env['cfdi.clavemetododepago'].sudo().search(
                    [('Clave_metodo_de_pago', '=', metodo_code)], limit=1
                )

            # Buscar forma de pago en catálogo
            forma_code = order.cfdi_forma_pago or (sat_invoice.factura_forma_pago if sat_invoice else False)
            if forma_code:
                cfdi_payment_type = self.env['cfdi.claveformadepago'].sudo().search(
                    [('Clave_forma_de_pago', '=', forma_code)], limit=1
                )

            # Buscar moneda en catálogo
            moneda_code = order.cfdi_moneda or (sat_invoice.factura_moneda if sat_invoice else False)
            if moneda_code:
                cfdi_coin_type = self.env['cfdi.clavemoneda'].sudo().search(
                    [('Clave_moneda', '=', moneda_code)], limit=1
                )

            move_vals = {
                'ref': 'Pre-Poliza %s' % order.name,
                'date': fields.Date.context_today(self),
                'journal_id': journal.id,
                'move_type': 'entry',
                'company_id': order.company_id.id,
                'partner_id': order.partner_id.id,
                'branch_id': order.company_id.id,
                'line_ids': move_lines,
            }

            # Pre-rellenar campos de facturación desde CFDI
            if sat_invoice:
                move_vals['invoice'] = sat_invoice.id
            if cfdi_payment_method:
                move_vals['payment_method'] = cfdi_payment_method.id
            if cfdi_payment_type:
                move_vals['payment_type'] = cfdi_payment_type.id
            if cfdi_coin_type:
                move_vals['coin_type'] = cfdi_coin_type.id
            if cfdi_invoice_date:
                move_vals['invoice_date'] = cfdi_invoice_date

            try:
                move = self.env['account.move'].create(move_vals)
                order.pre_policy_id = move.id
                _logger.info('[PRE-POLIZA] Creada: %s para %s', move.name, order.name)
                order.message_post(
                    body=_(
                        'Pre-Póliza Generada en Borrador\n'
                        'Pre-Póliza: %s\n'
                        'Monto Total: %.2f\n'
                        'Estado: Borrador\n'
                        'Se validará automáticamente al completarse la aprobación.'
                    ) % (move.name, order.amount_total)
                )
            except Exception as e:
                _logger.error('[PRE-POLIZA] Error creando para %s: %s', order.name, e, exc_info=True)
                raise UserError(_('Error al crear la Pre-Poliza: %s') % str(e))






    def action_view_pre_policy(self):
        """Abre la Pre-Póliza asociada a esta orden."""
        self.ensure_one()
        if not self.pre_policy_id:
            raise UserError(_(
                "Esta orden no tiene una Pre-Póliza asociada.\n\n"
                "La Pre-Póliza se genera automáticamente al hacer clic en "
                "'Solicitar Autorización'."
            ))
        return {
            'name': _('Pre-Póliza Contable'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.pre_policy_id.id,
            'target': 'current',
        }

        
    def action_open_accounting_policy(self):
        """
        Abre la Póliza Contable para registrar el pago.
        Si la pre-póliza está en borrador, la valida automáticamente.
        """
        self.ensure_one()
        if not self.pre_policy_id:
            raise UserError(_(
                "Pre-Póliza No Encontrada\n\n"
                "No se encontró una Pre-Póliza asociada a esta orden."
            ))

        # Validar la Pre-Póliza si está en borrador
        if self.pre_policy_id.state == 'draft':
            self.pre_policy_id.action_post()
            self.message_post(body=_(
                '<b>📄 Póliza Contable Validada</b><br/><br/>'
                'La Pre-Póliza ha sido validada automáticamente.<br/>'
                '• <b>Póliza:</b> %s<br/>'
                '• <b>Monto:</b> %.2f<br/><br/>'
                'Ahora puedes registrar el pago desde la póliza.'
            ) % (self.pre_policy_id.name, self.amount_total))

        return {
            'type': 'ir.actions.act_window',
            'name': _('Póliza Contable'),
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.pre_policy_id.id,
            'target': 'current',
        }



class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'
    price_per_pack = fields.Float(string="Precio por embalaje", help="Precio total del embalaje seleccionado.",
                                  digits=(16, 6))
    price_unit = fields.Float(string='Unit Price', digits=(16, 6))
    # markup

    mark_up = fields.Float(string="Markup", digits=(16, 6))
    price_per_pack_markup = fields.Float(string='Precio embalaje con markup', digits=(16, 6),
                                         compute='_compute_markup', store=True)
    unit_price_markup = fields.Float(string='Precio unitario con markup', digits=(16, 6),
                                     compute='_compute_markup', store=True)
    # test
    is_markup_line = fields.Boolean(string="Es línea de markup", default=False)

    # gastos

    expense_center = fields.Selection([
        ('sales', 'Gastos de venta y distribucion'),
        ('admin', 'Gastos de administracion'),
        ('general', 'Gastos generales')
    ], string='Centro de Costos')

    def _prepare_account_move_line(self, move=False):
        res = super()._prepare_account_move_line(move=move)
        company = (self.company_id or self.order_id.company_id)
        if self.expense_center and self.product_id:
            acc = self.product_id.product_tmpl_id._get_expense_account_by_center(self.expense_center, company)
            if acc:
                res['account_id'] = acc.id
        return res

    xml_description = fields.Char(string='Descripcion XML')

    branch_split_ids = fields.One2many(
        'purchase.line.branch.split',
        'order_line_id',
        string='Distribución por Sucursal'
    )

    @api.constrains('branch_split_ids', 'product_qty', 'product_uom')
    def _check_branch_split_sum(self):
        for line in self:
            if not line.branch_split_ids:
                continue
            total = sum(line.branch_split_ids.mapped('qty'))
            # Respetar el redondeo de la UoM
            precision = line.product_uom.rounding or 0.0001
            if float_compare(total, line.product_qty, precision_rounding=precision) != 0:
                raise ValidationError(_(
                    "La suma de cantidades por sucursal (%.4f) debe igualar la cantidad de la línea (%.4f)."
                ) % (total, line.product_qty))

    @api.onchange('price_per_pack', 'product_packaging_id')
    def _onchange_price_per_pack(self):
        """Recalcula el precio unitario cuando cambia el precio por embalaje o el tipo de embalaje."""
        for line in self:
            if line.product_packaging_id and line.product_packaging_id.qty > 0:
                # Calcular el precio unitario basado en el precio por embalaje
                line.price_unit = line.price_per_pack / line.product_packaging_id.qty


    @api.onchange('product_id', 'order_id.has_markup', 'order_id.factor', 'product_packaging_id',
                  'unit_price_no_markup', 'price_per_pack_no_markup', 'product_qty')
    @api.depends('order_id.has_markup', 'order_id.factor', 'price_unit', 'price_per_pack', 'product_packaging_id')
    def _compute_markup(self):
        for line in self:
            if line.is_markup_line:
                line.mark_up = 0
                return
            factor = line.order_id.factor if line.order_id.has_markup else 0.0

            # Si hay embalaje, se calcula el markup sobre el precio por embalaje
            if line.product_packaging_id and line.product_packaging_id.qty > 0 and line.price_per_pack:
                line.mark_up = line.price_per_pack * factor
                line.price_per_pack_markup = line.price_per_pack + line.mark_up
                line.unit_price_markup = line.price_per_pack_markup / line.product_packaging_id.qty
            else:
                line.mark_up = line.price_unit * factor
                line.unit_price_markup = line.price_unit + line.mark_up
                line.price_per_pack_markup = 0.0  # No aplica embalaje

    @api.onchange('product_id','order_id.partner_id')
    def onchange_product_id(self):
        if self.is_markup_line:
            return

        super().onchange_product_id()
        if not self.product_id:
            return

        partner = self.order_id.partner_id
        packaging = False

        # Buscar supplierinfo de este proveedor para este producto
        supplierinfo = self.env['product.supplierinfo'].sudo().search([
            ('partner_id', '=', partner.id),
            ('product_tmpl_id', '=', self.product_id.product_tmpl_id.id)
        ], limit=1)

        # Si tiene embalaje asignado → usarlo
        if supplierinfo and supplierinfo.default_packaging_id:
            packaging = supplierinfo.default_packaging_id
        else:
            # fallback: primer packaging del producto
            packaging = self.product_id.packaging_ids[:1]

        if packaging:
            self.product_packaging_id = packaging.id
            self.product_packaging_qty = 1
        else:
            self.product_packaging_id = False
            self.product_qty = 1

        # actualizar markup si aplica
        if self.order_id.has_markup:
            self.order_id._onchange_markup_dynamic_line()

    @api.onchange('mark_up')
    def _onchange_mark_up(self):
        if self.is_markup_line:
            return
        if self.order_id.has_markup:
            print('xdd2')
            self.order_id._onchange_markup_dynamic_line()


class PurchaseOrderDiot(models.Model):
    _name = 'purchase.order.diot'
    _description = 'Purchase Order Diot'

    order_id = fields.Many2one('purchase.order', string='Orden de Compra', ondelete='cascade')
    folio = fields.Char(string='Folio', required=True)
    code = fields.Char(string='Codigo', required=True)
    partner_id = fields.Many2one('res.partner', string='Proveedor', required=True, related='order_id.partner_id')
    taxes_ids = fields.Many2many('account.tax', string='Impuestos')
    amount = fields.Float(string='Importe base')
    factor_type = fields.Selection([
        ('Tasa', 'Tasa'),
        ('Cuota', 'Cuota'),
        ('Exento', 'Exento'),
    ], string='Tipo factor')
    rate = fields.Float(string='Tasa o cuota')
    tax_amount = fields.Float(string='Importe impuesto')
    deductible = fields.Float(string='% Deducible')

    @api.onchange('amount', 'rate')
    def _compute_tax_amount(self):
        for rec in self:
            rec.tax_amount = (rec.amount * rec.rate / 100) if rec.rate else 0.0


class PurchaseOrderFiscal(models.Model):
    _name = 'purchase.order.fiscal'
    _description = 'Purchase Order Fiscal'

    order_id = fields.Many2one('purchase.order', string='Orden de Compra', ondelete='cascade')
    currency_id = fields.Many2one('res.currency', string='Divisa',
                                  required=True, readonly=True,
                                  default=lambda
                                      self: self.env.company.currency_id.id)
    account = fields.Many2one('account.account', string='Cuenta Orden')
    deductible_percentage = fields.Float(string='% Deducible')
    deductible_amount = fields.Float(string='Monto deducible')
    amount = fields.Float(string='Monto no deducible')
    amount_art = fields.Float(string='Monto no deducible Art.')
    subtotal = fields.Monetary(string='Subtotal', related='order_id.amount_untaxed')


class PurchaseOrderImportXML(models.TransientModel):
    _name = 'purchase.order.import.xml'
    _description = 'Importar XML a orden de compra'

    file = fields.Binary(string='Archivo XML', required=True)
    filename = fields.Char(string='Nombre del archivo')

    def _upload_xml(self):
        if not self.filename.endswith(".xml") and not self.filename.endswith(".zip"):
            self.filename = self.filename + '.xml'

        self.env['sat.uploads'].with_context(skip_oc_creation=True).create({
            'file': self.file,
            'name': self.filename,
            'file_name': self.filename,
        })

    def action_process_xml(self):
        """
        Procesa un XML de factura y crea una orden de compra
        """
        missing_count = 0
        msg_parts = []
        
        # 1. PARSEAR XML
        resultados = self._get_values_xml()
        partner_rfc = resultados.get('emisor_rfc', '').upper()
        partner_name = resultados.get('emisor_name', 'Proveedor sin nombre')
        company_rfc = resultados.get('receptor_rfc', '').upper()
        uuid = resultados.get('uuid')
        folio = resultados.get('folio')
        fecha = datetime.fromisoformat(resultados.get('fecha').replace('T', ' '))
        productos = resultados.get('productos', [])
        
        _logger.info(
            f">>> XML parseado: {resultados}"
        )
        _logger.info(
            f">>> Factura UUID={uuid}, Folio={folio}, "
            f"RFC Emisor={partner_rfc}, RFC Receptor={company_rfc}, Productos={len(productos)}"
        )
        
        # 2. BUSCAR/VALIDAR EMPRESA
        company = self.env['res.company'].sudo().search([
            ('rfc', '=', company_rfc),
            ('is_branch', '=', False)
        ], limit=1)
        
        if not company:
            raise ValidationError(_(f"No se encontró ninguna empresa asociada al RFC: {company_rfc}"))
        
        if company.id != self.env.company.id and company.id != self.env.company.parent_id.id:
            raise UserError(_(
                f"El XML pertenece a otra empresa, actualmente no tienes acceso a '{company.name}'.\n"
                f"Cambia la empresa activa para continuar."
            ))
        
        # 3. VALIDAR CUENTAS CONTABLES (CRÍTICO)
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
        
        # 4. BUSCAR O CREAR PROVEEDOR
        partner = self.env['res.partner'].sudo().search([('rfc', '=', partner_rfc)], limit=1)
        
        if not partner:
            _logger.info(f">>> No se encontró partner, creando nuevo...")
            
            try:
                # Obtener cuentas base VALIDADAS
                base_payable = company.account_payable
                base_receivable = company.account_receivable
                
                # Calcular códigos de subcuentas
                last_child_payable = self.env['account.account'].sudo().search([
                    ('code', 'like', f"{base_payable.code}.%"),
                    ('company_id', '=', company.id)
                ], order="code desc", limit=1)
                
                if last_child_payable:
                    last_seq = int(last_child_payable.code.split('.')[-1])
                    payable_code = f"{base_payable.code}.{last_seq + 1}"
                else:
                    payable_code = f"{base_payable.code}.1"
                
                last_child_receivable = self.env['account.account'].sudo().search([
                    ('code', 'like', f"{base_receivable.code}.%"),
                    ('company_id', '=', company.id)
                ], order="code desc", limit=1)
                
                if last_child_receivable:
                    last_seq = int(last_child_receivable.code.split('.')[-1])
                    receivable_code = f"{base_receivable.code}.{last_seq + 1}"
                else:
                    receivable_code = f"{base_receivable.code}.1"
                
                _logger.info(f">>> Creando cuentas: Payable={payable_code}, Receivable={receivable_code}")
                
                # Crear cuenta por pagar
                partner_pay_acc = self.env['account.account'].sudo().create({
                    'name': partner_name,
                    'code': payable_code,
                    'company_id': company.id,
                    'account_type': 'liability_payable',
                    'sat_nivel': getattr(base_payable, 'sat_nivel', None),
                    'naturaleza': getattr(base_payable, 'naturaleza', None),
                })
                
                # Crear cuenta por cobrar
                partner_rec_acc = self.env['account.account'].sudo().create({
                    'name': partner_name,
                    'code': receivable_code,
                    'company_id': company.id,
                    'account_type': 'asset_receivable',
                    'sat_nivel': getattr(base_receivable, 'sat_nivel', None),
                    'naturaleza': getattr(base_receivable, 'naturaleza', None),
                })
                
                # Buscar régimen fiscal
                code = self.env['cfdi.claveregimenfiscal'].sudo().search(
                    [('Clave_regimenFiscal', '=', resultados.get('emisor_rf'))], limit=1
                )
                if not code:
                    code = self.env['cfdi.claveregimenfiscal'].sudo().search(
                        [('Clave_regimenFiscal', '=', '601')], limit=1
                    )
                
                # Crear partner
                partner = self.env['res.partner'].sudo().create({
                    'name': partner_name,
                    'rfc': partner_rfc,
                    'tax_regime': code.id if code else False,
                    'property_account_payable_id': partner_pay_acc.id,
                    'property_account_receivable_id': partner_rec_acc.id,
                    'supplier_rank': 1,
                })
                
                _logger.info(f'Partner creado: {partner.name} (ID: {partner.id})')
                
            except Exception as e:
                _logger.error(f"Error creando partner: {str(e)}", exc_info=True)
                raise UserError(_(f"Error al crear el proveedor: {str(e)}"))
        
        # 5. PROCESAR PRODUCTOS
        order_line = []
        
        for producto in productos:
            _logger.info(f">>> Procesando producto: {producto}")
            
            product_code = producto.get('codigo')
            quantity = producto.get('cantidad', 0)
            price_unit = producto.get('valor_unitario', 0)
            description = producto.get('descripcion', '')
            discount = producto.get('descuento', 0)
            
            # Buscar supplierinfo
            supplier_info = None
            
            if product_code:
                supplier_info = self.env['product.supplierinfo'].sudo().search([
                    ('product_code', '=', product_code),
                    ('partner_id', '=', partner.id)
                ], limit=1)
            
            if not supplier_info:
                supplier_info = self.env['product.supplierinfo'].sudo().search([
                    ('product_name', 'ilike', description),
                    ('partner_id', '=', partner.id)
                ], limit=1)
            
            if not supplier_info:
                # Búsqueda fuzzy
                all_supplier_info = self.env['product.supplierinfo'].sudo().search([
                    ('partner_id', '=', partner.id)
                ])
                supplier_info = all_supplier_info.filtered(
                    lambda s: isinstance(s.product_name, str) and s.product_name.lower() in description.lower()
                )[:1]
            
            if not supplier_info:
                _logger.warning(f">>> Producto sin asociación, creando sumup...")
                missing_count += 1
                
                # Crear sumup
                sumup = self.env['product.supplierinfo.sumup'].sudo().search([
                    ('partner_id', '=', partner.id),
                    '|',
                    ('product_code', '=', product_code),
                    ('name', '=', description)
                ], limit=1)
                
                if not sumup:
                    self.env['product.supplierinfo.sumup'].sudo().create({
                        'partner_id': partner.id,
                        'name': description,
                        'product_code': product_code,
                        'price': price_unit,
                    })
                    _logger.info(f">>> Producto agregado a sumup: {product_code or description}")
                
                continue
            
            # Obtener producto
            product = supplier_info.product_tmpl_id.product_variant_id
            
            # Buscar embalaje
            packaging = self.env['product.packaging'].sudo().search([
                ('product_id', '=', product.id),
                ('partner_id', '=', partner.id)
            ], order='sequence', limit=1)
            
            # Calcular descuento porcentual
            discount_percent = 0
            if discount and price_unit and quantity:
                discount_percent = (discount / (price_unit * quantity)) * 100
            
            # Crear línea
            line_vals = {
                'product_id': product.id,
                'price_unit': price_unit,
                'taxes_id': [(6, 0, product.supplier_taxes_id.ids)],
                'discount': discount_percent if discount and quantity and price_unit else 0,
            }
            
            if packaging:
                line_vals.update({
                    'product_packaging_qty': quantity,
                    'price_per_pack': price_unit
                })
            else:
                line_vals.update({'product_qty': quantity})
            
            order_line.append((0, 0, line_vals))
        
        # 6. NOTIFICACIÓN DE PRODUCTOS FALTANTES
        if missing_count > 0:
            msg_parts.append(
                f"Hay **{missing_count}** concepto(s) sin asociación de producto para el proveedor **{partner_name}**."
            )
        
        # 7. CREAR ORDEN DE COMPRA
        if not order_line:
            _logger.warning(f">>> No se crearon líneas de orden de compra para UUID: {uuid}")
            
            if msg_parts:
                detail = "\n\n".join(msg_parts)
                detail += f"\n\n**UUID:** {uuid} — **Folio:** {folio}"
                detail += "\n\n*La orden de compra no se creó por falta de productos asociados.*"
                self.sudo()._notify_error_in_upload(detail)
            
            return False
        
        purchase_order = self.env['purchase.order'].sudo().create({
            'partner_id': partner.id,
            'date_order': fecha,
            'invoice_date': fecha,
            'order_line': order_line,
            'uuid': uuid,
            'invoice_folio': folio,
            'cfdi_metodo_pago': resultados.get('metodo_pago'),
            'cfdi_forma_pago': resultados.get('forma_pago'),
            'cfdi_moneda': resultados.get('moneda'),
        })
        
        _logger.info(f"Orden de compra creada: {purchase_order.name}")
        
        # 8. POST-PROCESAMIENTO
        for line in purchase_order.order_line:
            line.sudo()._compute_product_qty()
            line.sudo()._compute_product_uom_qty()
            line.sudo()._compute_amount()
            line.sudo()._onchange_price_per_pack()
            line.sudo()._compute_markup()
        
        # 9. NOTIFICAR ERRORES SI EXISTEN
        if msg_parts:
            detail = "\n\n".join(msg_parts)
            detail += f"\n\n**Orden de compra creada:** {purchase_order.name}"
            self.sudo()._notify_error_in_upload(detail)
        
        return purchase_order



    def _get_values_xml(self):
        xml_content = base64.b64decode(self.file)
        try:
            xml_tree = etree.fromstring(xml_content)
        except ValueError:
            xml_text = xml_content.decode('utf-8', errors='ignore')
            xml_text = re.sub(r'<\?xml.*encoding=.*\?>', '', xml_text)
            xml_tree = etree.fromstring(xml_text.encode('utf-8'))

        print('xml tree: ', xml_tree)
        ns = {'cfdi': 'http://www.sat.gob.mx/cfd/4'}

        emisor_rfc = xml_tree.xpath('//cfdi:Emisor/@Rfc', namespaces=ns)[0]
        emisor_name = xml_tree.xpath('//cfdi:Emisor/@Nombre', namespaces=ns)[0]
        emisor_rf = xml_tree.xpath('//cfdi:Emisor/@RegimenFiscal', namespaces=ns)[0]
        receptor_rfc = xml_tree.xpath('//cfdi:Receptor/@Rfc', namespaces=ns)[0]
        folio = xml_tree.xpath('//cfdi:Comprobante/@Folio', namespaces=ns)[0]
        fecha = xml_tree.xpath('//cfdi:Comprobante/@Fecha', namespaces=ns)[0]
        conceptos = xml_tree.xpath('//cfdi:Concepto', namespaces=ns)
        namespaces = {
            'cfdi': 'http://www.sat.gob.mx/cfd/4',
            'tfd': 'http://www.sat.gob.mx/TimbreFiscalDigital',
        }
        uuid = xml_tree.xpath('//cfdi:Complemento//tfd:TimbreFiscalDigital/@UUID', namespaces=namespaces)

        uuid = uuid[0] if uuid else None
        if uuid:
            duplicate = self.env['purchase.order'].sudo().search([('uuid', '=', uuid)], limit=1)
            if duplicate:
                raise UserError(_("Ya existe una orden de compra con el UUID: %s" % uuid))
        productos = []
        for concepto in conceptos:
            producto_data = {
                'codigo': concepto.attrib.get('NoIdentificacion', ''),
                'descripcion': concepto.attrib.get('Descripcion', ''),
                'cantidad': float(concepto.attrib.get('Cantidad', 0)),
                'valor_unitario': float(concepto.attrib.get('ValorUnitario', 0)),
                'descuento': float(concepto.attrib.get('Descuento', 0)),
                'impuesto': 0,
            }

            # Leer impuestos si existen
            traslados = concepto.xpath('cfdi:Impuestos/cfdi:Traslados/cfdi:Traslado', namespaces=ns)
            producto_data['traslados'] = []

            for traslado in traslados:
                tasa_raw = traslado.attrib.get('TasaOCuota')
                impuesto_clave = traslado.attrib.get('Impuesto')  # 001, 002, etc.

                try:
                    tasa = float(tasa_raw)
                except (TypeError, ValueError):
                    tasa = 0.0

                producto_data['traslados'].append({
                    'impuesto': impuesto_clave,
                    'tasa': tasa,
                })
            productos.append(producto_data)

        # Extraer MetodoPago y FormaPago del XML
        metodo_pago = xml_tree.xpath('//cfdi:Comprobante/@MetodoPago', namespaces=ns)
        metodo_pago = metodo_pago[0] if metodo_pago else None
        forma_pago = xml_tree.xpath('//cfdi:Comprobante/@FormaPago', namespaces=ns)
        forma_pago = forma_pago[0] if forma_pago else None
        moneda = xml_tree.xpath('//cfdi:Comprobante/@Moneda', namespaces=ns)
        moneda = moneda[0] if moneda else None

        resultado = {
            'emisor_rfc': emisor_rfc,
            'emisor_name': emisor_name,
            'emisor_rf': emisor_rf,
            'receptor_rfc': receptor_rfc,
            'fecha': fecha,
            'productos': productos,
            'uuid': uuid,
            'folio': folio,
            'metodo_pago': metodo_pago,
            'forma_pago': forma_pago,
            'moneda': moneda,
        }

        _logger.info("Resultados XML: %s", resultado)
        return resultado

    def action_process_massive_xml(self):
        _logger.info('Iniciando procesamiento masivo de XML')
        msg_parts = []

        resultados = self._get_values_xml()
        
        partner_rfc = resultados.get('emisor_rfc', '').upper()
        partner_name = resultados.get('emisor_name')
        company_rfc = resultados.get('receptor_rfc')
        uuid = resultados.get('uuid')
        folio = resultados.get('folio')
        fecha = datetime.fromisoformat(resultados.get('fecha').replace('T', ' '))
        productos = resultados.get('productos', [])

        _logger.info(f">>> Factura UUID={uuid}, Folio={folio}, RFC Emisor={partner_rfc}")

        # ---------------- 1. VALIDACIONES INICIALES ----------------
        partner = self.env['res.partner'].sudo().search([('rfc', '=', partner_rfc)], limit=1)
        company = self.env['res.company'].sudo().search([('rfc', '=', company_rfc), ('is_branch', '=', False)], limit=1)
        
        if not company:
            raise ValidationError(f"No se encontró ninguna empresa asociada al RFC receptor: {company_rfc}")

        if not company.account_payable or not company.account_receivable:
             raise UserError(_(
                 f"La empresa {company.name} no tiene configurados los Grupos de Cuentas por Cobrar o Pagar.\n"
                 "Ve a Configuración de la Compañía y asigna los campos 'Cuentas por pagar' y 'Cuentas por cobrar'."
             ))

        # 4. BUSCAR O CREAR PROVEEDOR
        partner = self.env['res.partner'].sudo().search([('rfc', '=', partner_rfc)], limit=1)

        if not partner:
            _logger.info(f">>> No se encontró partner, creando nuevo...")
            
            try:
                # Obtener cuentas base VALIDADAS
                base_payable = company.account_payable
                base_receivable = company.account_receivable
                
                # ✅ FIX: Generar código único con protección contra duplicados
                def _get_unique_account_code(base_code, company_id):
                    """
                    Genera un código único de cuenta incrementando el consecutivo.
                    Si el código ya existe, sigue intentando hasta encontrar uno libre.
                    """
                    # Buscar todas las subcuentas existentes
                    existing_accounts = self.env['account.account'].sudo().search([
                        ('code', '=like', f"{base_code}.%"),
                        ('company_id', '=', company_id)
                    ])
                    
                    # Extraer solo los números finales válidos
                    used_numbers = []
                    for acc in existing_accounts:
                        parts = acc.code.split('.')
                        if len(parts) >= 2:
                            try:
                                used_numbers.append(int(parts[-1]))
                            except ValueError:
                                continue  # Ignorar códigos no numéricos
                    
                    # Encontrar el siguiente número disponible
                    next_num = 1
                    if used_numbers:
                        next_num = max(used_numbers) + 1
                    
                    # Verificar que no exista (doble validación)
                    max_attempts = 100
                    for attempt in range(max_attempts):
                        proposed_code = f"{base_code}.{next_num}"
                        
                        # Buscar si existe
                        duplicate = self.env['account.account'].sudo().search([
                            ('code', '=', proposed_code),
                            ('company_id', '=', company_id)
                        ], limit=1)
                        
                        if not duplicate:
                            return proposed_code
                        
                        # Si existe, incrementar
                        next_num += 1
                    
                    # Si después de 100 intentos no encuentra código libre, lanzar error
                    raise UserError(_(
                        f"No se pudo generar un código único para la cuenta. "
                        f"Revise las cuentas hijas de {base_code}"
                    ))
                
                # Generar códigos únicos
                payable_code = _get_unique_account_code(base_payable.code, company.id)
                receivable_code = _get_unique_account_code(base_receivable.code, company.id)
                
                _logger.info(f">>> Creando cuentas: Payable={payable_code}, Receivable={receivable_code}")
                
                # ✅ Crear cuenta por pagar
                partner_pay_acc = self.env['account.account'].sudo().create({
                    'name': partner_name,
                    'code': payable_code,
                    'company_id': company.id,
                    'account_type': 'liability_payable',
                    'reconcile': True,
                })
                
                # ✅ Crear cuenta por cobrar
                partner_rec_acc = self.env['account.account'].sudo().create({
                    'name': partner_name,
                    'code': receivable_code,
                    'company_id': company.id,
                    'account_type': 'asset_receivable',
                    'reconcile': True,
                })
                
                # Buscar régimen fiscal
                code = self.env['cfdi.claveregimenfiscal'].sudo().search(
                    [('Clave_regimenFiscal', '=', resultados.get('emisor_rf'))], limit=1
                )
                if not code:
                    code = self.env['cfdi.claveregimenfiscal'].sudo().search(
                        [('Clave_regimenFiscal', '=', '601')], limit=1
                    )
                
                # ✅ Crear partner
                partner = self.env['res.partner'].sudo().create({
                    'name': partner_name,
                    'rfc': partner_rfc,
                    'tax_regime': code.id if code else False,
                    'property_account_payable_id': partner_pay_acc.id,
                    'property_account_receivable_id': partner_rec_acc.id,
                    'supplier_rank': 1,
                })
                
                _logger.info(f'✅ Partner creado: {partner.name} (ID: {partner.id})')
                msg_parts.append(f"Se creó proveedor **{partner_name}**")
                
            except Exception as e:
                _logger.error(f"❌ Error creando partner: {str(e)}", exc_info=True)
                raise UserError(_(f"Error al crear el proveedor: {str(e)}"))


        if not partner:
            return False

        # ---------------- 3. PROCESAR PRODUCTOS ----------------
        order_line = []
        missing_products_data = [] 

        for producto in productos:
            product_code = producto.get('codigo')
            quantity = producto.get('cantidad', 0)
            price_unit = producto.get('valor_unitario', 0)
            description = producto.get('descripcion', '')
            discount = producto.get('descuento', 0)
            
            prod_match = False 
            supplier_info = False

            # A. Buscar por código exacto de proveedor
            if product_code:
                supplier_info = self.env['product.supplierinfo'].search(
                    [('product_code', '=', product_code), ('partner_id', '=', partner.id)], limit=1)
            
            # B. Buscar por descripción exacta de proveedor
            if not supplier_info:
                supplier_info = self.env['product.supplierinfo'].search(
                    [('product_name', 'ilike', description), ('partner_id', '=', partner.id)], limit=1)

            # C. Buscar por Fuzzy Search en proveedor
            if not supplier_info:
                all_supplier_info = self.env['product.supplierinfo'].search([('partner_id', '=', partner.id)])
                supplier_info = all_supplier_info.filtered(
                    lambda s: isinstance(s.product_name, str) and s.product_name.lower() in description.lower()
                )[:1]

            # D. Si no hay supplier info, intentar adivinar producto interno por Referencia Interna o Nombre
            if not supplier_info:
                 prod_match = self.env['product.product'].search([
                     '|', ('default_code', '=', product_code), ('name', 'ilike', description)
                 ], limit=1)

            # --- SI NO ENCUENTRA ENLACE: AGREGAR A FALTANTES ---
            if not supplier_info:
                missing_products_data.append({
                    'xml_code': product_code,
                    'xml_description': description,
                    'xml_quantity': quantity,
                    'xml_price': price_unit,
                    'suggested_product_id': prod_match.id if prod_match else False
                })
                continue # Importante: saltar al siguiente, no intentar crear línea

            # --- SI ENCUENTRA ENLACE: PREPARAR LÍNEA ---
            product = supplier_info.product_tmpl_id.product_variant_id
            packaging = self.env['product.packaging'].search(
                [('product_id', '=', product.id), ('partner_id', '=', partner.id)], order='sequence', limit=1)

            discount_percent = 0
            if discount and price_unit and quantity:
                discount_percent = (discount / (price_unit * quantity)) * 100

            line_vals = {
                'product_id': product.id,
                'price_unit': price_unit,
                'taxes_id': [(6, 0, product.supplier_taxes_id.ids)],
                'discount': discount_percent,
            }
            if packaging:
                line_vals.update({'product_packaging_qty': quantity, 'price_per_pack': price_unit})
            else:
                line_vals.update({'product_qty': quantity})

            order_line.append((0, 0, line_vals))

        # ---------------- 4. SI HAY FALTANTES ----------------
        if missing_products_data:
            wizard_lines = []
            for item in missing_products_data:
                vals = {
                    'xml_code': item['xml_code'],
                    'xml_description': item['xml_description'],
                    'xml_quantity': item['xml_quantity'],
                    'xml_price': item['xml_price'],
                    'action_type': 'link_existing' if item['suggested_product_id'] else 'create_new',
                    'selected_product_id': item['suggested_product_id']
                }
                wizard_lines.append((0, 0, vals))

            wizard = self.env['sat.xml.match.wizard'].create({
                'import_xml_id': self.id,
                'partner_id': partner.id,
                'line_ids': wizard_lines
            })

            # Retornamos la acción de ventana, NO una orden de compra
            return {
                'name': _('Conciliar Productos Faltantes'),
                'type': 'ir.actions.act_window',
                'res_model': 'sat.xml.match.wizard',
                'view_mode': 'form',
                'res_id': wizard.id,
                'target': 'new',
            }

        # ---------------- 5. CREACIÓN DE OC (Si todo está ok) ----------------
        purchase_order = False
        if order_line:
            purchase_order = self.env['purchase.order'].create({
                'partner_id': partner.id,
                'date_order': fecha,
                'invoice_date': fecha,
                'order_line': order_line,
                'uuid': uuid,
                'invoice_folio': folio,
                'cfdi_metodo_pago': resultados.get('metodo_pago'),
                'cfdi_forma_pago': resultados.get('forma_pago'),
                'cfdi_moneda': resultados.get('moneda'),
            })
            
            for line in purchase_order.order_line:
                line.sudo()._compute_product_qty()
                line.sudo()._compute_product_uom_qty()
                line.sudo()._compute_amount()
                line.sudo()._onchange_price_per_pack()
                line.sudo()._compute_markup()
            
            # ✅ NUEVA LÓGICA: Solo dejar en Draft, NO disparar aprobación
            _logger.info(f"✅ Orden de compra creada: {purchase_order.name} (Estado: {purchase_order.state})")
            
            # Agregar mensaje informativo
            if purchase_order.requires_authorization:
                purchase_order.message_post(
                    body=_(
                        "📋 **Orden creada desde XML**\n\n"
                        "Esta orden requiere aprobación manual.\n"
                        "Haz clic en **'Solicitar Autorización'** para iniciar el flujo de niveles."
                    )
                )


        # ---------------- 6. NOTIFICAR ERRORES NO CRÍTICOS ----------------
        if msg_parts:
            detail = f"<p><b>UUID:</b> {uuid} — <b>Folio:</b> {folio}</p>"
            if not purchase_order:
                detail += "<p><i>La orden de compra no se creó por errores en partner.</i></p>"
            self.sudo()._notify_error_in_upload(detail + "<br/>".join(msg_parts))

        return purchase_order

    def _notify_error_in_upload(self, msg):
        body_msg = msg
        # Obtener partner de OdooBot
        odoodbot_partner = self.env['res.partner'].search([('name', '=', 'OdooBot')], limit=1)

        # Buscar usuarios administradores relacionados a la empresa o sucursal
        admin_users = self.env['res.users'].search([
            ('groups_id', 'in', self.env.ref('base.group_system').id),
        ])

        if not admin_users:
            return

        # Crear el mensaje como OdooBot
        message = self.env['mail.message'].create({
            'model': 'res.users',
            'res_id': self.env.user.id,  # no afecta realmente aquí
            'message_type': 'notification',
            'subtype_id': self.env.ref('mail.mt_note').id,
            'body': body_msg,
            'subject': "Error en carga automática de facturas",
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


class PurchaseBranchLineSplit(models.Model):
    _name = 'purchase.line.branch.split'
    _description = 'Distribución por Sucursal (Línea OC)'
    _rec_name = 'display_name'

    def _get_branch_domain(self):
        company = self.env.company
        if company.is_branch:
            return [('parent_id', '=', company.parent_id.id)]
        else:
            return [('is_branch', '=', True), ('parent_id', '=', company.id)]

    branch_id = fields.Many2one('res.company', string='Sucursal', domain=lambda self: self._get_branch_domain())

    order_line_id = fields.Many2one(
        'purchase.order.line', ondelete='cascade')

    percent = fields.Float(
        string='Porcentaje',
        compute='_compute_percent', store=False
    )

    @api.depends('qty', 'order_line_id.product_qty')
    def _compute_percent(self):
        for rec in self:
            total = rec.order_line_id.product_qty or 0.0
            rec.percent = total and (rec.qty / total) * 100.0 or 0.0

    qty = fields.Float(
        string='Cantidad',
        digits='Product Unit of Measure',
        required=True
    )

    display_name = fields.Char(compute='_compute_display_name', store=False)

    @api.depends('branch_id', 'qty')
    def _compute_display_name(self):
        for r in self:
            wh = r.branch_id.display_name or ''
            r.display_name = f"{wh} - {r.qty}".strip()

    def name_get(self):
        result = []
        for record in self:
            display_name = f"{record.branch_id} ({record.qty})"
            result.append((record.id, display_name))
        return result

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=80):
        args = args or []
        line_id = self.env.context.get('current_order_line_id') or self.env.context.get('default_order_line_id')
        if line_id:
            args = expression.AND([args, [('order_line_id', '=', line_id)]])
        else:
            # Si no hay contexto de línea, no permitas reutilizar nada
            args = expression.AND([args, [('id', '=', 0)]])
        return super().name_search(name, args, operator=operator, limit=limit)
