from odoo import models, fields, api, SUPERUSER_ID


class ResUser(models.Model):
    _inherit = 'res.users'

    company_group = fields.Selection([
        ('hamburguesas', 'Hamburguesas Mafis SA de CV'),
        ('helados', 'Helados Mafis SA de CV'),
        ('sifam', 'Proyectos Sifam SA de CV'),
        ('hidro', 'Hidrológica Kuale SA de CV'),
        ('tinto5', 'Tintocinco SA de CV'),
        ('g_kuale', 'Gente Kuale SA de CV'),
        ('s_kuale', 'Servicios Kuale SA de CV'),
        ('kuale_srl', 'Kuale S de RL de CV'),
        ('gk_llc', 'Grupo Kuale USA LLC '),
        ('erben', 'Inmobiliaria Erben SA de CV'),
        ('mfda', 'Martha Fernanda Deutsch Azcárraga y Copropietarios'),
        ('ppt', 'Publipuentes Tamaulipas SA de CV'),
        ('c_kuale', 'Comercial Kuale SA de CV'),
        ('productora', 'Productora del Golfo SA de CV'),
        ('vdp', 'Video Producciones del Golfo SA de CV'),
        ('mr_motor', 'Mister Motor SA de CV'),
        ('express', 'Express Offshore de Mexico SA de CV'),
        ('ers', 'Especialistas en Reparto Seguro SA de CV'),
        ('operativos', 'Operativos de Franquicias SA de CV'),
        ('blanco_cafe', 'Blanco y Café SA de CV'),
        ('publirex', 'Publirex Mexicali SA de CV'),
        ('impulsora', 'Impulsora Inmobiliaria Tulum SA de CV'),
        ('rush', 'Industrias Cadillo SAPI de CV'),
        ('otro', 'Otro')
    ], string='Grupo Empresarial')

    see_all_company_groups = fields.Boolean(
        string="Ver todos los productos",
        help="Si está activo, este usuario puede ver productos de todos los grupos empresariales.")

    @api.onchange('company_group', 'see_all_company_groups')
    def _onchange_notify_reload(self):
        if self.env.uid == self.id:
            return {
                'warning': {
                    'title': "Cambios aplicados",
                    'message': "Tu grupo ha cambiado. Es posible que debas actualizar la página para que los cambios surtan efecto.",
                }
            }

    def _switch_company(self, company):
        """Sobrescribe el cambio de empresa activa"""
        print('testing')
        res = super()._switch_company(company)
        for user in self:
            if user.id != SUPERUSER_ID and company.company_group:
                user.sudo().write({'company_group': company.company_group})
        return res