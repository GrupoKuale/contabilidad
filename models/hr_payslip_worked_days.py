
from odoo import fields, models


class HrPayslipWorkedDays(models.Model):
    """Create new model for adding some fields"""
    _name = 'hr.payslip.worked.days'
    _description = 'Payslip Worked Days'
    _order = 'payslip_id, sequence'

    name = fields.Char(string='Descripción',required=True,
        help="Descripción de los días trabajados")
    payslip_id = fields.Many2one('hr.payslip',string='Nómina',required=True,ondelete='cascade',index=True,
        help="Selecciona la nómina para los días trabajados")
    sequence = fields.Integer(required=True,index=True,default=10,string="Secuencia",
        help="Secuencia para los días trabajados")
    code = fields.Char(required=True,string="Código",
        help="El código que puede usarse en las reglas salariales")
    number_of_days = fields.Float(string='Número de días',
        help="Número de días trabajados")
    number_of_hours = fields.Float(string='Número de horas',
        help="Número de horas trabajadas")
    contract_id = fields.Many2one('hr.contract',string='Contrato',required=True,
        help="El contrato al que se aplican estos días trabajados",)
