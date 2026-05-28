
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class HrPayslipLine(models.Model):
    """Create new model for adding Payslip Line"""
    _name = 'hr.payslip.line'
    _inherit = 'hr.salary.rule'
    _description = 'Línea de nómina'
    _order = 'contract_id, sequence'

    slip_id = fields.Many2one(
        'hr.payslip',
        string='Nómina',
        required=True,
        ondelete='cascade',
        help="Selecciona la nómina para esta línea"    )
    salary_rule_id = fields.Many2one(
        'hr.salary.rule',
        string='Regla salarial',
        required=True,
        help="Selecciona la regla salarial para esta línea",
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string='Empleado',
        required=True,
        help="Selecciona el empleado para esta línea",
    )
    contract_id = fields.Many2one(
        'hr.contract',
        string='Contrato',
        required=True,
        index=True,
        help="Selecciona el contrato para esta línea",
    )
    rate = fields.Float(
        string='Tasa (%)',
        help="Establece la tasa para la línea de nómina",
        digits=(16, 2),
        default=100.0,
    )
    amount = fields.Float(
        digits=(16, 2),
        string="Monto",
        help="Establece el monto para esta línea",
    )
    quantity = fields.Float(
        digits=(16, 2),
        default=1.0,
        string="Cantidad",
        help="Establece la cantidad para esta línea",
    )
    total = fields.Float(
        compute='_compute_total',
        string='Total',
        help="Monto total de la línea de nómina",
        digits=(16, 2),
        store=True,
    )



    @api.depends('quantity', 'amount', 'rate')
    def _compute_total(self):
        """Function for compute total amount"""
        for line in self:
            line.total = float(line.quantity) * line.amount * line.rate / 100

    @api.model_create_multi
    def create(self, vals_list):
        """Function for change value at the time of creation"""
        for values in vals_list:
            if 'employee_id' not in values or 'contract_id' not in values:
                payslip = self.env['hr.payslip'].browse(values.get('slip_id'))
                values['employee_id'] = values.get(
                    'employee_id') or payslip.employee_id.id
                values['contract_id'] = (values.get(
                    'contract_id') or payslip.contract_id and
                                         payslip.contract_id.id)
                if not values['contract_id']:
                    raise UserError(
                        _('You must set a contract to create a payslip line.'))
        return super(HrPayslipLine, self).create(vals_list)
