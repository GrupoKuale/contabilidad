
from odoo import fields, models


class HrContributionRegister(models.Model):
    """Create a new model for adding fields."""
    _name = 'hr.contribution.register'
    _description = 'Contribution Register'

    company_id = fields.Many2one(
        comodel_name='res.company',string='Compañía', help="Seleccione la compañía para el registro",
        default=lambda self: self.env['res.company']._company_default_get()
    )
    partner_id = fields.Many2one('res.partner',string='Socio',help="Seleccione el socio para el registro")
    name = fields.Char(required=True,string="Nombre",help="Nombre del registro de contribuciones")
    register_line_ids = fields.One2many('hr.payslip.line','register_id',
        string='Líneas del registro',readonly=True,help="Seleccione las líneas de nómina correspondientes")
    note = fields.Text(string='Descripción',help="Agregue una descripción para el registro")
