import os
import ast
import time

import xmltodict
from zeep import Client
import qrcode
from io import BytesIO
import base64
from dateutil.relativedelta import relativedelta
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT as DF
from num2words import num2words
from datetime import date, datetime, timedelta

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


class AccountMove(models.Model):
    """Inherits from the account.move model for adding the depreciation
    field to the account"""
    _inherit = 'account.move'

    asset_depreciation_ids = fields.One2many(
        'account.asset.depreciation.line',
        'move_id',
        string='Linea de depresiacion de activos')

    invoice = fields.Many2one('sat.xml.invoices', string='Factura',
                              help='uuid de la factura relacionada con esta nota credito/bonificación')
    invoice_ids = fields.Many2many(
        'sat.xml.invoices', 'account_move_sat_xml_invoices_rel',
        'move_id', 'invoice_id', string='Facturas',
        help='UUIDs de las facturas relacionadas con esta nota de crédito/bonificación')

    invoice_details = fields.Text(string='Detalles',
                                  help='Detalles de por que se aplica la nota de credito/bonificación')

    invoice_type = fields.Selection([
        ('invoice', 'Factura'),
        ('credit', 'Nota de credito'),
        ('debit', 'Nota de debito'),
        ('return', 'Nota de devolución'),
    ], string='Tipo de CFDI')

    payment_method = fields.Many2one('cfdi.clavemetododepago', string='Metodo de pago', required=True)
    payment_type = fields.Many2one('cfdi.claveformadepago', string='Forma de pago')
    coin_type = fields.Many2one('cfdi.clavemoneda', string='Moneda',
                                default=lambda self: self.env['cfdi.clavemoneda'].search([('Clave_moneda', '=', 'MXN')],
                                                                                         limit=1))

    complements = fields.Selection([
        ('none', 'Ninguno'),
        ('details', 'Complemento detallista'),
        ('donors', 'Complemento donatarias'),
        ('ine', 'Complemento INE'),
        ('aeroline', 'Complemento Aerolineas'),
        ('divisas', 'Divisas'),
        ('building', 'Servicios parciales de contruccion')
    ], string='Complementos', default='none')

    is_global = fields.Boolean(string='es Global?')
    additional_files = fields.One2many('contabilidad_kuale.additional_file',
                                       'invoice_id', string='Archivos digitales')

    # Campo para detectar si el diario es de compras (Facturas de proveedores)
    is_purchase_journal = fields.Boolean(
        string="Es diario de compras",
        compute='_compute_is_purchase_journal',
        store=False,
    )

    @api.depends('journal_id', 'journal_id.type', 'move_type')
    def _compute_is_purchase_journal(self):
        for move in self:
            move.is_purchase_journal = (
                move.journal_id.type == 'purchase'
                or move.move_type in ('in_invoice', 'in_refund', 'in_receipt')
            )

    # invoicing 1-1 to business like hidrologica
    client_rfc = fields.Char(string='RFC', related='partner_id.rfc', readonly=True)
    # client_address = fields.Char(string='Direccion', related='partner_id.street ', readonly=True)
    client_zip = fields.Char(string='Código postal', related='partner_id.zip', readonly=True)
    client_tax_regiment = fields.Many2one('cfdi.claveregimenfiscal', related='partner_id.tax_regime',
                                          string='Regimen fiscal', readonly=True)
    client_cfdi_use = fields.Many2one('cfdi.claveusocfdi', related='partner_id.Use_CFDI', string='Uso de CFDI',
                                      readonly=False)

    company_id = fields.Many2one('res.company', string='Empresa',
                                 domain="[('is_branch', '=', False)]")
    branch_id = fields.Many2one('res.company', string='Sucursal',
                                domain="['|', ('parent_id', '=', company_id), ('id', '=', company_id)]",
                                required=True)
    company_rfc = fields.Char(string='RFC', related='branch_id.rfc')
    company_zip = fields.Char(string='Código postal', related='branch_id.zip')
    company_tax_regiment = fields.Many2one('cfdi.claveregimenfiscal', string='Regimen fiscal',
                                           related='branch_id.regimen_fiscal', )
    company_serial = fields.Char(string='No. Serial', related='branch_id.client_serial_number')

    timbrado_errors = fields.Text(string='Errores de Timbrado', readonly=True)
    timbrado_status = fields.Selection([
        ('draft', 'Borrador'),
        ('ready', 'Listo para timbrar'),
        ('error', 'Error'),
        ('timbrado', 'Timbrado')
    ], string='Estado de Timbrado', default='draft')

    # global information
    periodicity = fields.Selection([
        ('01', 'Diario'),
        ('02', 'Semanal'),
        ('03', 'Quincenal'),
        ('04', 'Mensual'),
        ('05', 'Bimestral')
    ], string='Periodicidad')
    month = fields.Selection(
        [(str(i), datetime(2000, i, 1).strftime('%B')) for i in range(1, 13)],
        string="Mes")
    year = fields.Selection(
        [(str(y), str(y)) for y in range(2020, datetime.now().year + 1)],
        string="Año")

    # cron
    is_cron = fields.Boolean(string='Programada')
    recurrence_type = fields.Selection([
        ('once', 'Solo una vez'),
        ('weekly', 'Cada semana'),
        ('monthly', 'Cada mes'),
        ('yearly', 'Cada año'),
    ], string="Se aplica", default='once')

    schedule_date = fields.Datetime(string="Fecha y Hora Programada", )  # Solo para "una vez"
    week_day = fields.Selection([
        ('0', 'Lunes'), ('1', 'Martes'), ('2', 'Miércoles'),
        ('3', 'Jueves'), ('4', 'Viernes'), ('5', 'Sábado'), ('6', 'Domingo'),
    ], string="Día de la Semana")
    month_day = fields.Integer(string="Día del Mes")
    year_month = fields.Selection([(str(i), str(i)) for i in range(1, 13)], string="Mes")
    hour = fields.Float(string="Hora", help="Formato 24h (Ej: 14.5 para 14:30)")

    def action_schedule_invoice(self):
        return {
            'name': 'Programar Factura',
            'type': 'ir.actions.act_window',
            'res_model': 'account.move.schedule.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_move_id': self.id},
        }

    # Validación para pago en parcialidades
    @api.onchange('payment_method')
    def _onchange_payment_method(self):
        if self.payment_method and self.payment_method.Clave_metodo_de_pago == 'PPD':  # Pago en parcialidades
            forma_pago_99 = self.env['cfdi.claveformadepago'].search([('Clave_forma_de_pago', '=', '99')], limit=1)
            if forma_pago_99:
                self.payment_type = forma_pago_99

    # Validación para no facturar al mismo RFC del emisor
    @api.constrains('partner_id', 'branch_id')
    def _check_partner_rfc_not_same_as_company(self):
        for record in self:
            if record.partner_id and record.branch_id:
                if record.partner_id.rfc == record.branch_id.rfc:
                    raise ValidationError(
                        f"No es posible facturar al mismo RFC del emisor. "
                        f"RFC del cliente: {record.partner_id.rfc}, "
                        f"RFC del emisor: {record.branch_id.rfc}"
                    )

    # Validacion de timbrado
    def _validate_for_timbrado(self):
        """Valida los requisitos para timbrar una factura"""
        errors = []

        # Validar fecha
        if self.invoice_date > date.today():
            errors.append("• La fecha de facturación no puede ser futura")

        # Validar RFC diferente
        if self.partner_id.rfc == self.branch_id.rfc:
            errors.append(f"• No es posible facturar al mismo RFC del emisor ({self.branch_id.rfc})")

        # Validar datos obligatorios
        if not self.partner_id.rfc:
            errors.append("• El cliente debe tener RFC configurado")

        if not self.partner_id.zip:
            errors.append("• El cliente debe tener código postal configurado")

        if not self.client_cfdi_use:
            errors.append("• Debe seleccionar el uso de CFDI")

        if not self.payment_method:
            errors.append("• Debe seleccionar el método de pago")

        if not self.payment_type:
            errors.append("• Debe seleccionar la forma de pago")

        # Validar líneas de factura
        if not self.invoice_line_ids:
            errors.append("• La factura debe tener al menos una línea")

        for line in self.invoice_line_ids:
            if not line.product_id.sat_code_id:
                errors.append(f"• El producto '{line.product_id.name}' debe tener código SAT configurado")

        return errors

    def action_validate_timbrado(self):
        """Valida si la factura está lista para timbrar"""
        errors = self._validate_for_timbrado()

        if errors:
            self.timbrado_errors = '\n'.join(errors)
            self.timbrado_status = 'error'
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Errores de Validación',
                    'message': f'Se encontraron {len(errors)} errores. Revisa la sección "Errores de Timbrado".',
                    'sticky': True,
                    'type': 'warning'
                }
            }
        else:
            self.timbrado_errors = False
            self.timbrado_status = 'ready'
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Validación Exitosa',
                    'message': 'La factura está lista para timbrar.',
                    'type': 'success'
                }
            }

    @api.model
    def cron_process_scheduled_invoices(self):
        print('ejecutando cron')
        """Tarea programada que verifica las facturas programadas y las duplica si es el día correcto."""
        today = date.today()
        print('today: ', today)
        weekday_today = str(today.weekday())  # 0=Lunes, 6=Domingo
        print('weekday_today: ', weekday_today)
        month_today = str(today.month)
        print('month_today: ', month_today)
        day_today = today.day
        print('day_today: ', day_today)

        invoices = self.search([
            '|', '|', '|',
            ('recurrence_type', '=', 'once'),
            ('recurrence_type', '=', 'weekly'),
            ('recurrence_type', '=', 'monthly'),
            ('recurrence_type', '=', 'yearly'),
            ('is_cron', '=', True),
        ])
        print('invoices: ', invoices)

        for invoice in invoices:
            execute = False
            print('invoice.schedule_date', invoice.schedule_date.date())

            if invoice.recurrence_type == 'once' and invoice.schedule_date.date() == today:
                execute = True
            elif invoice.recurrence_type == 'weekly' and invoice.week_day == weekday_today:
                execute = True
            elif invoice.recurrence_type == 'monthly' and invoice.month_day == day_today:
                execute = True
            elif invoice.recurrence_type == 'yearly' and invoice.month_day == day_today and invoice.year_month == month_today:
                execute = True

            if execute:
                print('excuting invoice founded')
                new_invoice = invoice.copy({
                    'invoice_date': today,  # Asignar la fecha actual sin la hora
                    'state': 'draft',  # Dejar la nueva factura en estado 'draft'
                    'is_cron': False,
                })
                new_invoice.action_post()
                new_invoice.send_invoice_to_email()

    # complementos detallistas
    status = fields.Selection([
        ('ORIGINAL', 'Original'),
        ('DELETE', 'Delete'),
        ('COPY', 'Copy'),
        ('REEMPLAZA', 'Reemplaza')
    ], string='Estatus')

    state = fields.Selection([
        ('draft', 'Borrador'),
        ('to_approve', 'Por aprobar'),
        ('approved', 'Aprobado'),
        ('posted', 'Registrado'),
        ('preinvoiced', 'Pre-factura'),
        ('invoiced', 'Timbrado'),
        ('cancel', 'Cancelado'),
    ], string='Estado', readonly=True)

    document_type = fields.Selection([
        ('INVOICE', 'Factura'),
        ('DEBIT_NOTE', 'Nota de debito'),
        ('CREDIT_NOTE', 'Nota de credito'),
        ('LEASE_RECEIPT', 'Recibo de arrendamiento'),
        ('HONORARY_RECEIPT', 'Recibo de honorarios'),
        ('PARTIAL_INVOICE', 'Recibo de pago a plazos'),
        ('TRANSPORT_DOCUMENT', 'Carta porte'),
    ], string='Tipo de documento')
    uuid = fields.Char(string='UUID', help='UUID de factura cancelada')

    reference_date = fields.Date(string='Fecha de referencia(identificacion del pedido)')
    request_number = fields.Char(string='No. pedido')
    special_instructions_type = fields.Selection([
        ('AAB', 'Instrucciones de Entrega'),
        ('DUT', 'Instrucciones de Aduanas (Derechos e Impuestos)'),
        ('PUR', 'Instrucciones de Compra'),
        ('ZZZ', 'Otros'),
    ], string="Instrucciones especiales(tipo)")
    special_instructions = fields.Char(string='Instrucciones especiales(descripcion)')
    additional_info_type = fields.Selection([
        ('CK', 'Numero de cheque'),
        ('AAE', 'Cuenta predial'),
        ('ACE', 'Numero de documento(remision)'),
        ('ATZ', 'Numero de aprobacion'),
        ('AWR', 'Numero de documento que se reemplaza'),
        ('ON', 'Numero de pedido(comprador)'),
        ('DQ', 'Folio de recibo de mercancias'),
        ('IV', 'Numero de factura')
    ], string='Informacion adicional(tipo)')
    additional_info = fields.Char(string='Informacion adicional(descripcion)')
    folio_ticket = fields.Char(string='No. de folio contra-recibo')
    folio_ticket_date = fields.Date(string='Fecha de referencia(contra-recibo')
    gln_buyer = fields.Char(string='GLN comprador')
    buyer_info = fields.Char(string='Informacion de contacto comprador')
    gln_seller = fields.Char(string='GLN vendedor')
    secondary_identification = fields.Selection([
        ('SELLER_ASSIGNED_IDENTIFIER_FOR_A_PARTY', 'Numero interno del proveedor'),
        ('IEPS_REFERENCE', 'referencia signada para el IEPS')
    ], string='Numero de identificacion secundario')
    secondary_number = fields.Char(string='Numero de identificacion secundario')

    # complementos  donatarios
    authorization_number = fields.Char(string='Numero de autorizacion')
    authorization_date = fields.Date(string='Fecha de autorizacion')
    details_text = fields.Text(string='Leyenda',
                               default='Este comprobante ampara un donativo, el cual será destinado por la donataria a los fines propios de su objeto social. En el caso de que los bienes donados hayan sido deducidos previamente para los efectos del impuesto sobre la renta, este donativo no es deducible. La reproducción no autorizada de este comprobante constituye un delito en los términos de las disposiciones fiscales.')
    # complementos ine
    process_type = fields.Selection([
        ('Ordinario', 'Ordinario'),
        ('Precampaña', 'Precampaña'),
        ('Campaña', 'Campaña'),
    ], string='Tipo de proceso')
    scope = fields.Selection([
        ('Local', 'Local'),
        ('Federal', 'Federal'),
    ], string='Ambito')
    clave_state = fields.Many2one('cfdi.claveestado', string='Clave entidad')
    contabilidad_identification = fields.Char(string='Id contabilidad')
    # complemento aerolinea
    tua = fields.Char(string='TUA')
    complement_aeroline_ids = fields.One2many(
        'contabilidad_kuale.complement_aeroline',
        'invoice_id',
        string='Cargos agregados'
    )

    # complemento divisas
    operation_type = fields.Selection([
        ('venta', 'Venta'),
        ('compra', 'Compra'),
    ], string='Tipo de operacion')

    # servicios parciales de construccion
    license_number = fields.Char(string='Numero de permiso/licencia/autorizacion')
    street = fields.Char(string='Calle')
    exterior_number = fields.Char(string='No. exterior')
    interior_number = fields.Char(string='No. interior')
    colony = fields.Char(string='Colonia')
    locality = fields.Char(string='Localidad')
    reference = fields.Char(string='Referencia')
    municipality = fields.Char(string='Municipio')
    country = fields.Many2one('cfdi.claveestado', string='Estado')
    zip = fields.Char(string='Codigo postal')

    @api.constrains('invoice_date')
    def _check_invoice_date_limit(self):
        for record in self:
            if record.invoice_date:
                # Saltarse la restricción para facturas de proveedores (compras)
                if record.is_purchase_journal:
                    continue
                today = date.today()
                min_date = today - timedelta(days=3)
                max_date = today  # No puede ser fecha futura

                if record.invoice_date < min_date:
                    raise ValidationError("La fecha de factura no puede ser anterior a 3 días.")
                elif record.invoice_date > max_date:
                    raise ValidationError("La fecha de factura no puede ser una fecha futura.")

    def send_invoice_to_email(self):
        print('send_invoice_to_email')
        self.ensure_one()

        # Buscar los archivos adicionales asociados a este ticket
        invoice_files = self.env['contabilidad_kuale.additional_file'].search([
            ('invoice_id', '=', self.id),
            ('file_name', 'in', ['factura.pdf', 'factura.xml'])
        ])

        if not invoice_files:
            raise UserError("No se encontraron los archivos factura.pdf o factura.xml.")

        # Convertir archivos a adjuntos
        attachments = []
        for file in invoice_files:
            attachments.append((file.file_name, file.file))  # Asume que 'file_data' almacena los binarios

        # Crear valores del correo
        mail_values = {
            'subject': f"Factura {self.partner_id.name} - {self.invoice_date}",
            'body_html': "Gracias por tu preferencia \n el Adjunto encontrarás tu factura en PDF y XML.",
            'email_to': self.partner_id.email,
            'attachment_ids': [(0, 0, {
                'name': name,
                'datas': data,
                'res_model': 'mail.mail',
                'type': 'binary'
            }) for name, data in attachments],
        }

        # Enviar correo
        mail = self.env['mail.mail'].create(mail_values)
        mail.send()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Éxito',
                'message': 'Factura enviada correctamente',
                'sticky': False,  # Si es True, la alerta no se oculta automáticamente
                'type': 'success',  # Puede ser 'success', 'warning', 'danger', 'info'
            }
        }

    def duplicate_invoice(self):
        print('duplicadondo...')
        for record in self:
            default_vals = {
                'state': 'draft',
                'is_cron': False,
            }
            new_record = record.copy(default=default_vals)
            new_record.message_post(body="Factura duplicada desde %s" % record.name)

            return {
                'name': 'Factura Duplicada',
                'type': 'ir.actions.act_window',
                'res_model': 'account.move',
                'view_mode': 'form',
                'res_id': new_record.id,
                'target': 'current',
            }

    @api.onchange('branch_id')
    def _get_invoice_company_data(self):
        if self.branch_id:
            self.company_rfc = self.branch_id.rfc or ''
            self.company_zip = self.branch_id.zip or ''
            self.company_tax_regiment = self.branch_id.regimen_fiscal or ''
            self.company_serial = self.branch_id.client_serial_number or ''

    def action_timbrar_factura(self):
        # Forzar fecha de factura si no la tiene (requerida para validación y el XML)
        if not self.invoice_date:
            self.invoice_date = fields.Date.context_today(self)

        # Validar antes de timbrar
        errors = self._validate_for_timbrado()
        if errors:
            self.timbrado_errors = '\n'.join(errors)
            self.timbrado_status = 'error'
            raise UserError(f'No se puede timbrar la factura:\n\n' + '\n'.join(errors))

        # Limpiar errores y proceder
        self.timbrado_errors = False
        self.timbrado_status = 'ready'

        return self.action_timbrar()

    def action_resend_email(self):
        self.send_invoice_to_email()

    def action_preview_invoice(self):
        self.ensure_one()
        pre_pdf_file = self.env['contabilidad_kuale.additional_file'].search([
            ('invoice_id', '=', self.id),
            ('file_name', '=', 'temporaly_pdf.pdf')
        ], limit=1)

        if pre_pdf_file:
            pre_pdf_file.unlink()

        xml = self._generate_xml()
        self._generate_pdf(xml)

        # Buscar el archivo PDF generado
        pdf_file = self.env['contabilidad_kuale.additional_file'].search([
            ('invoice_id', '=', self.id),
            ('file_name', '=', 'temporaly_pdf.pdf')
        ], limit=1)

        if not pdf_file:
            raise UserError("No se encontró el archivo PDF generado.")

        # Aquí generas la URL para la vista previa
        preview_url = f'/web/content/{pdf_file._name}/{pdf_file.id}/file/factura.pdf'

        self.clear_temp_preview_files()

        # Retornar la URL para abrir el archivo
        result = {
            'type': 'ir.actions.act_url',
            'url': preview_url,
            'target': 'new',
        }

        return result

    def clear_temp_preview_files(self):
        print('cleaning shit')
        model = self.env['ir.model'].search([('model', '=', 'contabilidad_kuale.additional_file')], limit=1)

        if model:
            self.env['ir.cron'].create({
                'name': 'Borrar PDFs Temporales (Manual)',
                'model_id': model.id,
                'state': 'code',
                'code': "model.delete_temporary_pdfs()",
                'nextcall': (datetime.now() + timedelta(seconds=5)).strftime('%Y-%m-%d %H:%M:%S'),
                'interval_number': 1,
                'interval_type': 'days',  # aunque se ejecutará solo una vez
                'numbercall': 1,  # solo una ejecución
                'active': True,
            })

    def post(self):
        """Supering the post method to mapped the asset depreciation records"""
        self.mapped('asset_depreciation_ids').post_lines_and_close_asset()
        return super(AccountMove, self).action_post()

    @api.model
    def _refund_cleanup_lines(self, lines):
        """Supering the refund cleanup lines to check the asset category """
        result = super(AccountMove, self)._refund_cleanup_lines(lines)
        for i, line in enumerate(lines):
            for name, field in line._fields.items():
                if name == 'asset_category_id':
                    result[i][2][name] = False
                    break
        return result

    def action_cancel(self):
        """Action perform to cancel the asset record"""
        res = super(AccountMove, self).action_cancel()
        self.env['account.asset.asset'].sudo().search(
            [('invoice_id', 'in', self.ids)]).write({'active': False})
        return res

    def action_register_payment_supplier(self):
        """Registrar pago para pre-pólizas de proveedores (move_type='entry').
        Filtra las líneas de crédito (payable) y abre el wizard de pago."""
        self.ensure_one()
        payable_lines = self.line_ids.filtered(
            lambda l: l.account_id.account_type == 'liability_payable'
                      and l.credit > 0
        )
        if not payable_lines:
            raise UserError(_('No se encontraron líneas por pagar en esta póliza.'))

        return {
            'name': _('Registrar Pago'),
            'res_model': 'account.payment.register',
            'view_mode': 'form',
            'views': [[False, 'form']],
            'context': {
                'active_model': 'account.move.line',
                'active_ids': payable_lines.ids,
                'dont_redirect_to_payments': True,
            },
            'target': 'new',
            'type': 'ir.actions.act_window',
        }

    def action_post(self):
        print('action_post')
        """Action used to post invoice"""
        result = super(AccountMove, self).action_post()
        for inv in self:
            context = dict(self.env.context)
            # Within the context of an invoice,
            # this default value is for the type of the invoice, not the type
            # of the asset. This has to be cleaned from the context before
            # creating the asset,otherwise it tries to create the asset with
            # the type of the invoice.
            context.pop('default_type', None)
            inv.invoice_line_ids.with_context(context).asset_create()
        return result

    def _generate_xml(self):
        fecha_emision = str(self.invoice_date).replace(" ", "T")[:19]
        forma_pago = self.payment_type.Clave_forma_de_pago
        metodo_pago = self.payment_method.Clave_metodo_de_pago
        lugar_expedicion = self.company_zip
        exportacion = "01"

        rfc_emisor = self.company_rfc
        nombre_emisor = cfdi_escape(self.company_id.business_name)
        regimen_fiscal = self.company_tax_regiment.Clave_regimenFiscal
        serie = cfdi_escape(self.company_serial)
        folio = self.company_id.client_folio_number
        folio = str(folio).zfill(4)

        rfc_receptor = self.client_rfc
        nombre_receptor = cfdi_escape(self.partner_id.name)
        domicilio_fiscal_receptor = self.client_zip
        regimen_fiscal_receptor = self.client_tax_regiment.Clave_regimenFiscal
        uso_cfdi = self.client_cfdi_use.Clave_UsoCFDI

        subtotal = 0.0
        total_iva = 0.0
        total_descuento = 0.0
        conceptos_xml = ""
        complento_xml = ""

        for line in self.invoice_line_ids:
            clave_prod_serv = line.product_id.sat_code_id.code if line.product_id.sat_code_id else "01010101"
            no_identificacion = cfdi_escape(line.product_id.identification_number or '')
            cantidad = str(line.quantity) if line.quantity else '1'
            clave_unidad = line.product_id.unit_clave.Clave_unidad if line.product_id else "ACT"
            descripcion = cfdi_escape(line.product_id.name if line.product_id else "Venta")
            valor_unitario = line.price_unit
            importe = line.price_unit * line.quantity
            descuento = round((line.discount / 100) * importe, 2) if line.discount and line.discount > 0 else 0.0
            base_iva = importe - descuento
            importe_iva = round(base_iva * 0.16, 6)

            subtotal += importe
            total_iva += importe_iva
            total_descuento += descuento
            concepto_descuento = f' Descuento="{descuento:.2f}"' if descuento > 0 else ""
            descripcion_final = f'{descripcion}- Fecha de factura {self.invoice_date.strftime("%d/%m/%Y")}'
            conceptos_xml += f'''
                                <cfdi:Concepto ClaveProdServ="{clave_prod_serv}" NoIdentificacion="{no_identificacion}" Cantidad="{cantidad}"
                                ClaveUnidad="{clave_unidad}" Descripcion="{descripcion_final}" ValorUnitario="{valor_unitario:.2f}" Importe="{round(importe, 2):.2f}"
                                {concepto_descuento} ObjetoImp="02">
                                    <cfdi:Impuestos>
                                        <cfdi:Traslados>
                                            <cfdi:Traslado Base="{round(base_iva, 2):.2f}" Impuesto="002" TipoFactor="Tasa" TasaOCuota="0.160000" Importe="{round(importe_iva, 2):.2f}"/>
                                        </cfdi:Traslados>
                                    </cfdi:Impuestos>
                                </cfdi:Concepto>
                            '''

        if self.complements != 'none':
            if self.complements == 'details':
                print('complemento detallista')
                complento_xml = f'''
                <cfdi:Complemento>
                    <detallista:detallista xmlns:detallista="http://www.sat.gob.mx/detallista"
                        xsi:schemaLocation="http://www.sat.gob.mx/detallista http://www.sat.gob.mx/sitio_internet/cfd/detallista/detallista.xsd"
                        contentVersion="1.3.1"
                        documentStructureVersion="AMC8.1"
                        documentStatus="{self.status}"
                        type="SimpleInvoiceType">

                        <detallista:requestForPaymentIdentification>
                            <detallista:entityType>{self.document_type}</detallista:entityType>
                        </detallista:requestForPaymentIdentification>

                        <detallista:specialInstruction code="{self.special_instructions_type}">
                            <detallista:text>{self.special_instructions}</detallista:text>
                        </detallista:specialInstruction>

                        <detallista:orderIdentification>
                            <detallista:referenceIdentification type="ON">{self.request_number}</detallista:referenceIdentification>
                        </detallista:orderIdentification>

                        <detallista:AdditionalInformation>
                            <detallista:referenceIdentification type="{self.additional_info_type}">{self.additional_info}</detallista:referenceIdentification>
                        </detallista:AdditionalInformation>

                        <detallista:buyer>
                            <detallista:gln>{self.gln_buyer}</detallista:gln>
                            <detallista:contactInformation>
                                <detallista:personOrDepartmentName>
                                    <detallista:text>{self.buyer_info}</detallista:text>
                                </detallista:personOrDepartmentName>
                            </detallista:contactInformation>
                        </detallista:buyer>
                        <detallista:seller>
                        <detallista:gln>{self.gln_seller}</detallista:gln>
                            <detallista:alternatePartyIdentification type="{self.secondary_identification}">{self.secondary_number}</detallista:alternatePartyIdentification>
                        </detallista:seller>

                        <detallista:currency currencyISOCode="MXN">
                            <detallista:currencyFunction>BILLING_CURRENCY</detallista:currencyFunction>
                        </detallista:currency>

                        <detallista:currency currencyISOCode="MXN">
                            <detallista:currencyFunction>PAYMENT_CURRENCY</detallista:currencyFunction>
                            <detallista:rateOfChange>1.0000</detallista:rateOfChange>
                        </detallista:currency>
                    </detallista:detallista>
                </cfdi:Complemento>
                '''
            elif self.complements == 'donors':
                print('complemento donatario')
                complento_xml = f'''
                    <cfdi:Complemento>
                        <donat:Donatarias xmlns:donat="http://www.sat.gob.mx/donat" 
                            xsi:schemaLocation="http://www.sat.gob.mx/donat http://www.sat.gob.mx/sitio_internet/cfd/donat/donat11.xsd"
                            version="1.1" 
                            noAutorizacion="{self.authorization_number}" fechaAutorizacion="{self.authorization_date}" 
                            leyenda="{self.details_text}"/>
                    </cfdi:Complemento>
'''
            elif self.complements == 'ine':
                print('complemento ine')
                complento_xml = f'''
                <cfdi:Complemento>
                    <ine:INE 
                     xmlns:ine="http://www.sat.gob.mx/ine"
    xsi:schemaLocation="http://www.sat.gob.mx/cfd/4 cfdv40.xsd
    http://www.sat.gob.mx/ine http://www.sat.gob.mx/sitio_internet/cfd/ine/ine11.xsd"
                     Version="1.1" TipoProceso="{self.process_type}">
                      <ine:Entidad ClaveEntidad="{self.clave_state.Clave_estado}" Ambito="{self.scope}">
                        <ine:Contabilidad IdContabilidad="{self.contabilidad_identification}"/>
                      </ine:Entidad>
                    </ine:INE>
                  </cfdi:Complemento>
                '''
            elif self.complements == 'aeroline':
                print('complemento aeroline')
                cargos = self.complement_aeroline_ids
                total_cargos = sum(cargo.importe for cargo in cargos)
                complemento_aerolinea = f"""
                    <aerolineas:Aerolineas Version="1.0" TUA="{self.tua}" xsi:schemaLocation="http://www.sat.gob.mx/aerolineas http://www.sat.gob.mx/sitio_internet/cfd/aerolineas/aerolineas.xsd" xmlns:aerolineas="http://www.sat.gob.mx/aerolineas">
                        <aerolineas:OtrosCargos TotalCargos="{total_cargos:.2f}">
                    """
                for cargo in cargos:
                    complemento_aerolinea += f"""
                           <aerolineas:Cargo CodigoCargo="{cargo.code}" Importe="{cargo.importe:.6f}" />
                       """
                complemento_aerolinea += """
                       </aerolineas:OtrosCargos>
                   </aerolineas:Aerolineas>
                   """
                complento_xml = f'''
                <cfdi:Complemento>
                {complemento_aerolinea}
                </cfdi:Complemento>
                '''
            elif self.complements == 'divisas':
                print('complemento divisa')
                complento_xml = f'''
                <cfdi:Complemento>
                    <divisas:Divisas xmlns:divisas="http://www.sat.gob.mx/divisas"
    xsi:schemaLocation="http://www.sat.gob.mx/cfd/4 cfdv40.xsd
    http://www.sat.gob.mx/divisas http://www.sat.gob.mx/sitio_internet/cfd/divisas/divisas.xsd" version="1.0" tipoOperacion="{self.operation_type}" /> 
                  </cfdi:Complemento>
                '''
            elif self.complements == 'building':
                print('complemento building')
                complento_xml = f'''
                    <cfdi:Complemento>
                            <servicioparcial:parcialesconstruccion xmlns:servicioparcial="http://www.sat.gob.mx/servicioparcialconstruccion"
    xsi:schemaLocation="http://www.sat.gob.mx/cfd/4 cfdv40.xsd
    http://www.sat.gob.mx/servicioparcialconstruccion http://www.sat.gob.mx/sitio_internet/cfd/servicioparcialconstruccion/servicioparcialconstruccion.xsd"
                            Version="1.0" NumPerLicoAut="{self.license_number}">
                                <servicioparcial:Inmueble Colonia="{self.colony}" Municipio="{self.municipality}" Calle="{self.street}" Estado="{self.country.numero_estado}" Referencia="{self.reference}" NoInterior="{self.interior_number}" NoExterior="{self.exterior_number}" CodigoPostal="{self.zip}" Localidad="{self.locality}" />
                            </servicioparcial:parcialesconstruccion>
                      </cfdi:Complemento>
                '''

        if total_descuento > 0:
            total = (subtotal - total_descuento) + total_iva
            descuento_attr = f' Descuento="{round(total_descuento, 2):.2f}"'
        else:
            total = subtotal + total_iva
            descuento_attr = ""
        xml = f'''
                <cfdi:Comprobante Version="4.0" Serie="{serie}" Folio="{folio}" Fecha="{fecha_emision}" SubTotal="{round(subtotal, 2):.2f}" Total="{round(total, 2):.2f}" 
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
                            <cfdi:Traslado Base="{round(subtotal - total_descuento, 2):.2f}" Impuesto="002" TipoFactor="Tasa" 
                            TasaOCuota="0.160000" Importe="{round(total_iva, 2):.2f}"/>
                        </cfdi:Traslados>
                    </cfdi:Impuestos>
                        {complento_xml}
                </cfdi:Comprobante>
                '''

        print('xml: ', xml)
        return xml

    def _generate_pdf(self, xml, timbrado=False):
        self.ensure_one()
        file_name = 'temporaly_pdf.pdf'

        # Obtener el logo basado en el company_id
        logo_base64 = ""
        if self.company_id.client_invoice_logo:
            logo_base64 = self.company_id.client_invoice_logo.decode() if isinstance(
                self.company_id.client_invoice_logo, bytes) else self.company_id.client_invoice_logo
        else:
            print("Advertencia: La empresa no tiene configurado el logo de facturación.")

        try:
            uuid = ''
            qr_base64 = ''
            xml_dict = xmltodict.parse(xml)
            if timbrado:
                file_name = 'factura.pdf'
                uuid = xml_dict.get('cfdi:Comprobante', {}).get('cfdi:Complemento', {}).get('tfd:TimbreFiscalDigital',
                                                                                            {}).get('@UUID', '')

                if not uuid:
                    print("Error: No se encontró UUID en el XML")
                    return {'status': 'error', 'message': 'No se encontró UUID en el XML'}

                # Registrar UUID
                self.write({'uuid': uuid, })
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

            # complementos
            complemento = invoice_data.get('cfdi:Complemento', {})
            tipo_complemento = 'none'
            detallista = complemento.get('detallista:detallista', {})
            donataria = complemento.get('donat:Donatarias', {})
            ine = complemento.get('ine:INE', {})
            aeroline = complemento.get('aerolineas:Aerolineas', {})
            divisa = complemento.get('divisas:Divisas', {})
            build = complemento.get('servicioparcial:parcialesconstruccion', {})

            if detallista:
                tipo_complemento = 'detallista'
            elif donataria:
                tipo_complemento = 'donataria'
            elif ine:
                tipo_complemento = 'ine'
            elif aeroline:
                tipo_complemento = 'aerolinea'
            elif divisa:
                tipo_complemento = 'divisa'
            elif build:
                tipo_complemento = 'build'

            print('detallist:', detallista)
            print('donataria', donataria)
            print('ine:', ine)
            print('aeroline:', aeroline)
            print('divisa:', divisa)
            print('build:', build)

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
                'complemento': tipo_complemento,
                'detallista': detallista,
                'donataria': donataria,
                'ine': ine,
                'aerolinea': aeroline,
                'divisa': divisa,
                'build': build,
            })

            if not pdf_content:
                print("Error: No se generó contenido PDF")
                return {'status': 'error', 'message': 'No se generó contenido PDF'}

            # Codificar PDF en base64
            pdf_base64 = base64.b64encode(pdf_content)

            # Guardar el PDF junto con el XML
            self.env['contabilidad_kuale.additional_file'].sudo().create({
                'invoice_id': self.id,
                'file': pdf_base64,
                'file_name': file_name,
                'description': 'PDF generado',
                'file_type': 'pdf',
            })

            print("PDF guardado correctamente.")
            return {'status': 'success', 'message': 'PDF generado y guardado correctamente'}
        except Exception as e:
            raise UserError(f'Error generando el pdf: {e}')

    def action_timbrar(self):
        try:
            xml = self._generate_xml()
            # login = Client('https://testtimbrado.digibox.com.mx/Autenticacion/wsAutenticacion.asmx?WSDL')
            # token = login.service.AutenticarBasico("demo2", "123456789")
            login = Client('https://timbrado.digibox.com.mx/Autenticacion/wsAutenticacion.asmx?WSDL')
            token = login.service.AutenticarBasico("cfdi@grupokuale.com.mx", "1?eFCeZ7LR8")
            print('timbrando')
            timbrar = Client('https://sellado.digibox.com.mx/Timbrado.svc?singleWsdl')
            timbrar.service._binding_options['address'] = 'https://sellado.digibox.com.mx/Timbrado.svc'
            # timbrar = Client('https://testtimbrado.digibox.com.mx/Digibox.ServiciosSellado/Timbrado.svc?singleWsdl')
            xml_timbrado = timbrar.service.TimbrarXmlV2(xml, token)
            if xml_timbrado:
                print('XML Timbrado')
                
                # Publicar la póliza (apunte contable) solo cuando ya se timbró exitosamente
                if self.state in ['draft', 'to_approve', 'approved', 'preinvoiced']:
                    self.action_post()

                print("Guardando XML timbrado en archivos digitales...")
                file_data = base64.b64encode(xml_timbrado.encode('utf-8'))

                self.env['contabilidad_kuale.additional_file'].sudo().create({
                    'invoice_id': self.id,
                    'file': file_data,
                    'file_name': 'factura.xml',
                    'description': 'XML timbrado',
                    'file_type': 'xml',
                })
                self._generate_pdf(xml_timbrado, timbrado=True)
                self.company_id.sudo().write({
                    'client_folio_number': (self.company_id.client_folio_number + 1),
                })
                self.send_invoice_to_email()
                self.state = 'invoiced'
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': '¡Timbrado Exitoso!',
                        'message': f'El CFDI {self.name} ha sido timbrado correctamente. UUID: {self.uuid[:8]}... \nSe ha enviado al correo: {self.partner_id.email}',
                        'sticky': True,  # Para que permanezca visible más tiempo
                        'type': 'success',
                        'fadeout': 'slow'  # Desaparece lentamente
                    }
                }
            else:
                print('xml no timbrado')
        except Exception as e:
            print('error: ', e)
            raise UserError(f'error durante timbrado:{e}')


