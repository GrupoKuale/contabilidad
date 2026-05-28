from odoo import models, fields, api


class InvoiceClientWebsite(models.Model):
    _name = 'contabilidad_kuale.invoice_client_website'
    _description = 'Invoice Client Website'
    ## receptor ##
    receiver = fields.Char('Client Name', required=True)
    email = fields.Char('Client Email', required=True)
    address = fields.Char('Client Address', required=True)
    tax_regime = fields.Many2one(
        'cfdi.claveregimenfiscal',
        string='Client Tax Regime',
        required=True
    )
    cfdi_use = fields.Many2one(
        'cfdi.claveusocfdi',
        string='Client CFDI Use',
        required=True
    )
    rfc = fields.Char('Client RFC', required=True)

    ## receptor ##
    company_id = fields.Many2one('res.company', string='Compañia', required=True)
    branch_id = fields.Many2one('res.company', string="Sucursal",
                                domain="[('id', 'child_of', company_id)]")

    ## ticket ##
    ticket_folio = fields.Char('Client Ticket Folio', required=True)
