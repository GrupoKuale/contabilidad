from odoo import api, fields, models

class AccountGroup(models.Model):
    _inherit = 'account.group'

    sat_nivel = fields.Selection([
        ('1','1.ESTADO DE SITUACIÓN FINANCIERA'),
        ('2','2.ESTADO DE RESULTADOS'),
        ('3','3.ESTADO DE OTROS RESULTADOS INTEGRALES'),
        ('4','4.CUENTAS DE ORDEN'),
        ('5','5.ESTADO DE FLUJOS DE EFECTIVO'),
    ], string='Nivel SAT', required=True, exportable=True)

    code = fields.Char(string = 'Código', exportable=True)
    group_id = fields.Many2one('account.group', string='Grupo', exportable=True)
    accountable = fields.Many2one("hr.employee", string="Responsable", exportable=True)
    tax_ids = fields.Many2many('account.tax', string='Impuestos predeterminados', exportable=True)
    tag_ids = fields.Many2many('account.account.tag', string='Etiquetas', help='Etiquetas opcionales que puede asignar en reportes personalizados', exportable=True)
    allowed_journal_ids = fields.Many2many('account.journal',string='Diarios permitidos', exportable=True)
    currency_id = fields.Many2one('res.currency',string='Divisa de la cuenta', exportable=True)
    deprecated = fields.Boolean(string='Obsoleta',default=False, exportable=True)

    naturaleza = fields.Selection([
        ('D','Deudora'),
        ('A','Acreedora')
    ],string='Naturaleza', exportable=True)

    codigo_sat = fields.Many2many('codigo.agrupador.sat', string='Codigo Agrupador Sat', exportable=True)

    def name_get(self):
        result = []
        for rec in self:
            nam = '%s - %s' % (rec.code, rec.name)
            result.append((rec.id, nam))
        return result

    @api.model
    def _name_search(self, name, args=None, operator='ilike', limit=100, name_get_uid=None, order=None):
        args = args or []
        domain = []
        if name:
            domain = ['|', ('code', operator, name), ('name', operator, name)]
        return self._search(domain + args, limit=limit, access_rights_uid=name_get_uid)

    @api.onchange('code')
    def on_change_code(self):
        self.ensure_one()
        if self.code:
            self.code_prefix_start = self.code

    def _sanitize_writeable_fields(self, vals):
        clean = dict(vals)
        for k in list(clean.keys()):
            if k not in self._fields or self._fields[k].readonly or k in ('id', 'display_name'):
                clean.pop(k, None)
        return clean

    def _map_group_parent_to_company(self, src_parent, company):
        if not src_parent:
            return False
        dest_parent = self.search([
            ('company_id', '=', company.id),
            ('code', '=', src_parent.code),
        ], limit=1)
        if dest_parent:
            return dest_parent

        dest_parent = src_parent.with_context(no_propagate_groups=True).with_company(company).sudo().copy(
            default={'company_id': company.id}
        )
        return dest_parent

    def _prepare_vals_for_company(self, rec, target_company):
        vals = rec.copy_data()[0]
        vals = self._sanitize_writeable_fields(vals)
        vals['company_id'] = target_company.id

        # --- Remapeo de group_id  ---
        if rec.group_id:
            dest_parent = self._map_group_parent_to_company(rec.group_id, target_company)
            vals['group_id'] = dest_parent.id if dest_parent else False

        return vals

    ##### DESCOMENTAR en caso de que si se quieran duplicar las cuentas desde el company ####

    # def create(self,vals):
    #     records = super().create(vals)
    #
    #     if self.env.context.get('no_propagate_groups'):
    #         return records
    #
    #     companies = self.env['res.company'].sudo().search([])
    #     for rec in records:
    #         for company in companies.filtered(lambda c: c.id != rec.company_id.id and not c.is_branch):
    #             exists = self.sudo().search([
    #                 ('code', '=', rec.code),
    #                 ('company_id', '=', company.id)
    #             ], limit=1)
    #             if exists:
    #                 continue
    #
    #             vals_dest = self._prepare_vals_for_company(rec, company)
    #
    #             # Crear en destino sin volver a propagar en cascada
    #             self.with_context(no_propagate_groups=True).with_company(company).sudo().create(vals_dest)
    #
    #     return records

    @api.model
    def copy_groups_to_companies(self,company_id):
        source_company = self.env['res.company'].sudo().browse(company_id)
        if not source_company:
            print('error con source_company')
            return

        source_groups = self.env['account.group'].sudo().search([('company_id', '=', company_id)])
        target_companies = self.env['res.company'].sudo().search([('id', '!=', company_id)])

        for company in target_companies:
            if company.is_branch:
                continue

            for group in source_groups:
                exists = self.search([
                    ('company_id', '=', company.id),
                    ('code', '=', group.code),
                ], limit=1)
                if exists:
                    continue

                vals_dest = self._prepare_vals_for_company(group, company)
                self.with_context(no_propagate_groups=True).with_company(company).sudo().create(vals_dest)