class AccountInvoiceLine(models.Model):
    _inherit = 'account.move.line'

    asset_category_id = fields.Many2one('account.asset.category',
                                        string='Asset Category')
    asset_start_date = fields.Date(string='Fecha de inicio del activo',
                                   compute='_get_asset_date', readonly=True,
                                   store=True)
    asset_end_date = fields.Date(string='Fecha de finalización del activo',
                                 compute='_get_asset_date', readonly=True,
                                 store=True)
    asset_mrr = fields.Float(string='Ingresos recurrentes mensuales',
                             compute='_get_asset_date',
                             readonly=True, digits='Account',
                             store=True)

    clave_prodserv = fields.Many2one('sat.product.codes', string='Clave ProdServ', related='product_id.sat_code_id')
    unit_clave = fields.Many2one('cfdi.claveunidad', string='Clave unidad', related='product_id.unit_clave')
    purchase_id = fields.Many2one('purchase.order', 'Orden de compra')

    @api.depends('asset_category_id', 'move_id.invoice_date')
    def _get_asset_date(self):
        """Returns the asset_start_date and the asset_end_date of the Asset"""
        for record in self:
            record.asset_mrr = 0
            record.asset_start_date = False
            record.asset_end_date = False
            cat = record.asset_category_id
            if cat:
                if cat.method_number == 0 or cat.method_period == 0:
                    raise UserError(_(
                        'El número de depreciaciones o la duración del período de '
                        'su categoría de activo no puede ser nula.'))
                months = cat.method_number * cat.method_period
                if record.move_id in ['out_invoice', 'out_refund']:
                    record.asset_mrr = record.price_subtotal_signed / months
                if record.move_id.invoice_date:
                    start_date = datetime.strptime(
                        str(record.move_id.invoice_date), DF).replace(day=1)
                    end_date = (start_date + relativedelta(months=months,
                                                           days=-1))
                    record.asset_start_date = start_date.strftime(DF)
                    record.asset_end_date = end_date.strftime(DF)

    def asset_create(self):
        """Create function for the asset and its associated properties"""
        for record in self:
            if record.asset_category_id:
                vals = {
                    'name': record.name,
                    'code': record.move_id.name or False,
                    'category_id': record.asset_category_id.id,
                    'value': record.price_subtotal,
                    'partner_id': record.partner_id.id,
                    'company_id': record.move_id.company_id.id,
                    'currency_id': record.move_id.company_currency_id.id,
                    'date': record.move_id.invoice_date,
                    'invoice_id': record.move_id.id,
                }
                changed_vals = record.env[
                    'account.asset.asset'].onchange_category_id_values(
                    vals['category_id'])
                vals.update(changed_vals['value'])
                asset = record.env['account.asset.asset'].create(vals)
                if record.asset_category_id.open_asset:
                    asset.validate()
        return True

    @api.depends('asset_category_id')
    def onchange_asset_category_id(self):
        """On change function based on the category and its updates the
        account status"""
        if self.move_id.move_type == 'out_invoice' and self.asset_category_id:
            self.account_id = self.asset_category_id.account_asset_id.id
        elif self.move_id.move_type == 'in_invoice' and self.asset_category_id:
            self.account_id = self.asset_category_id.account_asset_id.id

    @api.onchange('product_id')
    def _onchange_uom_id(self):
        """Onchange function for product that's call the UOM compute function
         and the asset category function"""
        result = super(AccountInvoiceLine, self)._compute_product_uom_id()
        self.onchange_asset_category_id()
        return result

    @api.depends('product_id')
    def _onchange_product_id(self):
        """Onchange product values and it's associated with the move types"""
        vals = super(AccountInvoiceLine, self)._compute_price_unit()
        if self.product_id:
            if self.move_id.move_type == 'out_invoice':
                self.asset_category_id = (
                    self.product_id.product_tmpl_id.
                    deferred_revenue_category_id)
            elif self.move_id.move_type == 'in_invoice':
                self.asset_category_id = (
                    self.product_id.product_tmpl_id.asset_category_id)
        return vals

    def _set_additional_fields(self, invoice):
        """The function adds additional fields that based on the invoice
        move types"""
        if not self.asset_category_id:
            if invoice.type == 'out_invoice':
                self.asset_category_id = \
                    (self.product_id.product_tmpl_id.
                     deferred_revenue_category_id.id)
            elif invoice.type == 'in_invoice':
                self.asset_category_id = (
                    self.product_id.product_tmpl_id.asset_category_id.id)
            self.onchange_asset_category_id()
        super(AccountInvoiceLine, self)._set_additional_fields(invoice)

    def get_invoice_line_account(self, type, product, fpos, company):
        """"It returns the invoice line and callback"""
        return product.asset_category_id.account_asset_id or super(
            AccountInvoiceLine, self).get_invoice_line_account(type, product,
                                                               fpos, company)

    @api.model
    def _query_get(self, domain=None):
        """Used to add domain constraints to the query"""
        self.check_access_rights('read')
        context = dict(self._context or {})
        domain = domain or []
        if not isinstance(domain, (list, tuple)):
            domain = ast.literal_eval(domain)
        date_field = 'date'
        if context.get('aged_balance'):
            date_field = 'date_maturity'
        if context.get('date_to'):
            domain += [(date_field, '<=', context['date_to'])]
        if context.get('date_from'):
            if not context.get('strict_range'):
                domain += ['|', (date_field, '>=', context['date_from']),
                           ('account_id.include_initial_balance', '=', True)]
            elif context.get('initial_bal'):
                domain += [(date_field, '<', context['date_from'])]
            else:
                domain += [(date_field, '>=', context['date_from'])]
        if context.get('journal_ids'):
            domain += [('journal_id', 'in', context['journal_ids'])]
        state = context.get('state')
        if state and state.lower() != 'all':
            domain += [('parent_state', '=', state)]
        if context.get('company_id'):
            domain += [('company_id', '=', context['company_id'])]
        elif context.get('allowed_company_ids'):
            domain += [('company_id', 'in', self.env.companies.ids)]
        else:
            domain += [('company_id', '=', self.env.company.id)]
        if context.get('reconcile_date'):
            domain += ['|', ('reconciled', '=', False), '|',
                       ('matched_debit_ids.max_date', '>',
                        context['reconcile_date']),
                       ('matched_credit_ids.max_date', '>',
                        context['reconcile_date'])]
        if context.get('account_tag_ids'):
            domain += [
                ('account_id.tag_ids', 'in', context['account_tag_ids'].ids)]
        if context.get('account_ids'):
            domain += [('account_id', 'in', context['account_ids'].ids)]
        if context.get('analytic_tag_ids'):
            domain += [
                ('analytic_tag_ids', 'in', context['analytic_tag_ids'].ids)]
        if context.get('analytic_account_ids'):
            domain += [('analytic_account_id', 'in',
                        context['analytic_account_ids'].ids)]
        if context.get('partner_ids'):
            domain += [('partner_id', 'in', context['partner_ids'].ids)]
        if context.get('partner_categories'):
            domain += [('partner_id.category_id', 'in',
                        context['partner_categories'].ids)]
        where_clause = ""
        where_clause_params = []
        tables = ''
        if domain:
            domain.append(
                ('display_type', 'not in', ('line_section', 'line_note')))
            domain.append(('parent_state', '!=', 'cancel'))
            query = self._where_calc(domain)
            # Wrap the query with 'company_id IN (...)' to avoid bypassing
            # company access rights.
            self._apply_ir_rules(query)
            tables, where_clause, where_clause_params = query.get_sql()
        return tables, where_clause, where_clause_params


