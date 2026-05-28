from odoo import models, fields, api


class TrialBalanceLine(models.TransientModel):
    _name = 'contabilidad_kuale.trial_balance'
    _description = 'Trial Balance Line'
    _rec_name = 'name'

    account_id = fields.Many2one('account.account', string='Account')
    name = fields.Char(string='Nombre')
    parent_id = fields.Many2one('contabilidad_kuale.trial_balance', string='Parent')
    level = fields.Integer(string='Level', default=0)
    debit = fields.Float(string='Debit')
    credit = fields.Float(string='Credit')
    balance = fields.Float(string='Balance')
    has_children = fields.Boolean(string='Has Children')


class TrialBalanceWizard(models.TransientModel):
    _name = 'contabilidad_kuale.trial_balance_wizard'
    _description = 'Trial Balance Wizard'

    date_from = fields.Date(required=True)
    date_to = fields.Date(required=True)

    def action_generate_report(self):
        self.ensure_one()
        self.env['contabilidad_kuale.trial_balance'].search([]).unlink()

        # Solo grupos raíz
        root_groups = self.env['account.group'].search([('parent_id', '=', False)], order='code_prefix_start')
        for group in root_groups:
            self._add_group_lines(group, None, level=0)

        return {
            'type': 'ir.actions.act_window',
            'name': 'Trial Balance',
            'res_model': 'contabilidad_kuale.trial_balance',
            'view_mode': 'tree',
            'target': 'current',
        }

    def _add_group_lines(self, group, parent_line=None, level=0):
        debit_total = credit_total = balance_total = 0.0
        children_ids = []

        # Subgrupos
        subgroups = self.env['account.group'].search([('parent_id', '=', group.id)], order='code_prefix_start')
        for subgroup in subgroups:
            subgroup_result = self._add_group_lines(subgroup, None, level=level + 1)
            if subgroup_result:
                children_ids.append(subgroup_result.id)
                debit_total += subgroup_result.debit
                credit_total += subgroup_result.credit
                balance_total += subgroup_result.balance

        # Cuentas del grupo
        accounts = self.env['account.account'].search([('group_id', '=', group.id)], order='code')
        for acc in accounts:
            domain = [
                ('account_id', '=', acc.id),
                ('date', '>=', self.date_from),
                ('date', '<=', self.date_to),
                ('move_id.state', '=', 'posted')
            ]
            lines = self.env['account.move.line'].search(domain)
            debit = sum(l.debit for l in lines)
            credit = sum(l.credit for l in lines)
            balance = debit - credit

            acc_line = self.env['contabilidad_kuale.trial_balance'].create({
                'account_id': acc.id,
                'name': acc.display_name,
                'level': level + 1,
                'debit': debit,
                'credit': credit,
                'balance': balance,
                'has_children': False,
                'parent_id': None,  # Se asignará más abajo
            })

            children_ids.append(acc_line.id)
            debit_total += debit
            credit_total += credit
            balance_total += balance

        # Si no hay movimiento, no crear grupo
        if debit_total == 0 and credit_total == 0 and balance_total == 0:
            return None

        group_line = self.env['contabilidad_kuale.trial_balance'].create({
            'name': group.display_name,
            'level': level,
            'debit': debit_total,
            'credit': credit_total,
            'balance': balance_total,
            'has_children': True,
            'parent_id': parent_line.id if parent_line else None
        })

        # Asignar parent a hijos
        for child_id in children_ids:
            self.env['contabilidad_kuale.trial_balance'].browse(child_id).write({'parent_id': group_line.id})

        return group_line
