import re

import pdfplumber
import pytz
import unicodedata

from odoo import models, fields, api, _, SUPERUSER_ID
from odoo.exceptions import UserError, ValidationError

from zeep import Client
from zeep.transports import Transport
import requests
import xmltodict
import base64
import qrcode
from io import BytesIO
from datetime import datetime
import calendar
from num2words import num2words
from markupsafe import Markup
import logging

_logger = logging.getLogger(__name__)

def remove_non_ascii(text):
    return ''.join(
        c for c in unicodedata.normalize('NFKD', text)
        if ord(c) < 128
    )

def cfdi_escape(text):
    """Escapa caracteres especiales para atributos XML según el estándar SAT."""
    if not text:
        return ""
    if not isinstance(text, str):
        text = str(text)
    return (text.replace("&", "&amp;")
                .replace('"', "&quot;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("'", "&apos;"))

class TicketMonitor(models.Model):
    _name = 'contabilidad_kuale.ticket_monitor'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Monitoreo de tickets'
    _check_company_auto = True

    company_id = fields.Many2one('res.company',string='Empresa',
        domain="[('id', 'not in', child_company_ids)]", index=True,default=lambda self: self.env.company,
    )
    branch_id = fields.Many2one('res.company',string='Sucursal',
        domain="['|', ('parent_id', '=', company_id), ('id', '=', company_id)]", index=True,
    )

    allowed_company_ids_full = fields.Many2many('res.company',compute='_compute_allowed_company_ids_full',
        string='Empresas y sucursales permitidas',)

    @api.depends('company_id')
    def _compute_allowed_company_ids_full(self):
        for rec in self:
            # Incluye la empresa activa y sus hijas
            companies = self.env.user.company_ids
            all_companies = companies | companies.mapped('child_ids') | companies.mapped('parent_id')
            rec.allowed_company_ids_full = all_companies

    business_name = fields.Char(related='branch_id.business_name')
    _rec_name = 'ticket_folio'
    ticket_folio = fields.Char(string='Número de ticket')
    folio = fields.Char(string='Folio')
    date = fields.Datetime(string='Fecha ticket')
    closed_date = fields.Datetime(string='Fecha de cierre')
    closing_time = fields.Char(string="Tiempo abierto", compute="_compute_closing_time", store=True)
    cashier = fields.Many2one('hr.employee', string='Cajero inicial', help="Empleado asociado que abrio la venta de mostrador")
    closing_cashier = fields.Many2one('hr.employee', string= 'Cajero final', help="Empleado asociado que cerro la venta de mostrador")

    payment_method = fields.Many2one('cfdi.clavemetododepago', string='Método de pago')
    payment_type = fields.Many2one('cfdi.claveformadepago', string='Forma de pago principal', help='Forma de pago principal utilizada para la facturacion (forma de pago con la que se pago la mayor parte de la orden)')
    payments_ids = fields.One2many('contabilidad_kuale.ticket_monitor_payments','ticket_id',string='Métodos de pago')

    iva = fields.Float(string='IVA',digits=(16, 6),compute='_compute_iva', store=True,readonly=True)
    total = fields.Float(string='Total',digits=(16, 6), compute='_compute_total', store=True)
    subtotal = fields.Float(string='Subtotal',digits=(16, 6))
    discount_ids = fields.Many2many('contabilidad_kuale.ticket_discount','ticket_discount_rel',
        'ticket_id','discount_id',string='Descuentos',domain="[('active', '=', True)]")
    discount = fields.Float(string='Descuento',digits=(16, 6))
    discount_authorized = fields.Many2one('hr.employee', string='Autorizado por', help="Empleado asociado a la autorización del descuento en ticket")

    ticket_status = fields.Selection([
        ('timbrado', 'Timbrado'),
        ('no_timbrado', 'No Timbrado'),
        ('global', 'Global'),
        ('timbrado_externo', 'Timbrado Externo'),
    ], string='Estatus ticket', default='no_timbrado')
    invoice_status = fields.Selection([
        ('vigente', 'Vigente'),
        ('cancelado', 'Cancelado'),
        ('refacturado', 'Refacturado'),
    ], string='Estatus factura', default='vigente')
    modification_status = fields.Boolean(string='Auditado', default=False)
    is_empty_ticket = fields.Boolean(string='Ticket Vacío', default=False, readonly=True)
    modification_details = fields.Selection([
        ('none','Sin modificación'),
        ('found','Con modificación')
    ],string='Modificaciones')

    iva_difference = fields.Boolean(string='Error en iva', help='esta casilla indica si al subir un ticket al sistema hay diferencia entre lo calculado y lo enviado por el sistema')

    child_company_ids = fields.Many2many('res.company',compute='_compute_child_companies',store=False)

    sell_type = fields.Many2one('contabilidad_kuale.ticket_sell_types', string='Tipo de venta', ondelete='set null')
    sell_type_code = fields.Char(related='sell_type.clave', string='Código Tipo de Venta')
    eoi_text = fields.Char(string='Cajero', compute='_compute_eoi_text')

    def _compute_eoi_text(self):
        for rec in self:
            rec.eoi_text = 'EOI'

    void_authorized = fields.Many2one('hr.employee', string='Cancelación autorizada por', help="Empleado asociado a la autorización de la cancelacion de un producto en ticket")
    reprint_number = fields.Integer(string='Numero de reimpresión de ticket', help='Información general (advertencia si el ticket pasa las 2 reimpresiones)')

    @api.depends('subtotal', 'iva')
    def _compute_total(self):
        for record in self:
            subtotal = record.subtotal or 0.0
            iva = record.iva or 0.0
            record.total = subtotal + iva

    @api.depends('subtotal')
    def _compute_iva(self):
        for record in self:
            subtotal = record.subtotal or 0.0
            record.iva = round(subtotal * 0.16, 6) if subtotal > 0 else 0

    @api.depends('date', 'closed_date')
    def _compute_closing_time(self):
        """ Calcula el tiempo en que estuvo abierto el ticket """
        for record in self:
            if record.date and record.closed_date:
                delta = record.closed_date - record.date
                hours, remainder = divmod(delta.total_seconds(), 3600)
                minutes, seconds = divmod(remainder, 60)
                record.closing_time = f"{int(hours)}h {int(minutes)}m {int(seconds)}s"
            else:
                record.closing_time = "En proceso"

    @api.depends('company_id')
    def _compute_child_companies(self):
        """Obtiene todas las compañías que son hijas de alguna otra."""
        all_childs = self.env['res.company'].search([('parent_id', '!=', False)])
        self.child_company_ids = all_childs.ids

    invoiced = fields.Boolean(string='Facturado')
    invoiced_type = fields.Selection([
        ('manual', 'Manual'),
        ('web', 'Cliente'),
        ('global', 'Global'),
        ('externa', 'Externa'),
    ], string='Forma de factura')
    invoiced_by_system = fields.Boolean(string='Facturado por el sistema')
    additional_files = fields.One2many('contabilidad_kuale.additional_file',
                                       'ticket_monitor_id', string='Archivos digitales')

    product_line = fields.One2many('contabilidad_kuale.ticket_monitor_line',
                                   'ticket_monitor_id',
                                   string='Productos')
    invoice_uuid = fields.Char(string='UUID')
    invoice_date = fields.Datetime(string='Fecha de factura')
    client_rfc = fields.Char(string='RFC', default='XAXX010101000')
    client_tax_regimen_id = fields.Many2one('cfdi.claveregimenfiscal', string='Régimen fiscal')
    client_cfdi_use_id = fields.Many2one('cfdi.claveusocfdi', string='Uso de CFDI')
    client_phone = fields.Char(string='Teléfono')
    client_email = fields.Char(string='Correo')
    client_name = fields.Char(string='Nombre o Razón Social')
    client_cp = fields.Char(string='Código postal')
    client_city = fields.Char(string='Ciudad')
    client_street_1 = fields.Char(string='Calle')
    client_street_2 = fields.Char(string='Calle adicional')

    sale_order_id = fields.Many2one('sale.order', string='Orden de Venta')
    invoice_id = fields.Many2one('account.move',string='Factura del sistema Odoo')

    logbook_ids = fields.One2many('contabilidad_kuale.ticket_monitor_logbook','ticket_id',string='Bitacora')

    gross_sale = fields.Float(string='Venta Bruta', digits=(16, 6), compute='compute_gross_sale', store=True)

    def compute_gross_sale(self):
        for rec in self:
            if rec.discount_ids:
                rec.gross_sale = rec.subtotal + rec.discount
            else:
                rec.gross_sale = rec.subtotal

    def confirm_related_sale_order(self):
        self.ensure_one()
        if self.sale_order_id and self.sale_order_id.state == 'draft':
            admin_user = self.env.ref('base.user_admin').id
            company_ids = list(filter(None, [self.branch_id.id, self.company_id.id]))
            self.sale_order_id.with_user(admin_user).sudo().with_context(allowed_company_ids=company_ids).action_confirm()
            return True
        return False

    def _notify_iva_error(self):
        print('company:', self.company_id)

        body_msg = (
            f"<b>Error con respecto al IVA calculado y enviado en ticket</b><br/>"
            f"Fecha: {self.date or 'Sin fecha'}<br/>"
            f"Sucursal: {self.branch_id.name or 'Sin sucursal'} - Empresa: {self.company_id.name or 'Sin empresa'}"
        )

        # Obtener partner de OdooBot
        odoodbot_partner = self.env['res.partner'].search([('name', '=', 'OdooBot')], limit=1)

        # Buscar usuarios administradores relacionados a la empresa o sucursal
        admin_users = self.env['res.users'].search([
            '|',
            ('company_id', '=', self.company_id.id),
            ('company_ids', 'in', [self.branch_id.id]),
            ('groups_id', 'in', self.env.ref('base.group_system').id),
        ])

        if not admin_users:
            return  # O podrías loggear o notificar que no se encontraron admins

        # Crear el mensaje como OdooBot
        message = self.env['mail.message'].create({
            'model': 'res.users',
            'res_id': self.env.user.id,  # no afecta realmente aquí
            'message_type': 'notification',
            'subtype_id': self.env.ref('mail.mt_note').id,
            'body': body_msg,
            'subject': "Detalles en el iva en ticket de sucursales",
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

    @api.model
    def create(self, vals):
        date_ticket = vals.get('date')
        company_id = vals.get('company_id')
        branch_id = vals.get('branch_id')

        subtotal = vals.get('subtotal', 0.0)
        iva_enviado = vals.get('iva', 0.0)
        iva_calculado = round(subtotal * 0.16, 6)

        if date_ticket and company_id and branch_id:
            date_obj = fields.Datetime.from_string(date_ticket)
            month = str(date_obj.month)
            year = str(date_obj.year)

            existing_summary = self.env['contabilidad_kuale.ticket_monitor_summary_history'].sudo().search([
                ('company_id', '=', company_id),
                ('branch_id', '=', branch_id),
                ('month', '=', month),
                ('year', '=', year),
            ], limit=1)

            if existing_summary:
                raise ValidationError(
                    "No se pueden crear tickets en este mes, ya se ha realizado la factura global."
                )

        if abs(iva_enviado - iva_calculado) > 0.01:
            vals['iva_difference'] = True

        res = super(TicketMonitor, self).create(vals)

        if res.iva_difference:
            res._notify_iva_error()

        res.inventory_adjustment()

        if res.discount_ids:
            for discount in res.discount_ids:
                if discount.use_once_per_day:
                    date_ticket = fields.Datetime.from_string(res.date)
                    start_day = date_ticket.replace(hour=0, minute=0, second=0)
                    end_day = date_ticket.replace(hour=23, minute=59, second=59)

                    previous_use = self.env['contabilidad_kuale.ticket_discount_usage'].sudo().search([
                        ('discount_id', '=', discount.id),
                        ('date', '>=', start_day),
                        ('date', '<=', end_day),
                    ], limit=1)

                    if previous_use:
                        raise ValidationError(f"El descuento '{discount.name}' solo puede usarse una vez por día ")

                self.env['contabilidad_kuale.ticket_discount_usage'].create({
                    'discount_id': discount.id,
                    'ticket_id': res.id,
                })
        res.compute_gross_sale()

        if res.reprint_number > 2:
            try:
                res._notify_warning_reprint()
            except Exception as e:
                import traceback
                _logger.warning(
                    'Error al enviar notificación de reimpresión ticket %s:\n%s',
                    res.ticket_folio,
                    traceback.format_exc()  # ← muestra el traceback completo
                )

        return res

    def write(self, vals):
        res = super(TicketMonitor, self).write(vals)

        if 'discount_ids' in vals:
            for rec in self:
                self.env['contabilidad_kuale.ticket_discount_usage'].search([
                    ('ticket_id', '=', rec.id)
                ]).unlink()

                for discount in rec.discount_ids:
                    self.env['contabilidad_kuale.ticket_discount_usage'].create({
                        'discount_id': discount.id,
                        'ticket_id': rec.id,
                    })
        update_required = False
        update_required |= 'product_line' in vals
        update_required |= 'branch_id' in vals
        update_required |= any(field in vals for field in ['total', 'discount', 'subtotal', 'iva'])
        if update_required and not self.env.context.get('skip_inventory_adjustment'):
            for rec in self:
                rec.inventory_adjustment()
        if 'reprint_number' in vals:
            for rec in self:
                if rec.reprint_number > 2:
                    self._notify_warning_reprint()

        return res

    def inventory_adjustment(self):
        self.ensure_one()
        # No crear sale order para tickets vacíos (sin productos y total 0)
        if self.is_empty_ticket or (not self.product_line and self.total == 0.0):
            return True
        if self.invoice_id:
            raise UserError('No es posible modificar tickets de venta una vez la auditoría automática se ha realizado.')

        # Obtener el usuario administrador y las compañías
        admin_user = self.env.ref('base.user_admin').id
        company_ids = list(filter(None, [
            self.branch_id.id if self.branch_id else None,
            self.company_id.id if self.company_id else None,
        ]))

        if self.sale_order_id:
            self.sale_order_id.with_user(admin_user).sudo().with_context(allowed_company_ids=company_ids).action_cancel()
            self.sale_order_id.sudo().unlink()

        env = self.with_user(admin_user).sudo().with_context(allowed_company_ids=company_ids).env

        public_customer = env['res.partner'].search([('name', '=', 'Venta al Público')], limit=1)
        if not public_customer:
            raise UserError(_('No se encontró el cliente "Venta al Público".'))

        sale_order = env['sale.order'].create({
            'partner_id': public_customer.id,
            'company_id': self.branch_id.id,
            'date_order': self.date,
            'origin': f'Ticket: {self.ticket_folio}',
            'state': 'draft',
        })

        for line in self.product_line:
            product = env['product.product'].search(
                [('third_party_id', '=', line.third_party_id)], limit=1
            )
            if not product:
                raise UserError(
                    _('Producto con código %s no encontrado.') % line.third_party_id
                )

            env['sale.order.line'].create({
                'order_id': sale_order.id,
                'product_id': product.id,
                'name': product.name,
                'product_uom_qty': line.quantity,
                'price_unit': line.unit_price,
                'discount': line.discount,
            })

        self.sudo().write({'sale_order_id': sale_order.id})
        sale_order.write({'immediate_product_release': True})
        return True

    def _get_digibox_token(self):
        """Función centralizada para obtener el token del PAC con Timeout."""
        try:
            # Configurar el timeout en 20 segundos
            session = requests.Session()
            transport = Transport(session=session, timeout=20)
            
            # URl del WSDL
            wsdl_url = 'https://timbrado.digibox.com.mx/Autenticacion/wsAutenticacion.asmx?WSDL'
            login_client = Client(wsdl=wsdl_url, transport=transport)
            
            # TODO: Idealmente, saca estas credenciales de self.company_id o de ir.config_parameter
            #usuario = "cfdi@grupokuale.com.mx"
            #password = "1?eFCeZ7LR8" 
            usuario = "pruebaskuale@digibox.com.mx"
            password = "123456789" 
            
            token = login_client.service.AutenticarBasico(usuario, password)
            
            if not token:
                raise UserError("El PAC no devolvió un token de autenticación válido.")
                
            return token
            
        except requests.exceptions.Timeout:
            raise UserError("El servicio del PAC (Digibox) tardó demasiado en responder. Intenta de nuevo más tarde.")
        except Exception as e:
            raise UserError(f"Error al conectar con el PAC para autenticación: {str(e)}")

    def action_timbrar(self, xml=None, extra_address=None):
        if not xml:
            print("not xml received")
        try:
            print('Obteniendo token...')
            token = self._get_digibox_token() # <--- Llamas a tu función segura
            
            print('Timbrando...')
            # IMPORTANTE: También ponle timeout al cliente que timbra
            session = requests.Session()
            transport = Transport(session=session, timeout=30) # 30 segs max para timbrar
            
            timbrar = Client('https://sellado.digibox.com.mx/Timbrado.svc?singleWsdl', transport=transport)
            # timbrar = Client('https://testtimbrado.digibox.com.mx/Digibox.ServiciosSellado/Timbrado.svc?wsdl')
            timbrar.service._binding_options['address'] = 'https://sellado.digibox.com.mx/Timbrado.svc'
            
            xml_timbrado = timbrar.service.TimbrarXmlV2(xml, token)
            if not xml_timbrado:
                raise UserError("El PAC no devolvió el XML timbrado.")
            print("Procesando respuesta del timbrado...")
            xml_dict = xmltodict.parse(xml_timbrado)
            tfd = xml_dict.get('cfdi:Comprobante', {}).get('cfdi:Complemento', {}).get('tfd:TimbreFiscalDigital', {})
            uuid = tfd.get('@UUID')


            self.write({
                'invoice_uuid': uuid,
                'invoice_date': fields.Datetime.now(pytz.timezone('America/Mexico_City')),
            })
            comprobante = xml_dict.get('cfdi:Comprobante', {})
            serie = comprobante.get('@Serie', '') or 'S/N'
            folio = comprobante.get('@Folio', '') or '0000'
            rfc_cliente = comprobante.get('cfdi:Receptor', {}).get('@Rfc') or self.client_rfc or 'XAXX010101000'
            base_filename = f"{rfc_cliente}-{serie}-{folio}"

            print("Guardando XML timbrado en archivos digitales...")
            file_data = base64.b64encode(xml_timbrado.encode('utf-8'))

            self.env['contabilidad_kuale.additional_file'].sudo().create({
                'ticket_monitor_id': self.id,
                'file': file_data,
                'file_name': f'{base_filename}.xml',
                'description': 'XML timbrado',
                'file_type': 'xml',
            })

            # Generar pdf
            if not extra_address:
                self.action_generate_invoice_pdf()
            else:
                self.action_generate_invoice_pdf(extra_address)

            pdf_file = self.env['contabilidad_kuale.additional_file'].search([
                ('ticket_monitor_id', '=', self.id),
                ('file_type', '=', 'pdf')
            ], order='id desc', limit=1)

            if pdf_file:
                pdf_file.write({'file_name': f'{base_filename}.pdf'})
            # Marcar como facturado
            self.invoiced_type = 'web'
            self.ticket_status = 'timbrado'
            self.invoiced = True
            self.branch_id.write({'client_folio_number': (self.branch_id.client_folio_number or 1) + 1})
            return {'status': 'success', 'message': 'timbrado correctamente'}

        except Exception as e:
            print(f"Error en el timbrado: {e}")
            # Guardamos el XML que se intentó timbrar para diagnóstico
            self._log_error(str(e), xml_content=xml)
            return {'status': 'error', 'message': str(e)}

    def action_generate_invoice_pdf(self, extra_address=None):
        print("Generando el PDF de la factura...")
        self.ensure_one()

        # Obtener el ID de la empresa
        company_id = self.company_id.id if self.company_id else None

        # print("id de la compañia: ", company_id)

        # Definir logo
        logo_base64 = ""
        if self.company_id.client_invoice_logo:
            logo_base64 = self.company_id.client_invoice_logo.decode() if isinstance(
                self.company_id.client_invoice_logo, bytes) else self.company_id.client_invoice_logo
        else:
            print("Advertencia: La empresa no tiene configurado el logo de facturación.")

        # Buscar el XML timbrado más reciente
        xml_file = self.env['contabilidad_kuale.additional_file'].search([
            ('ticket_monitor_id', '=', self.id),
            ('file_type', '=', 'xml')
        ], order='id desc', limit=1)

        if not xml_file:
            print("Error: No se encontró XML timbrado")
            return {'status': 'error', 'message': 'No se encontró XML timbrado'}

        try:
            # Decodificar el XML
            xml_content = base64.b64decode(xml_file.file).decode('utf-8')
            xml_dict = xmltodict.parse(xml_content)
            # print(xml_dict)

            # Extraer el UUID del XML
            uuid = xml_dict.get('cfdi:Comprobante', {}).get('cfdi:Complemento', {}).get('tfd:TimbreFiscalDigital',
                                                                                        {}).get('@UUID', '')

            if not uuid:
                print("Error: No se encontró UUID en el XML")
                return {'status': 'error', 'message': 'No se encontró UUID en el XML'}

            # Generar el QR
            qr_data = f"https://verificacfdi.facturaelectronica.sat.gob.mx/default.aspx?id={uuid}"
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=0,
            )
            qr.add_data(qr_data)
            qr.make(fit=True)

            img = qr.make_image(fill_color="black", back_color="white")

            # Convertir la imagen QR a base64
            buffered = BytesIO()
            img.save(buffered, format="PNG")
            qr_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

            # Extraer datos del XML
            invoice_data = xml_dict.get('cfdi:Comprobante', {})
            emisor = invoice_data.get('cfdi:Emisor', {})
            receptor = invoice_data.get('cfdi:Receptor', {})
            conceptos = invoice_data.get('cfdi:Conceptos', {}).get('cfdi:Concepto', [])
            impuestos = invoice_data.get('cfdi:Impuestos', {})
            total_impuestos_trasladados = impuestos.get('@TotalImpuestosTrasladados', 'No disponible')

            if not isinstance(conceptos, list):
                conceptos = [conceptos]

            # Obtener el importe total del XML
            total_str = invoice_data.get('@Total', '0.00')  # Si no encuentra el total, usa 0.00
            total_float = float(total_str)  # Convertimos a flotante

            # Convertir el total a letras en formato "Mil pesos 50/100 M.N."
            total_entero = int(total_float)
            centavos = int(round((total_float - total_entero) * 100))  # Extrae los centavos
            total_letras = f"{num2words(total_entero, lang='es').capitalize()} pesos {centavos:02d}/100 M.N."

            # Extraer y mapear claves
            forma_pago_clave = invoice_data.get('@FormaPago', '')
            forma_pago_obj = self.env['cfdi.claveformadepago'].search([('Clave_forma_de_pago', '=', forma_pago_clave)],
                                                                      limit=1)
            descripcion_forma_pago = forma_pago_obj.Descripcion if forma_pago_obj else 'No encontrada'

            metodo_pago_clave = invoice_data.get('@MetodoPago', '')
            metodo_pago_obj = self.env['cfdi.clavemetododepago'].search(
                [('Clave_metodo_de_pago', '=', metodo_pago_clave)], limit=1)
            descripcion_metodo_pago = metodo_pago_obj.Descripcion if metodo_pago_obj else 'No encontrado'

            regimen_fiscal_clave_emisor = emisor.get('@RegimenFiscal', '')
            regimen_fiscal_obj_emisor = self.env['cfdi.claveregimenfiscal'].search(
                [('Clave_regimenFiscal', '=', regimen_fiscal_clave_emisor)], limit=1)
            descripcion_regimen_fiscal_emisor = regimen_fiscal_obj_emisor.Descripcion if regimen_fiscal_obj_emisor else 'No encontrado'

            regimen_fiscal_clave_receptor = receptor.get('@RegimenFiscalReceptor', '')
            regimen_fiscal_obj_receptor = self.env['cfdi.claveregimenfiscal'].search(
                [('Clave_regimenFiscal', '=', regimen_fiscal_clave_receptor)], limit=1)
            descripcion_regimen_fiscal_receptor = regimen_fiscal_obj_receptor.Descripcion if regimen_fiscal_obj_receptor else 'No encontrado'

            uso_cfdi_clave = receptor.get('@UsoCFDI', '')
            uso_cfdi_obj = self.env['cfdi.claveusocfdi'].search([('Clave_UsoCFDI', '=', uso_cfdi_clave)], limit=1)
            descripcion_uso_cfdi = uso_cfdi_obj.Descripcion if uso_cfdi_obj else 'No encontrado'

            clave_moneda = invoice_data.get('@Moneda', '')
            moneda_obj = self.env['cfdi.clavemoneda'].search([('Clave_moneda', '=', clave_moneda)], limit=1)
            descripcion_moneda = moneda_obj.Descripcion if moneda_obj else 'No encontrado'

            conceptos_procesados = []
            for concepto in conceptos:
                clave_objetoimp = concepto.get('@ObjetoImp', '')
                objeto_imp = self.env['cfdi.claveobjetoimp'].search([('Clave_objetoimp', '=', clave_objetoimp)],
                                                                    limit=1)
                descripcion_objetoimp = objeto_imp.Descripcion if objeto_imp else 'No encontrado'

                clave_impuesto = concepto.get('cfdi:Impuestos', {}).get('cfdi:Traslados', {}).get('cfdi:Traslado',
                                                                                                  {}).get('@Impuesto',
                                                                                                          '')
                impuesto = self.env['cfdi.claveimpuesto'].search([('Clave_impuesto', '=', clave_impuesto)], limit=1)
                descripcion_impuesto = impuesto.Descripcion if impuesto else 'No encontrado'

                concepto['descripcion_objetoimp'] = descripcion_objetoimp
                concepto['descripcion_impuesto'] = descripcion_impuesto

                conceptos_procesados.append(concepto)

            # Generar el PDF con QWeb
            print("Renderizando PDF con QWeb...")
            report_ref = self.env.ref('contabilidad_kuale.report_invoice')

            # Pasar datos al contexto, incluyendo el logo en base64 y el importe en letras
            if not extra_address:
                extra_address = ' '
            pdf_content, _ = report_ref._render_qweb_pdf(report_ref.id, data={
                'factura': self,
                'invoice_data': invoice_data,
                'emisor': emisor,
                'receptor': receptor,
                'conceptos': conceptos_procesados,
                'company_id': int(self.company_id.client_invoice_color),
                'logo_base64': logo_base64,
                'qr_base64': qr_base64,
                'total_letras': total_letras,
                'total_impuestos_trasladados': total_impuestos_trasladados,
                'descripcion_forma_pago': descripcion_forma_pago,
                'descripcion_metodo_pago': descripcion_metodo_pago,
                'descripcion_regimen_fiscal_emisor': descripcion_regimen_fiscal_emisor,
                'descripcion_regimen_fiscal_receptor': descripcion_regimen_fiscal_receptor,
                'descripcion_uso_cfdi': descripcion_uso_cfdi,
                'descripcion_moneda': descripcion_moneda,
                'descripcion_objetoimp': descripcion_objetoimp,
                'descripcion_impuesto': descripcion_impuesto,
                'domicilio_extra': extra_address,
            })

            if not pdf_content:
                print("Error: No se generó contenido PDF")
                return {'status': 'error', 'message': 'No se generó contenido PDF'}

            # Codificar PDF en base64
            pdf_base64 = base64.b64encode(pdf_content)

            # Guardar el PDF junto con el XML
            pdf_file_name = xml_file.file_name.replace('.xml', '.pdf')
            self.env['contabilidad_kuale.additional_file'].sudo().create({
                'ticket_monitor_id': self.id,
                'file': pdf_base64,
                'file_name': pdf_file_name,
                'description': 'PDF generado',
                'file_type': 'pdf',
            })

            print("PDF guardado correctamente.")
            return {'status': 'success', 'message': 'PDF generado y guardado correctamente'}

        except Exception as e:
            print(f"Error en la generación del PDF: {e}")
            return {'status': 'error', 'message': str(e)}

    def _generate_xml(self):
        fecha_emision = str(self.date).replace(" ", "T")[:19]
        forma_pago = self.payment_type.Clave_forma_de_pago
        metodo_pago = self.payment_method.Clave_metodo_de_pago
        lugar_expedicion = self.branch_id.zip
        exportacion = "01"
        print('branch: ', self.branch_id)
        company = self.env['res.company'].sudo().browse(self.branch_id.id)
        matriz = self.env['res.company'].sudo().browse(self.company_id.id)
        if not company:
            return {
                'status': 400,
                'data': [],
                'error': 'Error en datos de facturación, revise su información de compra'
            }

        rfc_emisor = company.rfc
        nombre_emisor = cfdi_escape(company.business_name)
        regimen_fiscal = company.regimen_fiscal.Clave_regimenFiscal
        serie = cfdi_escape(company.client_serial_number or '')
        folio = company.client_folio_number
        folio = str(folio).zfill(4)

        rfc_receptor = self.client_rfc
        nombre_receptor = cfdi_escape(self.client_name)
        domicilio_fiscal_receptor = self.client_cp
        regimen_fiscal_receptor = self.client_tax_regimen_id.Clave_regimenFiscal if self.client_tax_regimen_id else ''
        uso_cfdi = self.client_cfdi_use_id.Clave_UsoCFDI if self.client_cfdi_use_id else ''

        subtotal = 0.0
        total_iva = 0.0
        total_descuento = 0.0
        conceptos_xml = ""

        single_concept = matriz.single_concept
        # single_concept = company.single_concept
        if single_concept:
            print("single_concept")
            # Concepto único
            total_amount = sum(line.unit_price * line.quantity for line in self.product_line)
            total_discount = sum(line.discount for line in self.product_line if line.discount > 0)
            base_iva = total_amount - total_discount
            importe_iva = round(base_iva * 0.16, 6)

            subtotal = base_iva
            subtotal_no_desc = total_amount
            total_iva = importe_iva
            total_descuento = total_discount
            concepto_descuento = f' Descuento="{total_descuento:.2f}"' if total_descuento > 0 else ""

            # !TODO: DEFINE CARLS AND TITO IDs
            if matriz.client_invoice_color == "4" or company.client_invoice_color == "4":
                # datos de lo de CARLS
                clave_prod_serv = '90101500'
                clave_unidad = 'E48'
                descripcion = cfdi_escape(f'Consumo de alimentos - Número de ticket {self.ticket_folio} - Fecha de consumo {self.date.strftime("%d/%m/%Y")}')
            else:
                # datos de lo de TINTO
                clave_prod_serv = '91111500'
                clave_unidad = 'E48'
                descripcion = cfdi_escape(f'Servicio de tintorería - Número de ticket {self.ticket_folio} - Fecha {self.date.strftime("%d/%m/%Y")}')
            conceptos_xml = f'''
                <cfdi:Concepto ClaveProdServ="{clave_prod_serv}" NoIdentificacion="{self.ticket_folio}" Cantidad="1"
                ClaveUnidad="{clave_unidad}" Descripcion="{descripcion}" ValorUnitario="{round(total_amount, 2):.2f}" Importe="{round(total_amount, 2):.2f}"
                {concepto_descuento} ObjetoImp="02">
                    <cfdi:Impuestos>
                        <cfdi:Traslados>
                            <cfdi:Traslado Base="{round(base_iva, 2):.2f}" Impuesto="002" TipoFactor="Tasa" TasaOCuota="0.160000" Importe="{round(importe_iva, 2):.2f}"/>
                        </cfdi:Traslados>
                    </cfdi:Impuestos>
                </cfdi:Concepto>
            '''
        else:
            # Un concepto por producto
            for line in self.product_line:
                product = self.env['product.template'].sudo().search([('third_party_id', '=', line.third_party_id)],
                                                                     limit=1)
                clave_prod_serv = product.sat_code_id.code if product else '01010101'
                no_identificacion = cfdi_escape(product.identification_number if product else self.ticket_folio)
                cantidad = str(line.quantity) if line.quantity else '1'
                clave_unidad = product.unit_clave.Clave_unidad if product else "ACT"
                descripcion = cfdi_escape(product.name if product else "Venta")

                descuento = round(line.discount, 2) if line.discount and line.discount > 0 else 0.0
                valor_unitario = line.unit_price
                importe = line.unit_price * line.quantity
                base_iva = importe - descuento
                importe_iva = round(base_iva * 0.16, 6)

                subtotal += importe
                total_iva += importe_iva
                total_descuento += descuento

                concepto_descuento = f' Descuento="{descuento:.2f}"' if descuento > 0 else ""
                descripcion_final = f'Productos destinados a la alimentación {descripcion} - Número de ticket {self.ticket_folio} - Fecha de consumo {self.date.strftime("%d/%m/%Y")}'
                conceptos_xml += f'''
                    <cfdi:Concepto ClaveProdServ="{clave_prod_serv}" NoIdentificacion="{no_identificacion}" Cantidad="{cantidad}"
                    ClaveUnidad="{clave_unidad}" Descripcion="{descripcion_final}" ValorUnitario="{valor_unitario}" Importe="{importe}"
                    {concepto_descuento} ObjetoImp="02">
                        <cfdi:Impuestos>
                            <cfdi:Traslados>
                                <cfdi:Traslado Base="{base_iva}" Impuesto="002" TipoFactor="Tasa" TasaOCuota="0.160000" Importe="{importe_iva}"/>
                            </cfdi:Traslados>
                        </cfdi:Impuestos>
                    </cfdi:Concepto>
                '''
        if single_concept:
            if total_descuento > 0:
                total = subtotal + total_iva
                descuento_attr = f' Descuento="{round(total_descuento, 2):.2f}"'
            else:
                subtotal_no_desc = subtotal
                total = subtotal + total_iva
                descuento_attr = ""
        else:
            if total_descuento > 0:
                subtotal_no_desc = subtotal
                subtotal = subtotal - total_descuento
                total = subtotal + total_iva
                descuento_attr = f' Descuento="{round(total_descuento, 2):.2f}"'
            else:
                subtotal_no_desc = subtotal
                total = subtotal + total_iva
                descuento_attr = ""



        xml = f'''
        <cfdi:Comprobante Version="4.0" Serie="{serie}" Folio="{folio}" Fecha="{datetime.now(pytz.timezone('America/Mexico_City')).strftime('%Y-%m-%dT%H:%M:%S')}" SubTotal="{round(subtotal_no_desc, 2):.2f}" Total="{round(total, 2):.2f}" 
        Moneda="MXN" TipoDeComprobante="I" LugarExpedicion="{lugar_expedicion}" FormaPago="{forma_pago}" MetodoPago="{metodo_pago}"
        Exportacion="{exportacion}" {descuento_attr}
        xmlns:cfdi="http://www.sat.gob.mx/cfd/4" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
        xsi:schemaLocation="http://www.sat.gob.mx/cfd/4 http://www.sat.gob.mx/sitio_internet/cfd/4/cfdv40.xsd">
            <cfdi:Emisor Rfc="{rfc_emisor}" Nombre="{nombre_emisor}" RegimenFiscal="{regimen_fiscal}"/>
            <cfdi:Receptor Rfc="{rfc_receptor}" Nombre="{nombre_receptor}" DomicilioFiscalReceptor="{domicilio_fiscal_receptor}"
            RegimenFiscalReceptor="{regimen_fiscal_receptor}" UsoCFDI="{uso_cfdi}"/>
            <cfdi:Conceptos>
                {conceptos_xml}
            </cfdi:Conceptos>
            <cfdi:Impuestos TotalImpuestosTrasladados="{round(total_iva, 2):.2f}">
                <cfdi:Traslados>
                    <cfdi:Traslado Base="{round(subtotal, 2):.2f}" Impuesto="002" TipoFactor="Tasa" 
                    TasaOCuota="0.160000" Importe="{round(total_iva, 2):.2f}"/>
                </cfdi:Traslados>
            </cfdi:Impuestos>
        </cfdi:Comprobante>
        '''

        return xml

    def action_invoice(self):
        """
        Verifica que existan los datos del cliente para facturación.
        Si los datos están completos, se genera el XML y se procede a timbrar.
        """
        required_fields = ['client_rfc', 'client_name', 'client_cp', 'client_tax_regimen_id', 'client_cfdi_use_id']
        missing = [field for field in required_fields if not getattr(self, field)]
        if missing:
            raise UserError(_('Faltan datos de facturación en el cliente: %s') % ', '.join(missing))

        # Generar el XML
        xml = self._generate_xml()
        if not xml:
            raise UserError(_('No se pudo generar el XML de la factura.'))

        # Llamar al timbrado con el XML generado
        result = self.action_timbrar(xml)
        if result.get('status') == 'error':
            # Guardamos el XML que falló para diagnóstico en la bitácora
            self._log_error(result.get('message'), xml_content=xml)
            raise UserError(_('Error en el timbrado: %s') % result.get('message'))

        return result

    def send_invoice_email(self, email_to):
        self.ensure_one()

        # 1. Buscar la plantilla configurada en la sucursal o empresa
        template = self.branch_id.invoice_email_template_id or self.company_id.invoice_email_template_id
        if not template:
            template = self.env.ref('contabilidad_kuale.email_template_factura_ticket', raise_if_not_found=False)
        
        if not template:
            self._log_error("No se encontró la plantilla de correo para enviar la factura.")
            return False

        # 2. Preparar los adjuntos (XML y PDF)
        invoice_files = self.env['contabilidad_kuale.additional_file'].sudo().search([
            ('ticket_monitor_id', '=', self.id),
            ('file_type', 'in', ['pdf', 'xml'])
        ], order='id desc', limit=2)

        attachment_ids = []
        for f in invoice_files:
            attachment_ids.append(self.env['ir.attachment'].sudo().create({
                'name': f.file_name,
                'type': 'binary',
                'datas': f.file,
                'res_model': 'contabilidad_kuale.ticket_monitor',
                'res_id': self.id,
            }).id)

        # 3. ENVÍO CONTROLADO POR LA PLANTILLA
        try:
            template.sudo().send_mail(
                self.id, 
                force_send=True, 
                email_values={
                    'email_to': email_to,
                    'attachment_ids': [(6, 0, attachment_ids)]
                }
            )
        except Exception as e:
            self._log_error(f"Error al intentar enviar el correo: {str(e)}")
            return False

        return True

    def action_send_invoice_email(self):
        if self.invoiced:
            if self.client_email:
                self.send_invoice_email(email_to=self.client_email)
            else:
                raise UserError('No se encontro el correo del destinatario - verifique el correo del cliente')
        else:
            raise UserError('La factura debe ser generada antes de enviar o reenviar el correo')

    def action_open_ticket_summary_wizard(self):
        if self:
            matrix_id = self[0].company_id.id
            branch_id = self[0].branch_id.id
        else:
            current_company = self.env.company
            if current_company.parent_id:
                matrix_id = current_company.parent_id.id
                branch_id = current_company.id
            else:
                matrix_id = current_company.id
                branch_id = False

        return {
            'type': 'ir.actions.act_window',
            'name': 'Resumen Mensual de Tickets',
            'res_model': 'contabilidad_kuale.ticket_summary_wizard',
            'view_mode': 'form',
            'view_id': self.env.ref('contabilidad_kuale.view_ticket_summary_wizard_form').id,
            'target': 'new',
            'context': {
                'default_company_id': matrix_id,
                'default_branch_id': branch_id,
            },
        }

    def action_open_ticket_exterior_wizard(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Carga Timbrado Externo',
            'res_model': 'contabilidad_kuale.ticket_exterior_wizard',
            'view_mode': 'form',
            'view_id': self.env.ref('contabilidad_kuale.view_ticket_exterior_wizard_form').id,
            'target': 'new',
        }

    def _log_error(self, description, xml_content=None):
        """Guarda en bitácora los errores ocurridos durante facturación o PDF."""
        self.ensure_one()
        vals = {
            'date': fields.Date.context_today(self),
            'description': description[:2000],  # evita que errores largos rompan la vista
            'ticket_id': self.id,
        }
        if xml_content:
            vals['xml_content'] = xml_content[:50000]  # Límite de seguridad
        self.env['contabilidad_kuale.ticket_monitor_logbook'].sudo().create(vals)


    def _get_or_create_alert_channel(self):
        channel = self.env['mail.channel'].sudo().search([
            ('name', '=', 'Alertas POS')
        ], limit=1)

        if not channel:
            channel = self.env['mail.channel'].sudo().create({
                'name': 'Alertas POS',
                'channel_type': 'channel',
                'description': 'Canal de alertas automáticas del punto de venta',
            })

            # Agregar admins al canal automáticamente
            admin_users = self.env['res.users'].search([
                ('groups_id', 'in', self.env.ref('base.group_system').id),
            ])

            channel.sudo().write({
                'channel_member_ids': [
                    (0, 0, {'partner_id': user.partner_id.id})
                    for user in admin_users if user.partner_id
                ]
            })

        return channel
    
    def _notify_warning_reprint(self):
        body_msg = (
            f"<b>Detalles de reimpresión de tickets</b><br/>"
            f"Fecha: {self.date or 'Sin fecha'}<br/>"
            f"Sucursal: {self.branch_id.name or 'Sin sucursal'}<br/>"
            f"Empresa: {self.company_id.name or 'Sin empresa'}<br/>"
            f"<b>Se detecto el ticket con folio {self.ticket_folio} con mas de 2 reimpresiones</b>"
        )

        odoobot_user = self.env.ref('base.user_root')
        odoobot_partner = odoobot_user.partner_id

        channel = self.env['discuss.channel'].sudo().search([
            ('name', '=', 'DQ Hidalgo')
        ], limit=1)

        if not channel:
            _logger.warning('Canal "DQ Hidalgo" no encontrado.')
            return

        # En Odoo 17 sudo() no acepta usuario, usa with_user() en su lugar
        channel.with_user(odoobot_user).sudo().message_post(
            body=Markup(body_msg),
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
            author_id=odoobot_partner.id,
        )
            

    def action_open_cancel_wizard(self):
        self.ensure_one()

        if not self.invoice_uuid:
            raise UserError("El ticket no tiene UUID de factura para cancelar.")

        return {
            'name': 'Cancelar factura',
            'type': 'ir.actions.act_window',
            'res_model': 'contabilidad_ticket.invoice_cancellation',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_company_id': self.company_id.id,
                'default_branch_id': self.branch_id.id,
                'default_invoice_uuid': self.invoice_uuid,
            }
        }

    def open_cfdi_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Subir Constancia de Situación Fiscal'),
            'res_model': 'ticket.wizard.cfdi',
            'view_mode': 'form',
            'target': 'new',  # abre como modal
            'context': {
                'default_ticket_id': self.id,
            }
        }



class TicketMonitorLine(models.Model):
    _name = 'contabilidad_kuale.ticket_monitor_line'
    _description = 'Monitoreo de ticket line'

    third_party_id = fields.Char(string='Id campo de terceros',
                                 help='Campo de identificacion del producto en base al sistema de venta y el sistema de gestion')
    description = fields.Char(string='Descripcion',compute='_compute_description', store=True)
    quantity = fields.Integer(string='Cantidad')
    unit_price = fields.Float(string='precio Unitario',digits=(16, 6))
    discount = fields.Float(string='Descuento',digits=(16, 6))
    uom = fields.Many2one('uom.uom', string='Unidad de medida',compute='_compute_uom', store=True)
    subtotal = fields.Float(
        string="Subtotal",
        compute="_compute_subtotal",
        store=True,digits=(16, 6)
    )
    total = fields.Float(
        string="Total",
        compute="_compute_total",
        store=True, digits=(16, 6)
    )
    ticket_monitor_audit_id = fields.Many2one('contabilidad_kuale.ticket_monitor_audit', string='Auditoría',
                                              ondelete='cascade')
    ticket_audit_id = fields.Many2one('contabilidad_kuale.ticket_monitor_audit', string='Auditoría', ondelete='cascade')

    ticket_monitor_id = fields.Many2one('contabilidad_kuale.ticket_monitor', string='Ticket', ondelete='cascade')

    @api.depends('third_party_id')
    def _compute_description(self):
        for line in self:
            if not line.third_party_id:
                line.description = ''
                continue
            # Search product.template directly: its `name` is a plain Char field.
            # Avoids going through product.product.name which is a related field
            # (_compute_related chain) that fails when the ORM deferred-flush runs
            # under OdooBot (su=False) at commit time.
            template = self.env['product.template'].sudo().with_context(
                active_test=False, show_all_products=True
            ).search([('third_party_id', '=', line.third_party_id)], limit=1)
            line.description = template.name or '' if template else ''

    @api.depends('third_party_id')
    def _compute_uom(self):
        for line in self:
            if not line.third_party_id:
                line.uom = None
                continue
            template = self.env['product.template'].sudo().with_context(
                active_test=False, show_all_products=True
            ).search([('third_party_id', '=', line.third_party_id)], limit=1)
            line.uom = template.uom_po_id.id if template and template.uom_po_id else None

    @api.depends("unit_price", "quantity","discount")
    def _compute_subtotal(self):
        for line in self:
                line.subtotal = line.unit_price * line.quantity

    @api.depends("unit_price", "quantity","discount","subtotal")
    def _compute_total(self):
        for line in self:
            if line.discount> 0:
                iva = (line.subtotal - line.discount) * 0.16 if (line.subtotal - line.discount) > 0 else 0
                line.total = (line.subtotal - line.discount) + iva
            else:
                iva = (line.subtotal * 0.16) if line.subtotal > 0 else 0
                line.total = line.subtotal + iva

class TicketMonitorSummary(models.Model):
    _name = 'contabilidad_kuale.ticket_monitor_summary'
    _description = 'Resumen Mensual de Tickets por Sistema'

    company_id = fields.Many2one('res.company', string="Compañía", required=True)
    branch_id = fields.Many2one('res.company', string="Sucursal",
                                domain="['|', ('parent_id', '=', company_id), ('id', '=', company_id)]", required=True)
    month = fields.Selection(
        [(str(i), datetime(2000, i, 1).strftime('%B')) for i in range(1, 13)],
        string="Mes", required=True
    )
    year = fields.Selection(
        [(str(y), str(y)) for y in range(2020, datetime.now().year + 1)],
        string="Año", required=True
    )

    tickets_quantity = fields.Integer(string="Numero total de tickets")
    total_tickets = fields.Float(string="Total",digits=(16, 6))
    subtotal_tickets = fields.Float(string="Subtotal",digits=(16, 6))
    iva_tickets = fields.Float(string="IVA",digits=(16, 6))

    invoice_tickets_quantity = fields.Integer(string='Numero total de tickets facturados')
    total_invoiced = fields.Float(string="Total facturado",digits=(16, 6))
    subtotal_invoiced = fields.Float(string="Subtotal facturado",digits=(16, 6))
    iva_invoiced = fields.Float(string="IVA Facturado",digits=(16, 6))

    non_invoiced_quantity = fields.Integer('Numero total de tickets no facturados')
    total_non_invoiced = fields.Float(string="Total no facturado",digits=(16, 6))
    subtotal_non_invoiced = fields.Float(string="Subtotal no facturado",digits=(16, 6))
    iva_non_invoiced = fields.Float(string="IVA no facturado",digits=(16, 6))

class TicketSummaryWizard(models.TransientModel):
    _name = 'contabilidad_kuale.ticket_summary_wizard'
    _description = 'Resumen Mensual de Tickets'

    company_id = fields.Many2one('res.company', string="Compañía", domain="[('is_branch', '=', False)]", required=True, default=lambda self: self.env.company)
    branch_id = fields.Many2one('res.company', string="Sucursal",
                                domain="[('parent_id', '=', company_id)]", required=True, default=lambda self: self.env.company)

    month = fields.Selection(
        [(str(i), datetime(2000, i, 1).strftime('%B')) for i in range(1, 13)],
        string="Mes",
    )
    year = fields.Selection(
        [(str(y), str(y)) for y in range(2020, datetime.now().year + 1)],
        string="Año"
    )
    
    #RANGO DE FECHA
    date_from = fields.Date(string="Desde")
    date_to = fields.Date(string="Hasta")
    # SISTEMA
    tickets_quantity = fields.Integer(string="Numero total de tickets", readonly=True)
    total_tickets = fields.Float(string="Total", readonly=True,digits=(16, 6))
    subtotal_tickets = fields.Float(string="Subtotal", readonly=True,digits=(16, 6))
    iva_tickets = fields.Float(string="IVA", readonly=True,digits=(16, 6))

    invoice_tickets_quantity = fields.Integer(string='Numero total de tickets facturados', readonly=True)
    total_invoiced = fields.Float(string="Total facturado", readonly=True,digits=(16, 6))
    subtotal_invoiced = fields.Float(string="Subtotal facturado", readonly=True,digits=(16, 6))
    iva_invoiced = fields.Float(string="IVA Facturado", readonly=True,digits=(16, 6))

    non_invoiced_quantity = fields.Integer('Numero total de tickets no facturados', readonly=True)
    total_non_invoiced = fields.Float(string="Total no facturado", readonly=True,digits=(16, 6))
    subtotal_non_invoiced = fields.Float(string="Subtotal no facturado", readonly=True,digits=(16, 6))
    iva_non_invoiced = fields.Float(string="IVA no facturado", readonly=True,digits=(16, 6))

    # PIXLR
    system_tickets_quantity = fields.Integer(string="Numero total de tickets", readonly=True)
    system_total_tickets = fields.Float(string="Total", readonly=True,digits=(16, 6))
    system_subtotal_tickets = fields.Float(string="Subtotal", readonly=True,digits=(16, 6))
    system_iva_tickets = fields.Float(string="IVA", readonly=True,digits=(16, 6))

    system_invoice_tickets_quantity = fields.Integer(string='Numero total de tickets facturados', readonly=True)
    system_total_invoiced = fields.Float(string="Total facturado", readonly=True,digits=(16, 6))
    system_subtotal_invoiced = fields.Float(string="Subtotal facturado", readonly=True,digits=(16, 6))
    system_iva_invoiced = fields.Float(string="IVA Facturado", readonly=True,digits=(16, 6))

    system_non_invoiced_quantity = fields.Integer('Numero total de tickets no facturados', readonly=True)
    system_total_non_invoiced = fields.Float(string="Total no facturado", readonly=True,digits=(16, 6))
    system_subtotal_non_invoiced = fields.Float(string="Subtotal no facturado", readonly=True,digits=(16, 6))
    system_iva_non_invoiced = fields.Float(string="IVA no facturado", readonly=True,digits=(16, 6))

    # difference

    difference_tickets_quantity = fields.Integer(string="Numero total de tickets", readonly=True)
    difference_total_tickets = fields.Float(string="Total", readonly=True,digits=(16, 6))
    difference_subtotal_tickets = fields.Float(string="Subtotal", readonly=True,digits=(16, 6))
    difference_iva_tickets = fields.Float(string="IVA", readonly=True,digits=(16, 6))

    difference_invoice_tickets_quantity = fields.Integer(string='Numero total de tickets facturados', readonly=True)
    difference_total_invoiced = fields.Float(string="Total facturado", readonly=True,digits=(16, 6))
    difference_subtotal_invoiced = fields.Float(string="Subtotal facturado", readonly=True,digits=(16, 6))
    difference_iva_invoiced = fields.Float(string="IVA Facturado", readonly=True,digits=(16, 6))

    difference_non_invoiced_quantity = fields.Integer('Numero total de tickets no facturados', readonly=True)
    difference_total_non_invoiced = fields.Float(string="Total no facturado", readonly=True,digits=(16, 6))
    difference_subtotal_non_invoiced = fields.Float(string="Subtotal no facturado", readonly=True,digits=(16, 6))
    difference_iva_non_invoiced = fields.Float(string="IVA no facturado", readonly=True,digits=(16, 6))

    details = fields.Boolean(string='Ver detalles')
    use_date_range = fields.Boolean(string='Rango de fecha',default=False)
    
    def get_date_range(self):
        """Devuelve start_date y end_date según el modo activo."""
        user_tz = pytz.timezone(self.env.user.tz or 'America/Mexico_City')
        if self.use_date_range:
            if not self.date_from or not self.date_to:
                raise UserError("Debes seleccionar fecha inicio y fecha fin.")
            start_naive = datetime.combine(self.date_from, datetime.min.time())
            end_naive = datetime.combine(self.date_to, datetime.max.time().replace(microsecond=0))
        else:
            if not self.month or not self.year:
                raise UserError("Debes seleccionar mes y año.")
            year = int(self.year)
            month = int(self.month)
            last_day = calendar.monthrange(year, month)[1]
            start_naive = datetime(year, month, 1)
            end_naive = datetime(year, month, last_day, 23, 59, 59)
            
        start_date = user_tz.localize(start_naive).astimezone(pytz.utc).replace(tzinfo=None)
        end_date = user_tz.localize(end_naive).astimezone(pytz.utc).replace(tzinfo=None)
        return start_date, end_date

    def get_month_range(self):
        user_tz = pytz.timezone(self.env.user.tz or 'America/Mexico_City')
        year = int(self.year)
        month = int(self.month)
        last_day = calendar.monthrange(year, month)[1]
        start_naive = datetime(year, month, 1)
        end_naive = datetime(year, month, last_day, 23, 59, 59)
        
        start_date = user_tz.localize(start_naive).astimezone(pytz.utc).replace(tzinfo=None)
        end_date = user_tz.localize(end_naive).astimezone(pytz.utc).replace(tzinfo=None)
        return start_date, end_date

    def action_calculate_summary(self):
        """Calcula el resumen de tickets según mes y año"""
        start_date, end_date = self.get_date_range()
        print('sd: ', start_date)
        print('ed: ', end_date)

        tickets = self.env['contabilidad_kuale.ticket_monitor'].search([
            ('date', '>=', start_date),
            ('date', '<=', end_date),
            ('company_id', '=', self.company_id.id),
            ('branch_id', '=', self.branch_id.id),
        ])
        print('tickets: ', tickets)
        self.tickets_quantity = len(tickets)
        self.total_tickets = sum(tickets.mapped('total'))
        self.subtotal_tickets = sum(tickets.mapped('subtotal'))
        self.iva_tickets = sum(tickets.mapped('iva'))

        self.invoice_tickets_quantity = len(tickets.filtered(lambda t: t.invoiced))
        self.total_invoiced = sum(tickets.filtered(lambda t: t.invoiced).mapped('total'))
        self.subtotal_invoiced = sum(tickets.filtered(lambda t: t.invoiced).mapped('subtotal'))
        self.iva_invoiced = sum(tickets.filtered(lambda t: t.invoiced).mapped('iva'))

        self.non_invoiced_quantity = len(tickets.filtered(lambda t: not t.invoiced))
        self.total_non_invoiced = sum(tickets.filtered(lambda t: not t.invoiced).mapped('total'))
        self.subtotal_non_invoiced = sum(tickets.filtered(lambda t: not t.invoiced).mapped('subtotal'))
        self.iva_non_invoiced = sum(tickets.filtered(lambda t: not t.invoiced).mapped('iva'))

        summary = self.env['contabilidad_kuale.ticket_monitor_summary'].search([
            ('month', '=', self.month),
            ('year', '=', self.year),
            ('company_id', '=', self.company_id.id),
            ('branch_id', '=', self.branch_id.id),
        ], limit=1)

        self.system_tickets_quantity = summary.tickets_quantity
        self.system_total_tickets = summary.total_tickets
        self.system_subtotal_tickets = summary.subtotal_tickets
        self.system_iva_tickets = summary.iva_tickets

        self.system_invoice_tickets_quantity = summary.invoice_tickets_quantity
        self.system_total_invoiced = summary.total_invoiced
        self.system_subtotal_invoiced = summary.subtotal_invoiced
        self.system_iva_invoiced = summary.iva_invoiced

        self.system_non_invoiced_quantity = summary.non_invoiced_quantity
        self.system_total_non_invoiced = summary.total_non_invoiced
        self.system_subtotal_non_invoiced = summary.subtotal_non_invoiced
        self.system_iva_non_invoiced = summary.iva_non_invoiced

        # difference
        self.difference_tickets_quantity = self.system_tickets_quantity - self.tickets_quantity
        self.difference_total_tickets = self.system_total_tickets - self.total_tickets
        self.difference_subtotal_tickets = self.system_subtotal_tickets - self.subtotal_tickets
        self.difference_iva_tickets = self.system_iva_tickets - self.iva_tickets

        self.difference_invoice_tickets_quantity = self.system_invoice_tickets_quantity - self.invoice_tickets_quantity
        self.difference_total_invoiced = self.system_total_invoiced - self.total_invoiced
        self.difference_subtotal_invoiced = self.system_subtotal_invoiced - self.subtotal_invoiced
        self.difference_iva_invoiced = self.system_iva_invoiced - self.iva_invoiced

        self.difference_non_invoiced_quantity = self.system_non_invoiced_quantity - self.non_invoiced_quantity
        self.difference_total_non_invoiced = self.system_total_non_invoiced - self.total_non_invoiced
        self.difference_subtotal_non_invoiced = self.system_subtotal_non_invoiced - self.subtotal_non_invoiced
        self.difference_iva_non_invoiced = self.system_iva_non_invoiced - self.iva_non_invoiced

        return {
            'type': 'ir.actions.act_window',
            'name': 'Resumen de Tickets',
            'res_model': 'contabilidad_kuale.ticket_summary_wizard',
            'view_mode': 'form',
            'view_id': self.env.ref('contabilidad_kuale.view_ticket_summary_wizard_form').id,
            'target': 'new',
            'res_id': self.id,
        }

    def _get_digibox_token(self):
        """Función centralizada para obtener el token del PAC con Timeout."""
        try:
            # Configurar el timeout en 20 segundos
            session = requests.Session()
            transport = Transport(session=session, timeout=20)
            
            # URl del WSDL
            wsdl_url = 'https://timbrado.digibox.com.mx/Autenticacion/wsAutenticacion.asmx?WSDL'
            login_client = Client(wsdl=wsdl_url, transport=transport)
            
            # TODO: Idealmente, saca estas credenciales de self.company_id o de ir.config_parameter
            #usuario = "cfdi@grupokuale.com.mx"
            #password = "1?eFCeZ7LR8" 
            usuario = "pruebaskuale@digibox.com.mx"
            password = "123456789"  
            
            token = login_client.service.AutenticarBasico(usuario, password)
            
            if not token:
                raise UserError("El PAC no devolvió un token de autenticación válido.")
                
            return token
            
        except requests.exceptions.Timeout:
            raise UserError("El servicio del PAC (Digibox) tardó demasiado en responder. Intenta de nuevo más tarde.")
        except Exception as e:
            raise UserError(f"Error al conectar con el PAC para autenticación: {str(e)}")

    def action_timbrar_global(self):
        return self._generate_global_xml()


    def _timbrar(self, xml):
        try:
            print('autenticando...')
            # 1. Autenticación con Timeout
            session_auth = requests.Session()
            transport_auth = Transport(session=session_auth, timeout=20)
            #login = Client('https://timbrado.digibox.com.mx/Autenticacion/wsAutenticacion.asmx?WSDL', transport=transport_auth)
            #token = login.service.AutenticarBasico("cfdi@grupokuale.com.mx", "1?eFCeZ7LR8")
            login = Client('https://testtimbrado.digibox.com.mx/Autenticacion/wsAutenticacion.asmx?wsdl', transport=transport_auth)
            token = login.service.AutenticarBasico("pruebaskuale@digibox.com.mx", "123456789")
            if not token:
                raise UserError("Error: No se recibió token de autenticación del PAC")
                
            print('timbrando...')
            # 2. Timbrado con Timeout (le damos 30s porque el XML global puede pesar)
            session_timb = requests.Session()
            transport_timb = Transport(session=session_timb, timeout=180)
            #timbrar = Client('https://sellado.digibox.com.mx/Timbrado.svc?singleWsdl', transport=transport_timb)
            timbrar = Client('https://testtimbrado.digibox.com.mx/Digibox.ServiciosSellado/Timbrado.svc?Wsdl', transport=transport_timb)

            #timbrar.service._binding_options['address'] = 'https://sellado.digibox.com.mx/Timbrado.svc'
            timbrar.service._binding_options['address'] = 'https://testtimbrado.digibox.com.mx/Digibox.ServiciosSellado/Timbrado.svc'
            
            xml_timbrado = timbrar.service.TimbrarXmlV2(xml, token)
            print('timbrado')
            
            if not xml_timbrado:
                print('no timbrado')
                return False
                
            print("Procesando respuesta del timbrado...")
            xml_dict = xmltodict.parse(xml_timbrado)
            print('xml_timbrado : \n', xml_timbrado)
            return xml_timbrado
            
        except requests.exceptions.Timeout:
            # Si hay timeout a nivel HTTP, el PAC lo está procesando
            return 'EN_PROCESO'
        except Exception as e:
            error_msg = str(e)
            # Interceptamos el mensaje de la cola Redis
            if "procesará en segundo plano" in error_msg or "aceptado" in error_msg.lower():
                return 'EN_PROCESO'
            raise UserError(f'Error con el servicio de timbrado: {error_msg}')

    def _generate_pdf(self, xml):
        print('cid: ', self.company_id.id)
        company_id = self.company_id.id if self.company_id else None

        logo_base64 = ""
        if self.company_id.client_invoice_logo:
            logo_base64 = self.company_id.client_invoice_logo.decode() if isinstance(
                self.company_id.client_invoice_logo, bytes) else self.company_id.client_invoice_logo
        else:
            print("Advertencia: La empresa no tiene configurado el logo de facturación.")

        try:
            xml_dict = xmltodict.parse(xml)
            uuid = xml_dict.get('cfdi:Comprobante', {}).get('cfdi:Complemento', {}).get('tfd:TimbreFiscalDigital',
                                                                                        {}).get('@UUID', '')

            if not uuid:
                print("Error: No se encontró UUID en el XML")
                return {'status': 'error', 'message': 'No se encontró UUID en el XML'}

            # Generar el QR
            qr_data = f"https://verificacfdi.facturaelectronica.sat.gob.mx/default.aspx?id={uuid}"
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=0,
            )
            qr.add_data(qr_data)
            qr.make(fit=True)

            img = qr.make_image(fill_color="black", back_color="white")

            # Convertir la imagen QR a base64
            buffered = BytesIO()
            img.save(buffered, format="PNG")
            qr_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

            # Extraer datos del XML
            invoice_data = xml_dict.get('cfdi:Comprobante', {})
            emisor = invoice_data.get('cfdi:Emisor', {})
            receptor = invoice_data.get('cfdi:Receptor', {})
            conceptos = invoice_data.get('cfdi:Conceptos', {}).get('cfdi:Concepto', [])
            impuestos = invoice_data.get('cfdi:Impuestos', {})
            total_impuestos_trasladados = impuestos.get('@TotalImpuestosTrasladados', 'No disponible')

            if not isinstance(conceptos, list):
                conceptos = [conceptos]

            # Obtener el importe total del XML
            total_str = invoice_data.get('@Total', '0.00')  # Si no encuentra el total, usa 0.00
            total_float = float(total_str)  # Convertimos a flotante

            # Convertir el total a letras en formato "Mil pesos 50/100 M.N."
            total_entero = int(total_float)
            centavos = int(round((total_float - total_entero) * 100))  # Extrae los centavos
            total_letras = f"{num2words(total_entero, lang='es').capitalize()} pesos {centavos:02d}/100 M.N."

            # Extraer y mapear claves
            forma_pago_clave = invoice_data.get('@FormaPago', '')
            forma_pago_obj = self.env['cfdi.claveformadepago'].search([('Clave_forma_de_pago', '=', forma_pago_clave)],
                                                                      limit=1)
            descripcion_forma_pago = forma_pago_obj.Descripcion if forma_pago_obj else 'No encontrada'

            metodo_pago_clave = invoice_data.get('@MetodoPago', '')
            metodo_pago_obj = self.env['cfdi.clavemetododepago'].search(
                [('Clave_metodo_de_pago', '=', metodo_pago_clave)], limit=1)
            descripcion_metodo_pago = metodo_pago_obj.Descripcion if metodo_pago_obj else 'No encontrado'

            regimen_fiscal_clave_emisor = emisor.get('@RegimenFiscal', '')
            regimen_fiscal_obj_emisor = self.env['cfdi.claveregimenfiscal'].search(
                [('Clave_regimenFiscal', '=', regimen_fiscal_clave_emisor)], limit=1)
            descripcion_regimen_fiscal_emisor = regimen_fiscal_obj_emisor.Descripcion if regimen_fiscal_obj_emisor else 'No encontrado'

            regimen_fiscal_clave_receptor = receptor.get('@RegimenFiscalReceptor', '')
            regimen_fiscal_obj_receptor = self.env['cfdi.claveregimenfiscal'].search(
                [('Clave_regimenFiscal', '=', regimen_fiscal_clave_receptor)], limit=1)
            descripcion_regimen_fiscal_receptor = regimen_fiscal_obj_receptor.Descripcion if regimen_fiscal_obj_receptor else 'No encontrado'

            uso_cfdi_clave = receptor.get('@UsoCFDI', '')
            uso_cfdi_obj = self.env['cfdi.claveusocfdi'].search([('Clave_UsoCFDI', '=', uso_cfdi_clave)], limit=1)
            descripcion_uso_cfdi = uso_cfdi_obj.Descripcion if uso_cfdi_obj else 'No encontrado'

            clave_moneda = invoice_data.get('@Moneda', '')
            moneda_obj = self.env['cfdi.clavemoneda'].search([('Clave_moneda', '=', clave_moneda)], limit=1)
            descripcion_moneda = moneda_obj.Descripcion if moneda_obj else 'No encontrado'

            conceptos_procesados = []
            for concepto in conceptos:
                clave_objetoimp = concepto.get('@ObjetoImp', '')
                objeto_imp = self.env['cfdi.claveobjetoimp'].search([('Clave_objetoimp', '=', clave_objetoimp)],
                                                                    limit=1)
                descripcion_objetoimp = objeto_imp.Descripcion if objeto_imp else 'No encontrado'

                clave_impuesto = concepto.get('cfdi:Impuestos', {}).get('cfdi:Traslados', {}).get('cfdi:Traslado',
                                                                                                  {}).get('@Impuesto',
                                                                                                          '')
                impuesto = self.env['cfdi.claveimpuesto'].search([('Clave_impuesto', '=', clave_impuesto)], limit=1)
                descripcion_impuesto = impuesto.Descripcion if impuesto else 'No encontrado'

                concepto['descripcion_objetoimp'] = descripcion_objetoimp
                concepto['descripcion_impuesto'] = descripcion_impuesto

                conceptos_procesados.append(concepto)

            # Generar el PDF con QWeb
            print("Renderizando PDF con QWeb...")
            report_ref = self.env.ref('contabilidad_kuale.report_invoice')

            # Pasar datos al contexto, incluyendo el logo en base64 y el importe en letras
            pdf_content, _ = report_ref._render_qweb_pdf(report_ref.id, data={
                'factura': self,
                'invoice_data': invoice_data,
                'emisor': emisor,
                'receptor': receptor,
                'conceptos': conceptos_procesados,
                'company_id': int(self.company_id.client_invoice_color),
                'logo_base64': logo_base64,
                'qr_base64': qr_base64,
                'total_letras': total_letras,
                'total_impuestos_trasladados': total_impuestos_trasladados,
                'descripcion_forma_pago': descripcion_forma_pago,
                'descripcion_metodo_pago': descripcion_metodo_pago,
                'descripcion_regimen_fiscal_emisor': descripcion_regimen_fiscal_emisor,
                'descripcion_regimen_fiscal_receptor': descripcion_regimen_fiscal_receptor,
                'descripcion_uso_cfdi': descripcion_uso_cfdi,
                'descripcion_moneda': descripcion_moneda,
                'descripcion_objetoimp': descripcion_objetoimp,
                'descripcion_impuesto': descripcion_impuesto,
            })

            if not pdf_content:
                print("Error: No se generó contenido PDF")
                return False

            # Codificar PDF en base64
            pdf_base64 = base64.b64encode(pdf_content)
            print('pdf creado')
            return pdf_base64
        except Exception as e:
            raise UserError(f"Error en la generación del PDF: {str(e)}")

    def _generate_global_xml(self):
        print('Generating Global XML')

        # Obtener el rango de fechas del mes
        start_date, end_date = self.get_date_range()
        print('Start Date:', start_date, 'End Date:', end_date)

        # Buscar tickets no facturados dentro del rango de fechas
        tickets = self.env['contabilidad_kuale.ticket_monitor'].search([
            ('date', '>=', start_date),
            ('date', '<=', end_date),
            ('company_id', '=', self.company_id.id),
            ('branch_id', '=', self.branch_id.id),
            ('invoiced', '=', False),
        ])

        if not tickets:
            raise UserError(f"No se encontraron tickets sin facturar para {self.company_id.name}.")

        matriz = self.company_id
        company = self.branch_id


        # Datos generales
        tz_mexico = pytz.timezone('America/Mexico_City')
        fecha_emision = datetime.now(tz_mexico).strftime('%Y-%m-%dT%H:%M:%S')
        serie = company.global_serial_number or "FG"
        folio = company.global_folio_number or "000001"
        folio = str(folio).zfill(4)
        lugar_expedicion = company.zip
        exportacion = "01"

        # Obtener el ticket con mayor monto para determinar la forma de pago
        highest_ticket = max(tickets, key=lambda t: t.total, default=None)
        forma_pago = highest_ticket.payment_type.Clave_forma_de_pago if highest_ticket and highest_ticket.payment_type else "01"  # Default: Efectivo

        # Datos del emisor
        rfc_emisor = company.rfc
        nombre_emisor = cfdi_escape(company.business_name)
        regimen_fiscal = company.regimen_fiscal.Clave_regimenFiscal

        # Datos del receptor (Público en general)
        rfc_receptor = "XAXX010101000"
        nombre_receptor = "PUBLICO EN GENERAL"
        domicilio_fiscal_receptor = company.zip
        regimen_fiscal_receptor = "616"  # Régimen sin obligaciones fiscales
        uso_cfdi = "S01"  # Sin efectos fiscales

        # Configuración de periodicidad
        periodicidad = "04"  # Mensual
        mes = start_date.strftime('%m')
        anio = start_date.strftime('%Y')

        # Variables de cálculo
        subtotal = 0.0
        total_iva = 0.0
        total_descuento = 0.0
        conceptos_xml = ""

        for ticket in tickets:
            total_amount = sum(line.unit_price * line.quantity for line in ticket.product_line)
            total_discount = sum(line.discount for line in ticket.product_line if line.discount > 0)
            
            total_amount_rounded = round(total_amount, 2)
            total_discount_rounded = round(total_discount, 2)
            
            base_iva = total_amount_rounded - total_discount_rounded
            importe_iva_rounded = round(base_iva * 0.16, 2)

            subtotal += total_amount_rounded
            total_iva += importe_iva_rounded
            total_descuento += total_discount_rounded

            concepto_descuento = f' Descuento="{total_discount_rounded:.2f}"' if total_discount_rounded > 0 else ""

            conceptos_xml += f'''
                <cfdi:Concepto ClaveProdServ="01010101" ClaveUnidad="ACT" Cantidad="1.00" NoIdentificacion="{cfdi_escape(ticket.ticket_folio)}" 
                Descripcion="Venta" ValorUnitario="{total_amount_rounded:.2f}" Importe="{total_amount_rounded:.2f}" {concepto_descuento} ObjetoImp="02">
                    <cfdi:Impuestos>
                        <cfdi:Traslados>
                            <cfdi:Traslado Base="{base_iva:.2f}" Impuesto="002" TipoFactor="Tasa" 
                            TasaOCuota="0.160000" Importe="{importe_iva_rounded:.2f}"/>
                        </cfdi:Traslados>
                    </cfdi:Impuestos>
                </cfdi:Concepto>
            '''
        if total_descuento > 0:
            total = (subtotal - total_descuento) + total_iva
            descuento_attr = f' Descuento="{round(total_descuento, 2):.2f}"'
        else:
            total = subtotal + total_iva
            descuento_attr = ""

        xml = f'''
        <cfdi:Comprobante Version="4.0" Serie="{serie}" Folio="{folio}" Fecha="{fecha_emision}" SubTotal="{subtotal:.2f}" Total="{total:.2f}" 
        Moneda="MXN" TipoDeComprobante="I" LugarExpedicion="{lugar_expedicion}" Exportacion="{exportacion}" {descuento_attr} FormaPago="{forma_pago}" MetodoPago="PUE"
        xmlns:cfdi="http://www.sat.gob.mx/cfd/4" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
        xsi:schemaLocation="http://www.sat.gob.mx/cfd/4 http://www.sat.gob.mx/sitio_internet/cfd/4/cfdv40.xsd">
            <cfdi:InformacionGlobal Periodicidad="{periodicidad}" Meses="{mes}" Año="{anio}"/>
            <cfdi:Emisor Rfc="{rfc_emisor}" Nombre="{nombre_emisor}" RegimenFiscal="{regimen_fiscal}"/>
            <cfdi:Receptor Rfc="{rfc_receptor}" Nombre="{nombre_receptor}" DomicilioFiscalReceptor="{domicilio_fiscal_receptor}"
            RegimenFiscalReceptor="{regimen_fiscal_receptor}" UsoCFDI="{uso_cfdi}"/>
            <cfdi:Conceptos>
                {conceptos_xml}
            </cfdi:Conceptos>
            <cfdi:Impuestos TotalImpuestosTrasladados="{total_iva:.2f}">
                <cfdi:Traslados>
                    <cfdi:Traslado Base="{(subtotal - total_descuento):.2f}" Impuesto="002" TipoFactor="Tasa" 
                    TasaOCuota="0.160000" Importe="{total_iva:.2f}"/>
                </cfdi:Traslados>
            </cfdi:Impuestos>
        </cfdi:Comprobante>
        '''

        print("XML: ", xml)
        print('-------------------------')
        print('Caracateres del xml: ', len(xml))
        print('Bytes del xml: ', len(xml.encode('utf-8')))
        print('kilobytes del xml: ', len(xml.encode('utf-8')) / 1024)
        print('-------------------------')
        
        xml_timbrado = self._timbrar(xml)
        
        print('-------------------------')
        print('Caracteres del XML Timbrado: ', len(xml_timbrado))
        print('Bytes del XML Timbrado: ', len(xml_timbrado.encode('utf-8')))
        print('kilobytes del XML Timbrado: ', len(xml_timbrado.encode('utf-8')) / 1024)
        print('-------------------------')
        
        if xml_timbrado == 'EN_PROCESO':
            self.env['contabilidad_kuale.ticket_monitor_summary_history'].create({
                'company_id': self.company_id.id,
                'branch_id': self.branch_id.id,
                'month': self.month,
                'year': self.year,

                'tickets_quantity': self.tickets_quantity,
                'total_tickets': self.total_tickets,
                'subtotal_tickets': self.subtotal_tickets,
                'iva_tickets': self.iva_tickets,
                'invoice_tickets_quantity': self.invoice_tickets_quantity,
                'total_invoiced': self.total_invoiced,
                'subtotal_invoiced': self.subtotal_invoiced,
                'iva_invoiced': self.iva_invoiced,
                'non_invoiced_quantity': self.non_invoiced_quantity,
                'total_non_invoiced': self.total_non_invoiced,
                'subtotal_non_invoiced': self.subtotal_non_invoiced,
                'iva_non_invoiced': self.iva_non_invoiced,

                'system_tickets_quantity': self.system_tickets_quantity,
                'system_total_tickets': self.system_total_tickets,
                'system_subtotal_tickets': self.system_subtotal_tickets,
                'system_iva_tickets': self.system_iva_tickets,
                'system_invoice_tickets_quantity': self.system_invoice_tickets_quantity,
                'system_total_invoiced': self.system_total_invoiced,
                'system_subtotal_invoiced': self.system_subtotal_invoiced,
                'system_iva_invoiced': self.system_iva_invoiced,
                'system_non_invoiced_quantity': self.system_non_invoiced_quantity,
                'system_total_non_invoiced': self.system_total_non_invoiced,
                'system_subtotal_non_invoiced': self.system_subtotal_non_invoiced,
                'system_iva_non_invoiced': self.system_iva_non_invoiced,

                'difference_tickets_quantity': self.difference_tickets_quantity,
                'difference_total_tickets': self.difference_total_tickets,
                'difference_subtotal_tickets': self.difference_subtotal_tickets,
                'difference_iva_tickets': self.difference_iva_tickets,
                'difference_invoice_tickets_quantity': self.difference_invoice_tickets_quantity,
                'difference_total_invoiced': self.difference_total_invoiced,
                'difference_subtotal_invoiced': self.difference_subtotal_invoiced,
                'difference_iva_invoiced': self.difference_iva_invoiced,
                'difference_non_invoiced_quantity': self.difference_non_invoiced_quantity,
                'difference_total_non_invoiced': self.difference_total_non_invoiced,
                'difference_subtotal_non_invoiced': self.difference_subtotal_non_invoiced,
                'difference_iva_non_invoiced': self.difference_iva_non_invoiced,

                'estado_timbrado': 'en_proceso',
                'xml_enviado': xml, # MUY IMPORTANTE: Se guarda el string exacto para el caché de Redis
                'uuid': 'Procesando...',
                'serie': serie,
                'folio': folio,
                'fecha_timbrado': fields.Datetime.now(pytz.timezone('America/Mexico_City')),
                'total': total,
                'subtotal': subtotal,
                'iva': total_iva,
                'ticket_count': len(tickets),
            })
            
            # Marcar tickets como en proceso global
            for ticket in tickets:
                ticket.write({
                    'invoiced': True,
                    'invoiced_type': 'global',
                    'ticket_status': 'global'
                })
            self.branch_id.write({'global_folio_number': (self.branch_id.global_folio_number or 1) + 1})
            
            # Puedes retornar un mensaje en lugar de levantar un UserError
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Procesamiento en Segundo Plano',
                    'message': 'El documento masivo fue puesto en la cola de procesamiento del PAC. Se finalizará en unos minutos.',
                    'type': 'warning',
                    'sticky': True,
                }
            }

        # --- LÓGICA ORIGINAL SI EL TIMBRADO FUE INMEDIATO ---
        elif xml_timbrado:
            pdf = self._generate_pdf(xml_timbrado)
            uuid = xmltodict.parse(xml_timbrado).get('cfdi:Comprobante', {}).get('cfdi:Complemento', {}).get(
                'tfd:TimbreFiscalDigital', {}).get('@UUID', '')
            self.env['contabilidad_kuale.ticket_monitor_summary_history'].create({
                'company_id': self.company_id.id,
                'branch_id': self.branch_id.id,
                'month': self.month,
                'year': self.year,

                'tickets_quantity': self.tickets_quantity,
                'total_tickets': self.total_tickets,
                'subtotal_tickets': self.subtotal_tickets,
                'iva_tickets': self.iva_tickets,
                'invoice_tickets_quantity': self.invoice_tickets_quantity,
                'total_invoiced': self.total_invoiced,
                'subtotal_invoiced': self.subtotal_invoiced,
                'iva_invoiced': self.iva_invoiced,
                'non_invoiced_quantity': self.non_invoiced_quantity,
                'total_non_invoiced': self.total_non_invoiced,
                'subtotal_non_invoiced': self.subtotal_non_invoiced,
                'iva_non_invoiced': self.iva_non_invoiced,

                'system_tickets_quantity': self.system_tickets_quantity,
                'system_total_tickets': self.system_total_tickets,
                'system_subtotal_tickets': self.system_subtotal_tickets,
                'system_iva_tickets': self.system_iva_tickets,
                'system_invoice_tickets_quantity': self.system_invoice_tickets_quantity,
                'system_total_invoiced': self.system_total_invoiced,
                'system_subtotal_invoiced': self.system_subtotal_invoiced,
                'system_iva_invoiced': self.system_iva_invoiced,
                'system_non_invoiced_quantity': self.system_non_invoiced_quantity,
                'system_total_non_invoiced': self.system_total_non_invoiced,
                'system_subtotal_non_invoiced': self.system_subtotal_non_invoiced,
                'system_iva_non_invoiced': self.system_iva_non_invoiced,

                'difference_tickets_quantity': self.difference_tickets_quantity,
                'difference_total_tickets': self.difference_total_tickets,
                'difference_subtotal_tickets': self.difference_subtotal_tickets,
                'difference_iva_tickets': self.difference_iva_tickets,
                'difference_invoice_tickets_quantity': self.difference_invoice_tickets_quantity,
                'difference_total_invoiced': self.difference_total_invoiced,
                'difference_subtotal_invoiced': self.difference_subtotal_invoiced,
                'difference_iva_invoiced': self.difference_iva_invoiced,
                'difference_non_invoiced_quantity': self.difference_non_invoiced_quantity,
                'difference_total_non_invoiced': self.difference_total_non_invoiced,
                'difference_subtotal_non_invoiced': self.difference_subtotal_non_invoiced,
                'difference_iva_non_invoiced': self.difference_iva_non_invoiced,

                'uuid': uuid,
                'serie': serie,
                'folio': folio,
                'fecha_timbrado': fields.Datetime.now(pytz.timezone('America/Mexico_City')),
                'xml_timbrado': base64.b64encode(xml_timbrado.encode()).decode(),
                'pdf': pdf,
                'total': total,
                'subtotal': subtotal,
                'iva': total_iva,
                'ticket_count': len(tickets),
            })
            for ticket in tickets:
                ticket.write({
                    'invoiced': True,
                    'invoiced_type': 'global',
                    'ticket_status': 'global'
                })
            self.branch_id.write({'global_folio_number': (self.branch_id.global_folio_number or 1) + 1})
            print('timbrado')
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Facturación Exitosa',
                    'message': 'El documento masivo fue timbrado con éxito.',
                    'type': 'success',
                    'sticky': False,
                }
            }

        return xml

