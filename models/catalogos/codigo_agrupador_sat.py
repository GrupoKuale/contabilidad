from odoo import models, fields,api


class CodigoAgrupadorSat(models.Model):
    _name = 'codigo.agrupador.sat'
    _description = 'Codigo Agrupador Sat para plan de cuentas'
    _rec_name = 'code'

    level = fields.Char(string='Nivel')
    code = fields.Char(string='Código agrupador',required=True, index=True)
    name = fields.Char(string='Nombre de la cuenta')
    ciclo = fields.Char(string='Version de la cuenta',help="identificador del periodo valido de la cuenta")


    @api.depends('name', 'code')
    def _compute_display_name(self):
        for template in self:
            template.display_name = '{}{}'.format('%s - ' % template.code, template.name)