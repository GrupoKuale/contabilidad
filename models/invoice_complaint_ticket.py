from odoo import models, fields, api

class InvoiceComplaintTicket(models.Model):
    _name = 'contabilidad_kuale.invoice_complaint_ticket'
    _description = 'Clients Invoice Complaint Ticket panel'
    _order = 'create_date desc'

    additional_files = fields.One2many(
        'contabilidad_kuale.additional_file',
        'invoice_complaint_id',
        string='Archivos digitales'
    )
    complaint_type = fields.Selection([
        ('ticket', 'Nombre incorrecto del receptor de la factura.'),
        ('branch', 'No aparece la sucursal.'),
        ('payment', 'Forma o método de pago incorrecto.'),
        ('name', 'Nombre incorrecto del receptor de la factura.'),
        ('late', 'Mi ticket es de un mes anterior.'),
        ('data', 'Los datos de mi factura son incorrectos.'),
        ('specific', 'Requiero una refacturación por datos.'),
        ('register', 'No me permite registrar mis datos.'),
    ], string='Tipo de problema')
    rfc = fields.Char(string='RFC', required=True)
    cp = fields.Char(string='Codigo Postal', required=True)
    receiver = fields.Char(string='Nombre o Razón social', required=True)
    taxRegime = fields.Many2one('cfdi.claveregimenfiscal', string="Régimen Fiscal")
    cfdiUse = fields.Many2one('cfdi.claveusocfdi', string="Uso de CFDI")
    email = fields.Char(string='Correo electrónico', required=True)
    solved = fields.Boolean(string='Solucionado', default=False)

    empresa = fields.Many2one(
        'res.company',
        string='Empresa',
        domain=[('parent_id', '=', False)]
    )
    sucursal = fields.Many2one(
        'res.company',
        string='Sucursal',
        domain="[('parent_id', '=', empresa)]"
    )
    ticket_id = fields.Many2one(
        'contabilidad_kuale.ticket_monitor',
        string='Número de ticket',
    )
    
    ticket_folio_display = fields.Char(
        string='Número de Ticket',
        related='ticket_id.ticket_folio',
        readonly=True,
    )