class TicketMonitorSummaryHistory(models.Model):
    _name = 'contabilidad_kuale.ticket_monitor_summary_history'
    _description = 'Historial de facturas globales'

    company_id = fields.Many2one('res.company', string="Compañía", required=True)
    branch_id = fields.Many2one('res.company', string="Sucursal", required=True)
    month = fields.Selection(
        [(str(i), datetime(2000, i, 1).strftime('%B')) for i in range(1, 13)],
        string="Mes", required=True
    )
    year = fields.Selection(
        [(str(y), str(y)) for y in range(2020, datetime.now().year + 1)],
        string="Año", required=True
    )

    # summary
    tickets_quantity = fields.Integer(string="Numero total de tickets")
    total_tickets = fields.Float(string="Total",digits=(16, 6))
    subtotal_tickets = fields.Float(string="Subtotal",digits=(16, 6))
    iva_tickets = fields.Float(string="IVA",digits=(16, 6))

    invoice_tickets_quantity = fields.Integer(string='Numero total de tickets facturados')
    total_invoiced = fields.Float(string="Total facturado",digits=(16, 6))
    subtotal_invoiced = fields.Float(string="Subtotal facturado",digits=(16, 6))
    iva_invoiced = fields.Float(string="IVA Facturado",digits=(16, 6))

    non_invoiced_quantity = fields.Integer('Numero total de tickets no facturados')
    total_non_invoiced = fields.Float(string="Total no facturado",digits=(16, 6))
    subtotal_non_invoiced = fields.Float(string="Subtotal no facturado",digits=(16, 6))
    iva_non_invoiced = fields.Float(string="IVA no facturado",digits=(16, 6))

    # system
    system_tickets_quantity = fields.Integer(string="Numero total de tickets")
    system_total_tickets = fields.Float(string="Total",digits=(16, 6))
    system_subtotal_tickets = fields.Float(string="Subtotal",digits=(16, 6))
    system_iva_tickets = fields.Float(string="IVA",digits=(16, 6))

    system_invoice_tickets_quantity = fields.Integer(string='Numero total de tickets facturados')
    system_total_invoiced = fields.Float(string="Total facturado",digits=(16, 6))
    system_subtotal_invoiced = fields.Float(string="Subtotal facturado",digits=(16, 6))
    system_iva_invoiced = fields.Float(string="IVA Facturado",digits=(16, 6))

    system_non_invoiced_quantity = fields.Integer('Numero total de tickets no facturados')
    system_total_non_invoiced = fields.Float(string="Total no facturado",digits=(16, 6))
    system_subtotal_non_invoiced = fields.Float(string="Subtotal no facturado",digits=(16, 6))
    system_iva_non_invoiced = fields.Float(string="IVA no facturado",digits=(16, 6))
    # Difference
    difference_tickets_quantity = fields.Integer(string="Numero total de tickets")
    difference_total_tickets = fields.Float(string="Total",digits=(16, 6))
    difference_subtotal_tickets = fields.Float(string="Subtotal",digits=(16, 6))
    difference_iva_tickets = fields.Float(string="IVA",digits=(16, 6))

    difference_invoice_tickets_quantity = fields.Integer(string='Numero total de tickets facturados')
    difference_total_invoiced = fields.Float(string="Total facturado",digits=(16, 6))
    difference_subtotal_invoiced = fields.Float(string="Subtotal facturado",digits=(16, 6))
    difference_iva_invoiced = fields.Float(string="IVA Facturado",digits=(16, 6))

    difference_non_invoiced_quantity = fields.Integer('Numero total de tickets no facturados')
    difference_total_non_invoiced = fields.Float(string="Total no facturado",digits=(16, 6))
    difference_subtotal_non_invoiced = fields.Float(string="Subtotal no facturado",digits=(16, 6))
    difference_iva_non_invoiced = fields.Float(string="IVA no facturado",digits=(16, 6))

    # Invoice details
    estado_timbrado = fields.Selection([
        ('en_proceso', 'Procesando en el PAC'),
        ('timbrado', 'Timbrado'),
        ('error', 'Error')
    ], string='Estado de Timbrado', default='timbrado')
    
    xml_enviado = fields.Text(string="XML Enviado al PAC (Pendiente)")
    
    uuid = fields.Char(string="UUID", required=False)
    folio = fields.Char(string="Folio")
    serie = fields.Char(string="Serie")
    fecha_timbrado = fields.Datetime(string="Fecha de Timbrado")
    xml_timbrado = fields.Binary(string="XML Timbrado")
    pdf = fields.Binary(string="PDF Factura")
    total = fields.Float(string="Total Facturado",digits=(16, 6))
    subtotal = fields.Float(string="Subtotal",digits=(16, 6))
    iva = fields.Float(string="IVA Total",digits=(16, 6))
    ticket_count = fields.Integer(string="Número de Tickets",digits=(16, 6))

    @api.model
    def cron_procesar_facturas_asincronas(self):
        """
        Método ejecutado por el Cron para verificar las facturas en caché de Redis del PAC.
        """
        records = self.search([('estado_timbrado', '=', 'en_proceso')])
        if not records:
            return

        for rec in records:
            try:
                # 1. Autenticación
                session_auth = requests.Session()
                transport_auth = Transport(session=session_auth, timeout=20)
                # --- TEST ---
                login = Client('https://testtimbrado.digibox.com.mx/Autenticacion/wsAutenticacion.asmx?wsdl', transport=transport_auth)
                token = login.service.AutenticarBasico("pruebaskuale@digibox.com.mx", "123456789")
                # --- PRODUCCIÓN (descomentar para producción) ---
                #login = Client('https://timbrado.digibox.com.mx/Autenticacion/wsAutenticacion.asmx?WSDL', transport=transport_auth)
                #token = login.service.AutenticarBasico("cfdi@grupokuale.com.mx", "1?eFCeZ7LR8")
                
                # 2. Re-envío del mismo XML a la caché
                session_timb = requests.Session()
                transport_timb = Transport(session=session_timb, timeout=60)
                # --- TEST ---
                timbrar = Client('https://testtimbrado.digibox.com.mx/Digibox.ServiciosSellado/Timbrado.svc?Wsdl', transport=transport_timb)
                timbrar.service._binding_options['address'] = 'https://testtimbrado.digibox.com.mx/Digibox.ServiciosSellado/Timbrado.svc'
                # --- PRODUCCIÓN (descomentar para producción) ---
                #timbrar = Client('https://sellado.digibox.com.mx/Timbrado.svc?singleWsdl', transport=transport_timb)
                #timbrar.service._binding_options['address'] = 'https://sellado.digibox.com.mx/Timbrado.svc'
                
                # Se envía exactamente el mismo string almacenado previamente
                xml_timbrado = timbrar.service.TimbrarXmlV2(rec.xml_enviado, token)
                
                if xml_timbrado:
                    print(f'[Cron Async] XML timbrado recibido para registro {rec.id}')
                    # El PAC finalizó y devolvió el XML
                    xml_dict = xmltodict.parse(xml_timbrado)
                    uuid = xml_dict.get('cfdi:Comprobante', {}).get('cfdi:Complemento', {}).get('tfd:TimbreFiscalDigital', {}).get('@UUID', '')
                    
                    # Generar PDF
                    pdf_b64 = rec._generate_pdf_from_history(xml_timbrado) 
                    
                    update_vals = {
                        'estado_timbrado': 'timbrado',
                        'xml_timbrado': base64.b64encode(xml_timbrado.encode()).decode(),
                        'xml_enviado': False, # Limpiar XML temporal una vez timbrado
                        'uuid': uuid,
                    }
                    if pdf_b64:
                        update_vals['pdf'] = pdf_b64
                        print(f'[Cron Async] PDF generado correctamente para registro {rec.id}')
                    else:
                        print(f'[Cron Async] ADVERTENCIA: No se pudo generar PDF para registro {rec.id}')
                    
                    rec.write(update_vals)
                    
                    # Commit para asegurar que si falla el siguiente registro, este se guarde
                    self.env.cr.commit()
                else:
                    print(f'[Cron Async] El PAC no devolvió XML para registro {rec.id}, reintentando en próxima ejecución')

            except Exception as e:
                error_msg = str(e)
                print(f'[Cron Async] Excepción para registro {rec.id}: {error_msg}')
                # Si sigue en proceso, se ignora y el cron volverá a intentar en la próxima ejecución
                if "procesará en segundo plano" in error_msg or "aceptado" in error_msg.lower():
                    continue
                else:
                    # Si hubo un error real de estructura de datos (RFC inválido, montos descuadrados, etc.)
                    rec.write({'estado_timbrado': 'error'})
                    self.env.cr.commit()


    def _generate_pdf_from_history(self, xml):
        self.ensure_one()
        print('Generando PDF desde el Cron (Asíncrono)...')

        logo_base64 = ""
        if self.company_id.client_invoice_logo:
            logo_base64 = self.company_id.client_invoice_logo.decode() if isinstance(
                self.company_id.client_invoice_logo, bytes) else self.company_id.client_invoice_logo

        try:
            xml_dict = xmltodict.parse(xml)
            uuid = xml_dict.get('cfdi:Comprobante', {}).get('cfdi:Complemento', {}).get('tfd:TimbreFiscalDigital', {}).get('@UUID', '')

            if not uuid:
                print("Error: No se encontró UUID en el XML")
                return False

            # Generar el QR
            qr_data = f"https://verificacfdi.facturaelectronica.sat.gob.mx/default.aspx?id={uuid}"
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=0,
            )
            qr.add_data(qr_data)
            qr.make(fit=True)

            img = qr.make_image(fill_color="black", back_color="white")

            # Convertir la imagen QR a base64
            buffered = BytesIO()
            img.save(buffered, format="PNG")
            qr_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

            # Extraer datos del XML
            invoice_data = xml_dict.get('cfdi:Comprobante', {})
            emisor = invoice_data.get('cfdi:Emisor', {})
            receptor = invoice_data.get('cfdi:Receptor', {})
            conceptos = invoice_data.get('cfdi:Conceptos', {}).get('cfdi:Concepto', [])
            impuestos = invoice_data.get('cfdi:Impuestos', {})
            total_impuestos_trasladados = impuestos.get('@TotalImpuestosTrasladados', 'No disponible')

            if not isinstance(conceptos, list):
                conceptos = [conceptos]

            # Obtener el importe total del XML
            total_str = invoice_data.get('@Total', '0.00')
            total_float = float(total_str)

            # Convertir el total a letras
            total_entero = int(total_float)
            centavos = int(round((total_float - total_entero) * 100))
            total_letras = f"{num2words(total_entero, lang='es').capitalize()} pesos {centavos:02d}/100 M.N."

            # Extraer y mapear claves
            forma_pago_clave = invoice_data.get('@FormaPago', '')
            forma_pago_obj = self.env['cfdi.claveformadepago'].search([('Clave_forma_de_pago', '=', forma_pago_clave)], limit=1)
            descripcion_forma_pago = forma_pago_obj.Descripcion if forma_pago_obj else 'No encontrada'

            metodo_pago_clave = invoice_data.get('@MetodoPago', '')
            metodo_pago_obj = self.env['cfdi.clavemetododepago'].search([('Clave_metodo_de_pago', '=', metodo_pago_clave)], limit=1)
            descripcion_metodo_pago = metodo_pago_obj.Descripcion if metodo_pago_obj else 'No encontrado'

            regimen_fiscal_clave_emisor = emisor.get('@RegimenFiscal', '')
            regimen_fiscal_obj_emisor = self.env['cfdi.claveregimenfiscal'].search([('Clave_regimenFiscal', '=', regimen_fiscal_clave_emisor)], limit=1)
            descripcion_regimen_fiscal_emisor = regimen_fiscal_obj_emisor.Descripcion if regimen_fiscal_obj_emisor else 'No encontrado'

            regimen_fiscal_clave_receptor = receptor.get('@RegimenFiscalReceptor', '')
            regimen_fiscal_obj_receptor = self.env['cfdi.claveregimenfiscal'].search([('Clave_regimenFiscal', '=', regimen_fiscal_clave_receptor)], limit=1)
            descripcion_regimen_fiscal_receptor = regimen_fiscal_obj_receptor.Descripcion if regimen_fiscal_obj_receptor else 'No encontrado'

            uso_cfdi_clave = receptor.get('@UsoCFDI', '')
            uso_cfdi_obj = self.env['cfdi.claveusocfdi'].search([('Clave_UsoCFDI', '=', uso_cfdi_clave)], limit=1)
            descripcion_uso_cfdi = uso_cfdi_obj.Descripcion if uso_cfdi_obj else 'No encontrado'

            clave_moneda = invoice_data.get('@Moneda', '')
            moneda_obj = self.env['cfdi.clavemoneda'].search([('Clave_moneda', '=', clave_moneda)], limit=1)
            descripcion_moneda = moneda_obj.Descripcion if moneda_obj else 'No encontrado'

            conceptos_procesados = []
            for concepto in conceptos:
                clave_objetoimp = concepto.get('@ObjetoImp', '')
                objeto_imp = self.env['cfdi.claveobjetoimp'].search([('Clave_objetoimp', '=', clave_objetoimp)], limit=1)
                descripcion_objetoimp = objeto_imp.Descripcion if objeto_imp else 'No encontrado'

                clave_impuesto = concepto.get('cfdi:Impuestos', {}).get('cfdi:Traslados', {}).get('cfdi:Traslado', {}).get('@Impuesto', '')
                impuesto = self.env['cfdi.claveimpuesto'].search([('Clave_impuesto', '=', clave_impuesto)], limit=1)
                descripcion_impuesto = impuesto.Descripcion if impuesto else 'No encontrado'

                concepto['descripcion_objetoimp'] = descripcion_objetoimp
                concepto['descripcion_impuesto'] = descripcion_impuesto
                conceptos_procesados.append(concepto)

            # Generar el PDF con QWeb
            report_ref = self.env.ref('contabilidad_kuale.report_invoice')
            
            # Validamos el color por si viene vacío
            invoice_color = self.company_id.client_invoice_color
            company_color_int = int(invoice_color) if invoice_color and invoice_color.isdigit() else 1

            # Calcular descuento desde el XML (la plantilla espera la variable 'descuento')
            descuento_xml = invoice_data.get('@Descuento', '0.00')

            pdf_content, _ = report_ref._render_qweb_pdf(report_ref.id, data={
                'factura': None, # No aplica para factura global desde cron (la plantilla no usa este campo)
                'invoice_data': invoice_data,
                'emisor': emisor,
                'receptor': receptor,
                'conceptos': conceptos_procesados,
                'company_id': company_color_int,
                'logo_base64': logo_base64,
                'qr_base64': qr_base64,
                'total_letras': total_letras,
                'total_impuestos_trasladados': total_impuestos_trasladados,
                'descripcion_forma_pago': descripcion_forma_pago,
                'descripcion_metodo_pago': descripcion_metodo_pago,
                'descripcion_regimen_fiscal_emisor': descripcion_regimen_fiscal_emisor,
                'descripcion_regimen_fiscal_receptor': descripcion_regimen_fiscal_receptor,
                'descripcion_uso_cfdi': descripcion_uso_cfdi,
                'descripcion_moneda': descripcion_moneda,
                'descripcion_objetoimp': descripcion_objetoimp,
                'descripcion_impuesto': descripcion_impuesto,
                'descuento': descuento_xml,
                'complemento': 'none', # Factura global no tiene complemento CFDI
                'domicilio_extra': '', # No aplica para factura global
            })

            if not pdf_content:
                print("Error: No se generó contenido PDF en el Cron")
                return False

            pdf_base64 = base64.b64encode(pdf_content)
            print('PDF Asíncrono creado con éxito')
            return pdf_base64
            
        except Exception as e:
            # En tareas de cron es mejor loguear que usar UserError, para que no detenga otras ejecuciones
            print(f"Error crítico generando PDF en Cron: {str(e)}")
            return False

