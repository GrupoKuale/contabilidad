from odoo import fields, models, api

class AccountTax(models.Model):
    _inherit = 'account.tax'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        type(self).company_id.readonly = False

