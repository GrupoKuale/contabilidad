import calendar
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT as DF
from odoo.tools import float_compare, float_is_zero


class AccountAssetCategory(models.Model):
    _name = 'account.asset.category'
    _description = 'Asset category'

    active = fields.Boolean(default=True)
    name = fields.Char(required=True, index=True, string="Tipo de activo")
    company_id = fields.Many2one('res.company', string='Compañía',
                                 required=True,
                                 default=lambda self: self.env.company)
    price = fields.Monetary(string='Precio', required=True)
    currency_id = fields.Many2one("res.currency",
                                  default=lambda self: self.env[
                                      'res.currency'].search(
                                      [('name', '=', 'USD')]).id,
                                  readonly=True, hide=True)
    account_analytic_id = fields.Many2one('account.analytic.account',
                                          string='Cuenta analítica',
                                          domain="[('company_id', '=', "
                                                 "company_id)]")
    account_asset_id = fields.Many2one('account.account',
                                       string='Cuenta de activos', required=True,
                                       domain="[('account_type', '!=', "
                                              "'asset_receivable'),"
                                              "('account_type', '!=', "
                                              "'liability_payable'),"
                                              "('account_type', '!=', "
                                              "'asset_cash'),('account_type', "
                                              "'!=', 'liability_credit_card'),"
                                              "('deprecated', '=', False)]",
                                       help="Cuenta utilizada para registrar la "
                                            "compra del activo a su "
                                            "precio original.")
    account_depreciation_id = fields.Many2one(
        'account.account', string='Cuenta de depreciación',
        required=True,
        domain="[('account_type', '!=', 'asset_receivable'),('account_type',"
               " '!=', 'liability_payable'),"
               "('account_type', '!=', 'asset_cash')"
               ",('account_type', '!=', 'liability_credit_card'),"
               "('deprecated', '=', False),('company_id', '=', company_id)]",
        help="Cuenta utilizada en los asientos de depreciación,"
             "para disminuir el valor del activo")
    account_depreciation_expense_id = fields.Many2one(
        'account.account', string='Cuenta de Gastos',
        required=True,
        domain="[('account_type', '!=', 'asset_receivable'),"
               "('account_type', '!=','liability_payable'),"
               "('account_type', '!=', 'asset_cash'),"
               "('account_type', '!=','liability_credit_card'),"
               "('deprecated', '=', False),('company_id', '=', company_id)]",
        help="Cuenta utilizada en los asientos periódicos, para registrar una parte del "
             "activo como gasto.")
    journal_id = fields.Many2one('account.journal', string='Diario',
                                 required=True)
    method = fields.Selection(
        [('linear', 'Lineal'), ('degressive', 'Decreciente')],
        string='Método de cálculo', required=True, default='linear',
        help="Seleccione el método a utilizar para calcular el monto de las "
             "líneas de depreciación.\n"
             " * Lineal: Calculado en base a: Valor Bruto / Número de"
             "Depreciaciones\n"
             " * Degresivo: Calculado en base a: Valor Residual * "
             "Factor Degresivo")
    method_number = fields.Integer(string='Número de depreciaciones', default=5,
                                   help="El número de depreciaciones necesarias para"
                                        " depreciar su activo")
    method_period = fields.Integer(string='Duración del período', default=1,
                                   help="Indique aquí el tiempo transcurrido entre 2 "
                                        "depreciaciones, en meses",
                                   required=True)
    method_progress_factor = fields.Float('Factor decreciente', default=0.3)
    method_time = fields.Selection(
        [('number', 'Número de entradas'), ('end', 'Fecha de finalización')],
        string='Método del tiempo', required=True, default='number',
        help="Elija el método a utilizar para calcular las fechas y el número de "
             "entradas.\n"
             " * Número de entradas: Fije el número de entradas y el tiempo entre 2 "
             "depreciaciones.\n"
             " * Fecha de finalización: Elija el tiempo entre 2 depreciaciones y la "
             "fecha en la que las depreciaciones no deben exceder.")

    method_end = fields.Date('Fecha de finalización')
    prorata = fields.Boolean(string='Proporción de tiempo',
                             help='Indica que la primera entrada de depreciación '
                                  'para este activo debe hacerse desde la fecha de '
                                  'compra en lugar del 1 de enero / fecha de inicio '
                                  'del año fiscal')
    open_asset = fields.Boolean(string='Activos de confirmación automática',
                                help="Marque esta casilla si desea que los activos "
                                     "creados se confirmen automáticamente.")

    group_entries = fields.Boolean(string='Entradas del diario del grupo',
                                   help="Marque esta casilla si desea agrupar "
                                        "las entradas generadas por categorías"
                                   )
    type = fields.Selection([('sale', 'Venta: Reconocimiento de ingresos'),
                             ('purchase', 'Compra: Activo')], required=True,
                            index=True, default='purchase')

    @api.onchange('account_asset_id')
    def onchange_account_asset(self):
        if self.type == "purchase":
            self.account_depreciation_id = self.account_asset_id
        elif self.type == "sale":
            self.account_depreciation_expense_id = self.account_asset_id

    @api.onchange('type')
    def onchange_type(self):
        if self.type == 'sale':
            self.prorata = True
            self.method_period = 1
        else:
            self.method_period = 12

    @api.onchange('method_time')
    def _onchange_method_time(self):
        if self.method_time != 'number':
            self.prorata = False


