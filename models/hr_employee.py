
from odoo import fields, models


class HrEmployee(models.Model):
    """Inherit hr_employee for getting Payslip Counts"""
    _inherit = 'hr.employee'
    _description = 'Employee'

    slip_ids = fields.One2many(
        'hr.payslip','employee_id',string='Nóminas',
        readonly=True,help="Seleccione las nóminas del empleado")
    payslip_count = fields.Integer(compute='_compute_payslip_count',
        string='Cantidad de nóminas',help="Muestra el total de nóminas del empleado")

    cashier_code = fields.Char(string='Código de cajero',
        help='Identificador de cajero para ventas de mostrador')

    def _compute_payslip_count(self):
        """Function for count Payslips"""
        payslip_data = self.env['hr.payslip'].sudo().read_group(
            [('employee_id', 'in', self.ids)],
            ['employee_id'], ['employee_id'])
        result = dict(
            (data['employee_id'][0], data['employee_id_count']) for data in
            payslip_data)
        for employee in self:
            employee.payslip_count = result.get(employee.id, 0)
