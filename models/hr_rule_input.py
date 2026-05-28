
from odoo import fields, models


class HrRuleInput(models.Model):
    """Create new model for adding some fields"""
    _name = 'hr.rule.input'
    _description = 'Entrada de regla salarial'

    name = fields.Char(string='Descripción',required=True,
        help="Descripción de la entrada de la regla salarial")
    code = fields.Char(required=True,string="Código",
        help="El código que puede usarse en las reglas salariales")
    input_id = fields.Many2one('hr.salary.rule',string='Regla salarial',required=True,
        help="Selecciona la regla salarial correspondiente")