class AccountAssetAsset(models.Model):
    _name = 'account.asset.asset'
    _description = 'Asset/Revenue Recognition'
    _inherit = ['mail.thread']

    entry_count = fields.Integer(compute='_entry_count',
                                 string='# Asset Entries')
    name = fields.Char(string='Nombre del activo', required=True, readonly=True)
    code = fields.Char(string='Referencia', size=32, readonly=True)
    value = fields.Float(string='Valor bruto', required=True, readonly=True,
                         digits=0)
    currency_id = fields.Many2one('res.currency', string='Divisa',
                                  required=True, readonly=True,
                                  default=lambda
                                      self: self.env.company.currency_id.id)
    company_id = fields.Many2one('res.company', string='Compañía',
                                 required=True, readonly=True,
                                 default=lambda self: self.env.company)
    note = fields.Text()
    category_id = fields.Many2one('account.asset.category',
                                  string='Categoría de activo',
                                  required=True, change_default=True,
                                  readonly=True, )
    date = fields.Date(string='Fecha', required=True, readonly=True,
                       default=fields.Date.context_today)
    state = fields.Selection(
        [('draft', 'Borrador'), ('open', 'En ejecución'), ('close', 'Cerrado')],
        'Estado', required=True, copy=False, default='draft',
        help="Cuando se crea un activo, el estado es 'Borrador'.\n"
             "Si el activo está confirmado, el estado pasa a 'En ejecución' y las "
             "líneas de depreciación se pueden registrar en la contabilidad.\n"
             "Puede cerrar manualmente un activo cuando finaliza la depreciación. "
             "Si se registra la última línea de depreciación, el activo "
             "pasa automáticamente a ese estado")
    active = fields.Boolean(default=True)
    partner_id = fields.Many2one('res.partner', string='Contacto',
                                 readonly=True)
    method = fields.Selection(
        [('linear', 'Lineal'), ('degressive', 'Decreciente')],
        string='Método de cálculo', required=True, readonly=True,
        default='linear',
        help="Elija el método a utilizar para calcular el monto de la depreciación "
             "líneal.\n * Lineal: Calculado en base a: Valor Bruto / Número "
             "de Depreciaciones\n"
             " * Degresivo: Calculado en base a: Valor Residual * "
             "Factor Degresivo")
    method_number = fields.Integer(string='Número de depreciaciones',
                                   readonly=True,
                                   default=5,
                                   help="El número de depreciaciones necesarias para"
                                        " depreciar su activo")
    method_period = fields.Integer(string='Número de meses en un período',
                                   required=True, readonly=True, default=12,
                                   help="Indique aquí el tiempo transcurrido entre 2 "
                                        "depreciaciones, en meses")
    method_end = fields.Date(string='Fecha de finalización', readonly=True, )
    method_progress_factor = fields.Float(string='Factor decreciente',
                                          readonly=True, default=0.3, )
    value_residual = fields.Float(compute='_amount_residual',
                                  digits=0, string='Valor residual')
    method_time = fields.Selection(
        [('number', 'Número de entradas'), ('end', 'Fecha de finalización')],
        string='Método del tiempo', required=True, readonly=True, default='number',
        help="Elija el método que se utilizará para calcular las fechas y la cantidad de "
             "entradas.\n"
             "* Número de entradas: fije la cantidad de entradas y el tiempo "
             "entre 2 depreciaciones.\n"
             "* Fecha de finalización: elija el tiempo entre 2 depreciaciones y la "
             "fecha que las depreciaciones no superarán.")
    prorata = fields.Boolean(string='Prorata Temporis', readonly=True,
                             help='Indica que la primera entrada de depreciación '
                                  'para este activo debe realizarse a partir de la '
                                  'fecha de compra en lugar de la primera '
                                  'fecha de enero / Fecha de inicio del año fiscal')
    depreciation_line_ids = fields.One2many(
        'account.asset.depreciation.line',
        'asset_id',
        string='Líneas de depreciación',
        readonly=True, )
    salvage_value = fields.Float(string='Valor de rescate', digits=0,
                                 readonly=True,
                                 help="Es la cantidad que planeas tener "
                                      "y que no puedes depreciar")
    invoice_id = fields.Many2one('account.move', string='Factura',
                                 copy=False)
    type = fields.Selection(related="category_id.type", string='Tipo',
                            required=True)

    def unlink(self):
        for asset in self:
            if asset.state in ['open', 'close']:
                raise UserError(
                    _('You cannot delete a document is in %s state.') % (
                        asset.state,))
            for depreciation_line in asset.depreciation_line_ids:
                if depreciation_line.move_id:
                    raise UserError(_(
                        'No se puede eliminar un activo que tiene líneas de '
                        'depreciación contabilizadas.'))
        return super(AccountAssetAsset, self).unlink()

    def _get_last_depreciation_date(self):
        """
        @param id: ids of a account.asset.asset objects
        @return: Returns a dictionary of the effective dates of the last
         depreciation entry made for given asset ids. If there isn't any,
         return the purchase date of this asset
        """
        self.env.cr.execute("""
                            SELECT a.id as id, COALESCE(MAX(m.date), a.date) AS date
                            FROM account_asset_asset a
                                LEFT JOIN account_asset_depreciation_line rel
                            ON
                                (rel.asset_id = a.id)
                                LEFT JOIN account_move m ON (rel.move_id = m.id)
                            WHERE a.id IN %s
                            GROUP BY a.id, m.date """, (tuple(self.ids),))
        result = dict(self.env.cr.fetchall())
        return result

    # @api.model
    # def _cron_generate_entries(self):
    #     self.compute_generated_entries(datetime.today())
    @api.onchange('category_id')
    def gross_value(self):
        self.value = self.category_id.price

    @api.model
    def compute_generated_entries(self, date, asset_type=None):
        # Entries generated : one by grouped category and one by asset
        # from ungrouped category
        created_move_ids = []
        type_domain = []
        if asset_type:
            type_domain = [('type', '=', asset_type)]

        ungrouped_assets = self.env['account.asset.asset'].search(
            type_domain + [('state', '=', 'open'),
                           ('category_id.group_entries', '=', False)])
        created_move_ids += (ungrouped_assets.
                             _compute_entries(date, group_entries=False))

        for grouped_category in self.env['account.asset.category'].search(
                type_domain + [('group_entries', '=', True)]):
            assets = self.env['account.asset.asset'].search(
                [('state', '=', 'open'),
                 ('category_id', '=', grouped_category.id)])
            created_move_ids += assets._compute_entries(date,
                                                        group_entries=True)
        return created_move_ids

    def _compute_board_amount(self, sequence, residual_amount, amount_to_depr,
                              undone_dotation_number,
                              posted_depreciation_line_ids, total_days,
                              depreciation_date):
        amount = 0
        if sequence == undone_dotation_number:
            amount = residual_amount
        else:
            if self.method == 'linear':
                amount = amount_to_depr / (undone_dotation_number - len(
                    posted_depreciation_line_ids))
                if self.prorata:
                    amount = amount_to_depr / self.method_number
                    if sequence == 1:
                        if self.method_period % 12 != 0:
                            date = datetime.strptime(str(self.date),
                                                     '%Y-%m-%d')
                            month_days = \
                                calendar.monthrange(date.year, date.month)[1]
                            days = month_days - date.day + 1
                            amount = ((amount_to_depr / self.method_number)
                                      / month_days * days)
                        else:
                            days = (self.company_id.compute_fiscalyear_dates(
                                depreciation_date)[
                                        'date_to'] - depreciation_date).days + 1
                            amount = ((
                                              amount_to_depr /
                                              self.method_number) /
                                      total_days * days)
            elif self.method == 'degressive':
                amount = residual_amount * self.method_progress_factor
                if self.prorata:
                    if sequence == 1:
                        if self.method_period % 12 != 0:
                            date = datetime.strptime(str(self.date),
                                                     '%Y-%m-%d')
                            month_days = \
                                calendar.monthrange(date.year, date.month)[1]
                            days = month_days - date.day + 1
                            amount = ((
                                              residual_amount *
                                              self.method_progress_factor) /
                                      month_days * days)
                        else:
                            days = (self.company_id.compute_fiscalyear_dates(
                                depreciation_date)[
                                        'date_to'] - depreciation_date).days + 1
                            amount = ((
                                              residual_amount *
                                              self.method_progress_factor) /
                                      total_days * days)
        return amount

    def _compute_board_undone_dotation_nb(self, depreciation_date, total_days):
        undone_dotation_number = self.method_number
        if self.method_time == 'end':
            end_date = datetime.strptime(str(self.method_end), DF).date()
            undone_dotation_number = 0
            while depreciation_date <= end_date:
                depreciation_date = date(depreciation_date.year,
                                         depreciation_date.month,
                                         depreciation_date.day) + relativedelta(
                    months=+self.method_period)
                undone_dotation_number += 1
        if self.prorata:
            undone_dotation_number += 1
        return undone_dotation_number

    def compute_depreciation_board(self):
        self.ensure_one()
        posted_depreciation_line_ids = self.depreciation_line_ids.filtered(
            lambda x: x.move_check).sorted(key=lambda l: l.depreciation_date)
        unposted_depreciation_line_ids = self.depreciation_line_ids.filtered(
            lambda x: not x.move_check)

        # Remove old unposted depreciation lines. We cannot use unlink()
        # with One2many field
        commands = [(2, line_id.id, False) for line_id in
                    unposted_depreciation_line_ids]

        if self.value_residual != 0.0:
            amount_to_depr = residual_amount = self.value_residual
            if self.prorata:
                # if we already have some previous validated entries,
                # starting date is last entry + method perio
                if posted_depreciation_line_ids and \
                        posted_depreciation_line_ids[-1].depreciation_date:
                    last_depreciation_date = datetime.strptime(
                        posted_depreciation_line_ids[-1].depreciation_date,
                        DF).date()
                    depreciation_date = last_depreciation_date + relativedelta(
                        months=+self.method_period)
                else:
                    depreciation_date = datetime.strptime(
                        str(self._get_last_depreciation_date()[self.id]),
                        DF).date()
            else:
                # depreciation_date = 1st of January of purchase year if
                # annual valuation, 1st of
                # purchase month in other cases
                if self.method_period >= 12:
                    if self.company_id.fiscalyear_last_month:
                        asset_date = (date(year=int(self.date.year),
                                           month=int(
                                               self.company_id.fiscalyear_last_month),
                                           day=int(
                                               self.company_id.
                                               fiscalyear_last_day)) +
                                      relativedelta(days=1) + relativedelta(
                                    year=int(
                                        self.date.year)))
                        # e.g. 2018-12-31 +1 -> 2019
                    else:
                        asset_date = datetime.strptime(
                            str(self.date)[:4] + '-01-01', DF).date()
                else:
                    asset_date = datetime.strptime(str(self.date)[:7] + '-01',
                                                   DF).date()
                # if we already have some previous validated entries, starting
                # date isn't 1st January but last entry + method period
                if posted_depreciation_line_ids and \
                        posted_depreciation_line_ids[-1].depreciation_date:
                    last_depreciation_date = datetime.strptime(str(
                        posted_depreciation_line_ids[-1].depreciation_date),
                        DF).date()
                    depreciation_date = last_depreciation_date + relativedelta(
                        months=+self.method_period)
                else:
                    depreciation_date = asset_date
            day = depreciation_date.day
            month = depreciation_date.month
            year = depreciation_date.year
            total_days = (year % 4) and 365 or 366

            undone_dotation_number = self._compute_board_undone_dotation_nb(
                depreciation_date, total_days)

            for x in range(len(posted_depreciation_line_ids),
                           undone_dotation_number):
                sequence = x + 1
                amount = self._compute_board_amount(sequence, residual_amount,
                                                    amount_to_depr,
                                                    undone_dotation_number,
                                                    posted_depreciation_line_ids,
                                                    total_days,
                                                    depreciation_date)

                amount = self.currency_id.round(amount)
                if float_is_zero(amount,
                                 precision_rounding=self.currency_id.rounding):
                    continue
                residual_amount -= amount
                vals = {
                    'amount': amount,
                    'asset_id': self.id,
                    'sequence': sequence,
                    'name': (self.code or '') + '/' + str(sequence),
                    'remaining_value': residual_amount if
                    residual_amount >= 0 else 0.0,
                    'depreciated_value': self.value - (
                            self.salvage_value + residual_amount),
                    'depreciation_date': depreciation_date.strftime(DF),
                }
                commands.append((0, False, vals))
                # Considering Depr. Period as months
                depreciation_date = date(year, month, day) + relativedelta(
                    months=+self.method_period)
                day = depreciation_date.day
                month = depreciation_date.month
                year = depreciation_date.year

        self.write({'depreciation_line_ids': commands})

        return True

    def validate(self):
        self.write({'state': 'open'})
        fields = [
            'method',
            'method_number',
            'method_period',
            'method_end',
            'method_progress_factor',
            'method_time',
            'salvage_value',
            'invoice_id',
        ]
        ref_tracked_fields = self.env['account.asset.asset'].fields_get(fields)
        for asset in self:
            tracked_fields = ref_tracked_fields.copy()
            if asset.method == 'linear':
                del (tracked_fields['method_progress_factor'])
            if asset.method_time != 'end':
                del (tracked_fields['method_end'])
            else:
                del (tracked_fields['method_number'])
            dummy, tracking_value_ids = asset._mail_track(tracked_fields,
                                                          dict.fromkeys(
                                                              fields))
            asset.message_post(subject=_('Asset created'),
                               tracking_value_ids=tracking_value_ids)

    def _get_disposal_moves(self):
        move_ids = []
        for asset in self:
            unposted_depreciation_line_ids = (
                asset.depreciation_line_ids.filtered(
                    lambda x: not x.move_check))
            if unposted_depreciation_line_ids:
                old_values = {
                    'method_end': asset.method_end,
                    'method_number': asset.method_number,
                }

                # Remove all unposted depr. lines
                commands = [(2, line_id.id, False) for line_id in
                            unposted_depreciation_line_ids]

                # Create a new depr. line with the residual amount and post it
                sequence = len(asset.depreciation_line_ids) - len(
                    unposted_depreciation_line_ids) + 1
                today = datetime.today().strftime(DF)
                vals = {
                    'amount': asset.value_residual,
                    'asset_id': asset.id,
                    'sequence': sequence,
                    'name': (asset.code or '') + '/' + str(sequence),
                    'remaining_value': 0,
                    'depreciated_value': asset.value - asset.salvage_value,
                    # the asset is completely depreciated
                    'depreciation_date': today,
                }
                commands.append((0, False, vals))
                asset.write(
                    {'depreciation_line_ids': commands, 'method_end': today,
                     'method_number': sequence})
                tracked_fields = self.env['account.asset.asset'].fields_get(
                    ['method_number', 'method_end'])
                changes, tracking_value_ids = asset._mail_track(
                    tracked_fields, old_values)
                if changes:
                    asset.message_post(subject=_(
                        'Activo vendido o enajenado. Entrada contable en espera'
                        'para validación.'),
                        tracking_value_ids=tracking_value_ids)
                move_ids += asset.depreciation_line_ids[-1].create_move(
                    post_move=False)

        return move_ids

    def set_to_close(self):
        move_ids = self._get_disposal_moves()
        if move_ids:
            name = _('Disposal Move')
            view_mode = 'form'
            if len(move_ids) > 1:
                name = _('Disposal Moves')
                view_mode = 'tree,form'
            return {
                'name': name,
                'view_mode': view_mode,
                'res_model': 'account.move',
                'type': 'ir.actions.act_window',
                'target': 'current',
                'res_id': move_ids[0],
            }
        # Fallback, as if we just clicked on the smartbutton
        return self.open_entries()

    def set_to_draft(self):
        self.write({'state': 'draft'})

    @api.depends('value', 'salvage_value',
                 'depreciation_line_ids.move_check',
                 'depreciation_line_ids.amount')
    def _amount_residual(self):
        for record in self:
            total_amount = 0.0
            for line in record.depreciation_line_ids:
                if line.move_check:
                    total_amount += line.amount
            record.value_residual = (record.value - total_amount -
                                     record.salvage_value)

    @api.onchange('company_id')
    def onchange_company_id(self):
        self.currency_id = self.company_id.currency_id.id

    @api.depends('depreciation_line_ids.move_id')
    def _entry_count(self):
        for asset in self:
            res = self.env['account.asset.depreciation.line'].search_count(
                [('asset_id', '=', asset.id), ('move_id', '!=', False)])
            asset.entry_count = res or 0

    @api.constrains('prorata', 'method_time')
    def _check_prorata(self):
        if self.prorata and self.method_time != 'number':
            raise ValidationError(_(
                'Prorata temporis se puede aplicar sólo para el método del tiempo.'
                '"número de depreciaciones".'))

    @api.onchange('category_id')
    def onchange_category_id(self):
        vals = self.onchange_category_id_values(self.category_id.id)
        # We cannot use 'write' on an object that doesn't exist yet
        if vals:
            for k, v in vals['value'].items():
                setattr(self, k, v)

    def onchange_category_id_values(self, category_id):
        if category_id:
            category = self.env['account.asset.category'].browse(category_id)
            return {
                'value': {
                    'method': category.method,
                    'method_number': category.method_number,
                    'method_time': category.method_time,
                    'method_period': category.method_period,
                    'method_progress_factor': category.method_progress_factor,
                    'method_end': category.method_end,
                    'prorata': category.prorata,
                }
            }

    @api.onchange('method_time')
    def onchange_method_time(self):
        if self.method_time != 'number':
            self.prorata = False

    def copy_data(self, default=None):
        if default is None:
            default = {}
        default['name'] = self.name + _(' (copy)')
        return super(AccountAssetAsset, self).copy_data(default)

    def _compute_entries(self, date, group_entries=False):
        depreciation_ids = self.env['account.asset.depreciation.line'].search([
            ('asset_id', 'in', self.ids), ('depreciation_date', '<=', date),
            ('move_check', '=', False)])
        if group_entries:
            return depreciation_ids.create_grouped_move()
        return depreciation_ids.create_move()

    @api.model
    def create(self, vals):
        asset = super(AccountAssetAsset,
                      self.with_context(mail_create_nolog=True)).create(vals)
        asset.sudo().compute_depreciation_board()
        return asset

    def write(self, vals):
        res = super(AccountAssetAsset, self).write(vals)
        if 'depreciation_line_ids' not in vals and 'state' not in vals:
            for rec in self:
                rec.compute_depreciation_board()
        return res

    def open_entries(self):
        move_ids = []
        for asset in self:
            for depreciation_line in asset.depreciation_line_ids:
                if depreciation_line.move_id:
                    move_ids.append(depreciation_line.move_id.id)
        return {
            'name': _('Journal Entries'),
            'view_mode': 'tree,form',
            'res_model': 'account.move',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'domain': [('id', 'in', move_ids)],
        }