class TicketMonitorLogbook(models.Model):
    _name='contabilidad_kuale.ticket_monitor_logbook'
    _description = 'bitacora de erores durante facturacion'

    date = fields.Date(string='Fecha', required=True)
    description = fields.Text(string='Detalles', required=True)
    ticket_id = fields.Many2one('contabilidad_kuale.ticket_monitor','ticket', required=True)
    xml_content = fields.Text(string='XML Generado', help='Contenido del XML que fue enviado al PAC para timbrado. Útil para diagnóstico de errores.')

    def action_view_xml_content(self):
        """Abre un wizard/popup mostrando el XML generado para este error."""
        self.ensure_one()
        if not self.xml_content:
            raise UserError('No hay XML guardado en este registro de bitácora.')
        return {
            'type': 'ir.actions.act_window',
            'name': 'XML Generado (Diagnóstico)',
            'res_model': 'contabilidad_kuale.logbook_xml_viewer',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_xml_content': self.xml_content,
                'default_logbook_date': str(self.date),
                'default_description': self.description,
            },
        }

class LogbookXmlViewer(models.TransientModel):
    """Wizard de solo lectura para visualizar el XML generado capturado en la bitácora."""
    _name = 'contabilidad_kuale.logbook_xml_viewer'
    _description = 'Visor de XML de Diagnóstico'

    xml_content = fields.Text(string='XML Generado', readonly=True)
    logbook_date = fields.Char(string='Fecha del error', readonly=True)
    description = fields.Text(string='Descripción del error', readonly=True)


