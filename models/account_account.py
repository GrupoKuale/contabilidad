
from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.misc import get_lang


class AccountAccount(models.Model):
    _inherit = 'account.account'

    accountable = fields.Many2one("hr.employee", string="Responsable", exportable=True)

    sat_nivel = fields.Selection([
        ('1', '1.ESTADO DE SITUACIÓN FINANCIERA'),
        ('2', '2.ESTADO DE RESULTADOS'),
        ('3', '3.ESTADO DE OTROS RESULTADOS INTEGRALES'),
        ('4', '4.CUENTAS DE ORDEN'),
        ('5', '5.ESTADO DE FLUJOS DE EFECTIVO'),
    ], string='Nivel SAT', required=True, exportable=True)

    naturaleza = fields.Selection([
        ('D', 'Deudora'),
        ('A', 'Acreedora')
    ], string='Naturaleza', exportable=True)

    group_id = fields.Many2one('account.group', string='Código agrupador', readonly=False, exportable=True)

    codigo_sat = fields.Many2many('codigo.agrupador.sat', string='Codigo Agrupador Sat', exportable=True)

    # @api.constrains('account_type', 'accountable')
    # def _check_accountable_for_asset_cash(self):
    #     for record in self:
    #         if record.account_type == 'asset_cash' and not record.accountable:
    #             raise ValidationError("El campo 'Responsable' es obligatorio para cuentas de tipo 'Banco y Efectivo'.")

class CashFlow(models.Model):
    _inherit = 'account.account'

    def get_cash_flow_ids(self):
        """Returns a list of cashflows for the account"""
        cash_flow_id = self.env.ref(
            'contabilidad_kuale.account_financial_report_cash_flow0')
        if cash_flow_id:
            return [('parent_id.id', '=', cash_flow_id.id)]

    cash_flow_type = fields.Many2one('account.financial.report',
                                     string="Cash Flow type",
                                     domain=get_cash_flow_ids)

    @api.onchange('cash_flow_type')
    def onchange_cash_flow_type(self):
        """Onchange the cash flow type of the account that will be updating
        the account_ids values"""
        for rec in self.cash_flow_type:
            # update new record
            rec.write({
                'account_ids': [(4, self._origin.id)]
            })
        if self._origin.cash_flow_type.ids:
            for rec in self._origin.cash_flow_type:
                # remove old record
                rec.write({'account_ids': [(3, self._origin.id)]})


class AccountCommonReport(models.Model):
    """Inherits the Account report model to add special fields and functions"""
    _inherit = "account.report"
    _description = "Account Common Report"

    company_id = fields.Many2one('res.company', string='Compañía',
                                 required=True, readonly=True,
                                 default=lambda self: self.env.company)
    journal_ids = fields.Many2many(
        comodel_name='account.journal',
        string='Diarios',
        required=True,
        default=lambda self: self.env['account.journal'].search(
            [('company_id', '=', self.company_id.id)]),
        domain="[('company_id', '=', company_id)]")
    date_from = fields.Date(string='Fecha de inicio')
    date_to = fields.Date(string='Fecha de finalización')
    target_move = fields.Selection([('posted', 'Todas las entradas publicadas'),
                                    ('all', 'Todas las entradas'),
                                    ], string='Movimientos de destino',
                                   required=True, default='posted')

    @api.onchange('company_id')
    def _onchange_company_id(self):
        """Onchange function based on the company and updated the journals"""
        if self.company_id:
            self.journal_ids = self.env['account.journal'].search(
                [('company_id', '=', self.company_id.id)])
        else:
            self.journal_ids = self.env['account.journal'].search([])

    def _build_contexts(self, data):
        """Builds the context information for the given data"""
        result = {}
        result['journal_ids'] = 'journal_ids' in data['form'] and data['form'][
            'journal_ids'] or False
        result['state'] = 'target_move' in data['form'] and data['form'][
            'target_move'] or ''
        result['date_from'] = data['form']['date_from'] or False
        result['date_to'] = data['form']['date_to'] or False
        result['strict_range'] = True if result['date_from'] else False
        result['company_id'] = data['form']['company_id'][0] or False
        return result

    def _print_report(self, data):
        """Raise an error if the report comes checked """
        raise NotImplementedError()

    def check_report(self):
        """Function to check if the report comes active models and related
        values"""
        self.ensure_one()
        data = {}
        data['ids'] = self.env.context.get('active_ids', [])
        data['model'] = self.env.context.get('active_model', 'ir.ui.menu')
        data['form'] = self.read(
            ['date_from', 'date_to', 'journal_ids', 'target_move',
             'company_id'])[0]
        used_context = self._build_contexts(data)
        data['form']['used_context'] = dict(used_context,
                                            lang=get_lang(self.env).code)
        return self.with_context(discard_logo_check=True)._print_report(data)


class AccountCommonJournalReport(models.TransientModel):
    """Model used for creating the common journal report"""
    _name = 'account.common.journal.report'
    _description = 'Common Journal Report'
    _inherit = "account.report"

    section_main_report_ids = fields.Many2many(string="Sección de",
                                               comodel_name='account.report',
                                               relation="account_common_journal_report_section_rel",
                                               column1="sub_report_id",
                                               column2="main_report_id")
    section_report_ids = fields.Many2many(string="Secciones",
                                          comodel_name='account.report',
                                          relation="account_common_journal_report_section_rel",
                                          column1="main_report_id",
                                          column2="sub_report_id")
    amount_currency = fields.Boolean(
        'Con moneda',
        help="Imprimir informe con la columna de moneda si la moneda es diferente a la moneda de la empresa")
    company_id = fields.Many2one('res.company', string='Compañía',
                                 required=True, readonly=True,
                                 default=lambda self: self.env.company)
    date_from = fields.Date(string='Fecha de inicio')
    date_to = fields.Date(string='Fecha de finalización')
    target_move = fields.Selection([('posted', 'Todas las entradas publicadas'),
                                    ('all', 'Todas las entradas'),
                                    ], string='Movimientos de destino',
                                   required=True, default='posted')

    def pre_print_report(self, data):
        """Pre-print the given data and that updates the amount
        amount_currency value"""
        data['form'].update({'amount_currency': self.amount_currency})
        return data

    def check_report(self):
        """Function to check if the report comes active models and related
                values"""
        self.ensure_one()
        data = {}
        data['ids'] = self.env.context.get('active_ids', [])
        data['model'] = self.env.context.get('active_model', 'ir.ui.menu')
        data['form'] = self.read(
            ['date_from', 'date_to', 'journal_ids', 'target_move',
             'company_id'])[0]
        used_context = self._build_contexts(data)
        data['form']['used_context'] = dict(used_context,
                                            lang=get_lang(self.env).code)
        return self.with_context(discard_logo_check=True)._print_report(data)

    def _build_contexts(self, data):
        """Builds the context information for the given data"""
        result = {}
        result['journal_ids'] = 'journal_ids' in data['form'] and data['form'][
            'journal_ids'] or False
        result['state'] = 'target_move' in data['form'] and data['form'][
            'target_move'] or ''
        result['date_from'] = data['form']['date_from'] or False
        result['date_to'] = data['form']['date_to'] or False
        result['strict_range'] = True if result['date_from'] else False
        result['company_id'] = data['form']['company_id'][0] or False
        return result