class AccountAssetDepreciationLine(models.Model):
    _name = 'account.asset.depreciation.line'
    _description = 'Asset depreciation line'

    name = fields.Char(string='Nombre de depreciación', required=True, index=True)
    sequence = fields.Integer(required=True)
    asset_id = fields.Many2one('account.asset.asset', string='Activo',
                               required=True, ondelete='cascade')
    parent_state = fields.Selection(related='asset_id.state',
                                    string='Estado de activo')
    amount = fields.Float(string='Depreciación actual',
                          required=True)
    remaining_value = fields.Float(string='Depreciación del próximo período',
                                   required=True)
    depreciated_value = fields.Float(string='Depreciación acumulada',
                                     required=True)
    depreciation_date = fields.Date('Fecha de depreciación', index=True)
    move_id = fields.Many2one('account.move', string='Depreciación '
                                                     'Entrada')
    move_check = fields.Boolean(compute='_get_move_check', string='Vinculado',
                                store=True)
    move_posted_check = fields.Boolean(compute='_get_move_posted_check',
                                       string='Al corriente', store=True)

    @api.depends('move_id')
    def _get_move_check(self):
        for line in self:
            line.move_check = bool(line.move_id)

    @api.depends('move_id.state')
    def _get_move_posted_check(self):
        for line in self:
            line.move_posted_check = True if (line.move_id and
                                              line.move_id.state == 'posted') \
                else False

    def create_move(self, post_move=True):
        created_moves = self.env['account.move']
        prec = self.env['decimal.precision'].precision_get('Account')
        if self.mapped('move_id'):
            raise UserError(_(
                '¡Esta depreciación ya está vinculada a una entrada en el diario!'
                'Por favor, publíquela o elimínela.'))
        for line in self:
            category_id = line.asset_id.category_id
            depreciation_date = (self.env.context.get(
                'depreciation_date') or line.depreciation_date or
                                 fields.Date.context_today(
                                     self))
            company_currency = line.asset_id.company_id.currency_id
            current_currency = line.asset_id.currency_id
            amount = current_currency.with_context(
                date=depreciation_date)._convert(line.amount, company_currency)
            asset_name = line.asset_id.name + ' (%s/%s)' % (
                line.sequence, len(line.asset_id.depreciation_line_ids))
            partner = self.env['res.partner']._find_accounting_partner(
                line.asset_id.partner_id)
            move_line_1 = {
                'name': asset_name,
                'account_id': category_id.account_depreciation_id.id,
                'debit': 0.0 if float_compare(amount, 0.0,
                                              precision_digits=prec) > 0
                else -amount,
                'credit': amount if float_compare(amount, 0.0,
                                                  precision_digits=prec) > 0
                else 0.0,
                'journal_id': category_id.journal_id.id,
                'partner_id': partner.id,
                # 'analytic_account_id': category_id.account_analytic_id.id if
                # category_id.type == 'sale' else False,
                'currency_id': company_currency != current_currency and
                               current_currency.id or company_currency.id,
                'amount_currency': company_currency != current_currency
                                   and - 1.0 * line.amount or 0.0,
            }
            move_line_2 = {
                'name': asset_name,
                'account_id': category_id.account_depreciation_expense_id.id,
                'credit': 0.0 if float_compare(amount, 0.0,
                                               precision_digits=prec) > 0
                else -amount,
                'debit': amount if float_compare(amount, 0.0,
                                                 precision_digits=prec) > 0
                else 0.0,
                'journal_id': category_id.journal_id.id,
                'partner_id': partner.id,
                # 'analytic_account_id': category_id.account_analytic_id.id
                # if category_id.type == 'purchase' else False,
                'currency_id': company_currency != current_currency and
                               current_currency.id or company_currency.id,
                'amount_currency': company_currency != current_currency and
                                   line.amount or 0.0,
            }
            line_ids = [(0, 0, {
                'account_id': category_id.account_depreciation_id.id,
                'partner_id': partner.id,
                'credit': amount if float_compare(amount, 0.0,
                                                  precision_digits=prec) > 0
                else 0.0,
            }), (0, 0, {
                'account_id': category_id.account_depreciation_expense_id.id,
                'partner_id': partner.id,
                'debit': amount if float_compare(amount, 0.0,
                                                 precision_digits=prec) > 0
                else 0.0,
            })]
            move = self.env['account.move'].create({
                'ref': line.asset_id.code,
                'date': depreciation_date or False,
                'journal_id': category_id.journal_id.id,
                'line_ids': line_ids,
            })
            for move_line in move.line_ids:
                if move_line.account_id.id == move_line_1['account_id']:
                    move_line.write({'credit': move_line_1['credit'],
                                     'debit': move_line_1['debit']})
                elif move_line.account_id.id == move_line_2['account_id']:
                    move_line.write({'debit': move_line_2['debit'],
                                     'credit': move_line_2['credit']})
            if move.line_ids.filtered(
                    lambda x: x.name == 'Automatic Balancing Line'):
                move.line_ids.filtered(
                    lambda x: x.name == 'Automatic Balancing Line').unlink()
            line.write({'move_id': move.id, 'move_check': True})
            created_moves |= move
        if post_move and created_moves:
            created_moves.filtered(lambda m: any(
                m.asset_depreciation_ids.mapped(
                    'asset_id.category_id.open_asset'))).post()
        return [x.id for x in created_moves]

    def create_grouped_move(self, post_move=True):
        if not self.exists():
            return []
        created_moves = self.env['account.move']
        category_id = self[
            0].asset_id.category_id  # we can suppose that all lines have the
        # same category
        depreciation_date = self.env.context.get(
            'depreciation_date') or fields.Date.context_today(self)
        amount = 0.0
        for line in self:
            # Sum amount of all depreciation lines
            company_currency = line.asset_id.company_id.currency_id
            current_currency = line.asset_id.currency_id
            amount += current_currency.compute(line.amount, company_currency)
        name = category_id.name + _(' (grouped)')
        move_line_1 = {
            'name': name,
            'account_id': category_id.account_depreciation_id.id,
            'debit': 0.0,
            'credit': amount,
            'journal_id': category_id.journal_id.id,
            'analytic_account_id': category_id.account_analytic_id.id
            if category_id.type == 'sale' else False,
        }
        move_line_2 = {
            'name': name,
            'account_id': category_id.account_depreciation_expense_id.id,
            'credit': 0.0,
            'debit': amount,
            'journal_id': category_id.journal_id.id,
            'analytic_account_id': category_id.account_analytic_id.id
            if category_id.type == 'purchase' else False,
        }
        move_vals = {
            'ref': category_id.name,
            'date': depreciation_date or False,
            'journal_id': category_id.journal_id.id,
            'line_ids': [(0, 0, move_line_1), (0, 0, move_line_2)],
        }
        move = self.env['account.move'].create(move_vals)
        self.write({'move_id': move.id, 'move_check': True})
        created_moves |= move
        if post_move and created_moves:
            self.post_lines_and_close_asset()
            created_moves.post()
        return [x.id for x in created_moves]

    def post_lines_and_close_asset(self):
        # we re-evaluate the assets to determine whether we can close them
        # `message_post` invalidates the (whole) cache
        # preprocess the assets and lines in which a message should be posted,
        # and then post in batch will prevent the re-fetch of the same
        # data over and over.
        assets_to_close = self.env['account.asset.asset']
        for line in self:
            asset = line.asset_id
            if asset.currency_id.is_zero(asset.value_residual):
                assets_to_close |= asset
        self.log_message_when_posted()
        assets_to_close.write({'state': 'close'})
        for asset in assets_to_close:
            asset.message_post(body=_("Documento cerrado."))

    def log_message_when_posted(self):
        def _format_message(message_description, tracked_values):
            message = ''
            if message_description:
                message = '<span>%s</span>' % message_description
            for name, values in tracked_values.items():
                message += '<div> &nbsp; &nbsp; &bull; <b>%s</b>: ' % name
                message += '%s</div>' % values
            return message

        # `message_post` invalidates the (whole) cache
        # preprocess the assets in which messages should be posted,
        # and then post in batch will prevent the re-fetch of the same data
        # over and over.
        assets_to_post = {}
        for line in self:
            if line.move_id and line.move_id.state == 'draft':
                partner_name = line.asset_id.partner_id.name
                currency_name = line.asset_id.currency_id.name
                msg_values = {_('Currency'): currency_name,
                              _('Amount'): line.amount}
                if partner_name:
                    msg_values[_('Partner')] = partner_name
                msg = _format_message(_('Depreciation line posted.'),
                                      msg_values)
                assets_to_post.setdefault(line.asset_id, []).append(msg)
        for asset, messages in assets_to_post.items():
            for msg in messages:
                asset.message_post(body=msg)

    def unlink(self):
        for record in self:
            if record.move_check:
                if record.asset_id.category_id.type == 'purchase':
                    msg = _("No se pueden eliminar líneas de depreciación contabilizadas.")
                else:
                    msg = _("No es posible eliminar líneas de cuotas publicadas.")
                raise UserError(msg)
        return super(AccountAssetDepreciationLine, self).unlink()