class TicketPayments(models.Model):
    _name='contabilidad_kuale.ticket_monitor_payments'
    _description = 'listado de metodos de pagos para tickets'

    # payment_method = fields.Many2one('cfdi.clavemetododepago', string='Método de pago',)
    payment_type = fields.Many2one('cfdi.claveformadepago', string='Forma de pago',required=True)
    amount = fields.Float(string='Monto', required=True)
    ticket_id = fields.Many2one('contabilidad_kuale.ticket_monitor','ticket',)

    ticket_monitor_payment_audit_id = fields.Many2one(
        'contabilidad_kuale.ticket_monitor_audit',
        string='Auditoría'
    )
    ticket_payment_audit_id = fields.Many2one( 'contabilidad_kuale.ticket_monitor_audit',
        string='Auditoría pago ticket')

class TicketInvoiceCancellation(models.TransientModel):
    _name='contabilidad_ticket.invoice_cancellation'
    _description = 'Wizard para cancelar'

    company_id = fields.Many2one('res.company', string='Empresa',
                                 domain="[('is_branch', '=', False)]")
    branch_id = fields.Many2one('res.company', string='Sucursal',
                                domain="['|', ('parent_id', '=', company_id), ('id', '=', company_id)]",
                                required=True)

    invoice_uuid = fields.Char(string="UUID", required=True)

    cancel_reason = fields.Selection([
        ('01','Con relación (requiere folio sustitución)'),
        ('02','Sin relación'),
        ('03','No se llevó a cabo la operación'),
        ('04','Operación nominativa incluida en factura global')
    ],string = 'Motivo de cancelacion',required=True)

    uuid_replacement = fields.Char(string='UUID de remplazo')


    def action_cancel_invoice(self):
        self.ensure_one()
        ticket = self.env['contabilidad_kuale.ticket_monitor'].sudo().search([('invoice_uuid','=',self.invoice_uuid)])
        if not ticket:
            raise UserError(f'No se encontro factura con uuid: {self.invoice_uuid} asociada a ningun registro ')

        if not self.company_id.csd_cert or not self.company_id.csd_key or not self.company_id.csd_password:
            raise UserError("Faltan datos del CSD en la sucursal para realizar la cancelación.")

        csd_cer_b64 = base64.b64encode(self.company_id.csd_cert).decode()
        csd_key_b64 = base64.b64encode(self.company_id.csd_key).decode()
        csd_password = self.company_id.csd_password

        # 1. Autenticación con Timeout
        try:
            session_auth = requests.Session()
            transport_auth = Transport(session=session_auth, timeout=20)
            #login = Client('https://timbrado.digibox.com.mx/Autenticacion/wsAutenticacion.asmx?WSDL', transport=transport_auth)
            #token = login.service.AutenticarBasico("cfdi@grupokuale.com.mx", "1?eFCeZ7LR8")
            login = Client('https://testtimbrado.digibox.com.mx/Autenticacion/wsAutenticacion.asmx?wsdl', transport=transport_auth)
            token = login.service.AutenticarBasico("pruebaskuale@digibox.com.mx", "123456789")
            
            if not token:
                raise UserError("No se obtuvo token de autenticación para cancelar.")
        except requests.exceptions.Timeout:
            raise UserError("El servicio de autenticación del PAC tardó demasiado (Timeout). Intenta más tarde.")
        except Exception as e:
            raise UserError(f"Error al obtener token de autenticación: {str(e)}")

        if self.cancel_reason == "01" and not self.uuid_replacement:
            raise UserError("Para motivo 01 se requiere el folio de sustitución.")

        # 2. Cancelación con Timeout
        try:
            session_canc = requests.Session()
            transport_canc = Transport(session=session_canc, timeout=60)
            cancel_ws = Client('https://timbrado.digibox.com.mx/Cancelacion/wsCancelacion.asmx?WSDL', transport=transport_canc)

            response = cancel_ws.service.CancelarCSDV2(
                CSDCer=csd_cer_b64,
                CSDKey=csd_key_b64,
                password=csd_password,
                RFCEmisor=self.company_id.rfc,
                UUIDs={"string": [self.invoice_uuid]},
                motivo=self.cancel_reason,
                folioSustitucion=self.uuid_replacement or "",
                tokenAutenticacion=token
            )
        except requests.exceptions.Timeout:
            raise UserError("El servicio de cancelación del PAC tardó demasiado en responder (Timeout). Intenta más tarde.")
        except Exception as e:
            raise UserError(f"Error al cancelar CFDI: {str(e)}")

        # procesar respuesta SAT
        try:
            acuse_xml = response
            acuse_dict = xmltodict.parse(acuse_xml)
            estatus = acuse_dict["Acuse"]["Folios"]["EstatusUUID"]
        except:
            raise UserError("Error procesando el acuse de cancelación devuelto por el PAC.")

        codes = {
            201: "Cancelación exitosa.",
            202: "El CFDI ya estaba cancelado.",
            203: "UUID no corresponde al emisor.",
            204: "Folio fiscal no aplicable.",
            205: "UUID no existente.",
            207: "Motivo inválido.",
            208: "Folio sustituto inválido.",
        }

        msg = codes.get(estatus, f"Código de cancelación SAT: {estatus}")
        ticket.env['contabilidad_kuale.additional_file'].sudo().create({
            'ticket_monitor_id': ticket.id,
            'file': base64.b64encode(acuse_xml.encode()),
            'file_name': f"{ticket.invoice_uuid}_acuse_cancelacion.xml",
            'description': 'Acuse de cancelación SAT',
            'file_type': 'xml',
        })

        # Actualizar estatus en Odoo solo si fue cancelado o ya estaba cancelado
        if estatus in (201, 202):
            ticket.invoice_status = "cancelado"

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Resultado de cancelación",
                "message": msg,
                "sticky": False,
                "type": "success" if estatus in (201, 202) else "danger",
            }
        }


