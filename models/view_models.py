from odoo import fields, models


class IrActionsActWindowView(models.Model):
    _inherit = 'ir.actions.act_window.view'

    view_mode = fields.Selection(
        selection_add=[
            ('kuale_trial_balance', "Kuale Trial Balance"),
            ('kuale_income_statement',"Kuale Income Statement"),
            ('kuale_financial_position',"Kuale Financial Position"),
            ('kuale_static_balance',"Kuale Static Balance"),
            ('kuale_aux_movement',"Kuale Auxiliary Movement"),
        ],
        ondelete={'kuale_trial_balance': 'cascade','kuale_income_statement': 'cascade',
                  'kuale_financial_position': 'cascade','kuale_static_balance': 'cascade',
                  'kuale_aux_movement': 'cascade'},
    )

class IrUiView(models.Model):
   _inherit = 'ir.ui.view'

   type = fields.Selection(
       selection_add=[
           ('kuale_trial_balance', "Kuale Trial Balance"),
           ('kuale_income_statement', "Kuale Income Statement"),
           ('kuale_financial_position', "Kuale Financial Position"),
           ('kuale_static_balance', "Kuale Static Balance"),
           ('kuale_aux_movement', "Kuale Auxiliary Movement"),
       ],
   )