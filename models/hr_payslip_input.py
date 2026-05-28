
from datetime import datetime
from dateutil import relativedelta
from odoo import fields, models


class HrPayslipInput(models.Model):
    """Create new model for adding fields"""
    _name = 'hr.payslip.input'
    _description = 'Entrada de nomina'
    _order = 'payslip_id, sequence'

    name = fields.Char(string='Descripción', required=True)
    payslip_id = fields.Many2one(
        'hr.payslip',string='Nómina',required=True,ondelete='cascade',
        help="Nómina",index=True,
    )
    sequence = fields.Integer(required=True,index=True,
        default=10,help="Secuencia",
    )
    code = fields.Char(
        required=True,
        help="El código que puede usarse en las reglas salariales",
    )
    date_from = fields.Date(
        string='Fecha desde',
        help="Fecha de inicio para las líneas de la nómina",required=True,
        default=datetime.now().strftime('%Y-%m-01')
    )
    date_to = fields.Date(
        string='Fecha hasta',help="Fecha de finalización para las líneas de la nómina",
        required=True,default=str(datetime.now() + relativedelta.relativedelta(months=+1, day=1, days=-1))[:10])

    amount = fields.Float(string="Monto",help=(
            "Se utiliza en los cálculos. "
            "Por ejemplo, una regla para ventas que tenga "
            "una comisión del 1% del salario básico por producto "
            "puede definirse en una expresión como: "
            "result = inputs.SALEURO.amount * contract.wage * 0.01."
        ))
    contract_id = fields.Many2one('hr.contract',string='Contrato',required=True,
        help="El contrato al que se aplica esta entrada",)
