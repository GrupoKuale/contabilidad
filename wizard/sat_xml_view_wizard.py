from odoo import models, fields

class SatXmlViewWizard(models.TransientModel):
    _name = 'sat.xml.view.wizard'
    _description = 'Ver XMl CFDI'

    xml_code = fields.Text(string='XML Code', readonly=True)