
from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    customer_credit_limit = fields.Boolean(
        string="Límite de crédito del cliente"
    )

    use_anglo_saxon_accounting = fields.Boolean(
        string="Usar contabilidad anglosajona",
        readonly=False,related='company_id.anglo_saxon_accounting')

    @api.model
    def get_values(self):
        res = super(ResConfigSettings, self).get_values()
        params = self.env['ir.config_parameter'].sudo()
        customer_credit_limit = params.get_param('customer_credit_limit',
                                                 default=False)
        res.update(customer_credit_limit=customer_credit_limit)
        return res

    def set_values(self):
        super(ResConfigSettings, self).set_values()
        self.env['ir.config_parameter'].sudo().set_param(
            "customer_credit_limit",
            self.customer_credit_limit)

    module_account_accountant = fields.Boolean(string='Account Accountant',
                                               help="Is Account Accountant")
    module_l10n_fr_hr_payroll = fields.Boolean(string='French Payroll',
                                               help="Is French Payroll")
    module_l10n_be_hr_payroll = fields.Boolean(string='Belgium Payroll',
                                               help="Is Belgium Payroll")
    module_l10n_in_hr_payroll = fields.Boolean(string='Indian Payroll',
                                               help="Is Indian Payroll")