
from datetime import date, datetime
from dateutil.relativedelta import relativedelta

from odoo import fields, models, _


class HrPayslipRun(models.Model):
    """Create new model for getting Payslip Batches"""
    _name = 'hr.payslip.run'
    _description = 'Lotes de nomina'

    name = fields.Char(
        required=True,
        help="Nombre del lote de nóminas",
        string="Nombre"
    )
    slip_ids = fields.One2many(
        'hr.payslip','payslip_run_id',string='Nóminas',
        help="Selecciona las nóminas para el lote"
    )
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('close', 'Cerrado'),
    ],string='Estado',index=True,readonly=True,copy=False,
        default='draft',help="Estado del lote de nóminas",
    )
    date_start = fields.Date(
        string='Fecha desde',
        required=True,
        help="Fecha de inicio del lote",
        default=lambda self: fields.Date.to_string(
            date.today().replace(day=1)
        )
    )
    date_end = fields.Date(
        string='Fecha de fin del lote',
        required=True,
        help="Fecha de finalización del lote",
        default=lambda self: fields.Date.to_string(
            (datetime.now() + relativedelta(months=+1, day=1, days=-1)).date()
        )
    )
    credit_note = fields.Boolean(
        string='Nota de crédito',
        help=(
            "Si está marcada, indica que todas las nóminas generadas "
            "desde aquí son nóminas de reembolso."
        )
    )

    def action_payslip_run(self):
        """Function for state change"""
        return self.write({'state': 'draft'})

    def close_payslip_run(self):
        """Function for state change"""
        return self.write({'state': 'close'})
