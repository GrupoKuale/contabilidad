
from odoo import fields, models


class HrContractAdvantageTemplate(models.Model):
    """Create a new model for adding fields."""
    _name = 'hr.contract.advantage.template'
    _description = "Employee's Advantage on Contract"

    name = fields.Char('Nombre', required=True,
                       help="Name for Employee's Advantage on Contract")
    code = fields.Char('Codigo', required=True,
                       help="Code for Employee's Advantage on Contract")
    lower_bound = fields.Float('Limite inferior',
                               help="Lower bound authorized by the employer"
                                    "for this advantage")
    upper_bound = fields.Float('Limite superior',
                               help="Upper bound authorized by the employer"
                                    "for this advantage")
    default_value = fields.Float(string="Valor por defecto",
                                 help='Default value for this advantage')