class InvoiceComplementAeroline(models.Model):
    _name = 'contabilidad_kuale.complement_aeroline'
    _description = 'Invoice information for complement aeroline'

    code = fields.Char(string='Código cargo')
    importe = fields.Float(string='Importe')
    invoice_id = fields.Many2one('account.move', string='Factura')


class AccountMoveScheduleWizard(models.TransientModel):
    _name = "account.move.schedule.wizard"
    _description = "Programar Factura"

    move_id = fields.Many2one('account.move', string="Factura", required=True)
    recurrence_type = fields.Selection([
        ('once', 'Solo una vez'),
        ('weekly', 'Cada semana'),
        ('monthly', 'Cada mes'),
        ('yearly', 'Cada año'),
    ], string="Se aplica", required=True, default='once')

    schedule_date = fields.Datetime(string="Fecha y Hora", required=False)  # Solo para "una vez"
    week_day = fields.Selection([
        ('0', 'Lunes'), ('1', 'Martes'), ('2', 'Miércoles'),
        ('3', 'Jueves'), ('4', 'Viernes'), ('5', 'Sábado'), ('6', 'Domingo'),
    ], string="Día de la Semana", required=False)
    month_day = fields.Integer(string="Día del Mes (numero)", required=False)
    year_month = fields.Selection([(str(i), str(i)) for i in range(1, 13)], string="Mes", required=False)

    @api.onchange('recurrence_type')
    def _onchange_recurrence_type(self):
        """ Limpiar los campos cuando cambia el tipo de recurrencia """
        if self.recurrence_type == 'once':
            self.schedule_date = fields.Datetime.now()
        else:
            self.schedule_date = False
            self.week_day = False
            self.month_day = False
            self.year_month = False

    def confirm_schedule(self):
        """ Guardar la programación en la factura """

        values = {
            'recurrence_type': self.recurrence_type,
            'schedule_date': self.schedule_date if self.recurrence_type == 'once' else False,
            'week_day': self.week_day if self.recurrence_type == 'weekly' else False,
            'month_day': self.month_day if self.recurrence_type == 'monthly' else False,
            'year_month': self.year_month if self.recurrence_type == 'yearly' else False,
        }
        self.move_id.write(values)
        self.move_id.write({
            'is_cron': True
        })
        return {'type': 'ir.actions.act_window_close'}