class TicketWizardCFDI(models.TransientModel):
    _name='ticket.wizard.cfdi'
    _description='wizard para subir cfdi y obtener los datos para facturación'

    file = fields.Binary(string='Constancia de Situación Fiscal (PDF)',required=True)
    ticket_id = fields.Many2one('contabilidad_kuale.ticket_monitor',string='Ticket')

    def _extract_text_from_pdf(self,pdf_binary):
        pdf_bytes = base64.b64decode(pdf_binary)
        text = ""
        with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"

        if not text:
            raise UserError("No se pudo leer texto del PDF. ¿Es una constancia válida del SAT?")
        print(text)
        return text

    def _parse_sat_data(self, text):
        def find(pattern):
            match = re.search(pattern, text, re.MULTILINE)
            return match.group(1).strip() if match else False

        def normalize(txt):
            if not txt:
                return ""
            txt = unicodedata.normalize('NFKD', txt)
            txt = ''.join(c for c in txt if not unicodedata.combining(c))
            return txt.upper().replace(" ", "")


        rfc = find(r"RFC:\s*([A-Z0-9]{12,13})")
        if not rfc:
            raise UserError("No se pudo detectar el RFC en la constancia del SAT.")


        razon_social = find(r"Denominación/RazónSocial:\s*(.+)") or find(r"Denominación/Razón Social:\s*(.+)")

        nombre_pf = find(r"Nombre\(s\):\s*(.+)")
        apellido_paterno = find(r"PrimerApellido:\s*(.+)")
        apellido_materno = find(r"SegundoApellido:\s*(.+)")

        if razon_social:
            client_name = razon_social
            es_fisica = False
        else:
            partes = [nombre_pf, apellido_paterno, apellido_materno]
            client_name = " ".join(p for p in partes if p)
            es_fisica = True


        cp = find(r"CódigoPostal:\s*(\d{5})")
        city = (
                find(r"NombredelMunicipio.*?:\s*(.+)")
                or find(r"Nombre del Municipio.*?:\s*(.+)")
        )

        street_1 = find(r"NombredeVialidad:\s*(.+)")
        street_2 = (
                find(r"NúmeroExterior:\s*(.+)")
                or ""
        )


        regimen_id = False
        regimen_model = self.env['cfdi.claveregimenfiscal'].sudo().search([])

        normalized_text = normalize(text)

        for reg in regimen_model:
            if normalize(reg.Descripcion) in normalized_text:
                if es_fisica and not reg.Fisica:
                    continue
                if not es_fisica and not reg.Moral:
                    continue
                regimen_id = reg.id
                break

        if not regimen_id:
            raise UserError(
                "No se pudo identificar el régimen fiscal en la constancia. "
                "Verifique que el catálogo esté actualizado."
            )

        return {
            "client_rfc": rfc,
            "client_name": client_name,
            "client_cp": cp,
            "client_city": city,
            "client_street_1": street_1,
            "client_street_2": street_2,
            "client_tax_regimen_id": regimen_id,
        }

    def action_apply_cfdi_data(self):
        self.ensure_one()

        text = self._extract_text_from_pdf(self.file)
        data = self._parse_sat_data(text)

        self.ticket_id.write({
            'client_rfc': data.get('client_rfc'),
            'client_name': data.get('client_name'),
            'client_cp': data.get('client_cp'),
            'client_city': data.get('client_city'),
            'client_street_1': data.get('client_street_1'),
            'client_street_2': data.get('client_street_2'),
            'client_tax_regimen_id': data.get('client_tax_regimen_id'),
        })

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Constancia procesada'),
                'message': _('Los datos fiscales se cargaron correctamente en el ticket.'),
                'type': 'success',
                'sticky': False,
            }
        }



