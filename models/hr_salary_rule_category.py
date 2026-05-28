
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class HrSalaryRuleCategory(models.Model):
    """Create new model for Salary Rule Category"""
    _name = 'hr.salary.rule.category'
    _description = 'Salary Rule Category'

    name = fields.Char(
        required=True,string="Nombre",help="Nombre de la categoría de regla salarial")
    code = fields.Char(required=True,string="Código",help="Código de la categoría de regla salarial")
    parent_id = fields.Many2one('hr.salary.rule.category',string='Categoría padre',
        help="Vincular una categoría salarial con su categoría padre se utiliza únicamente con fines de reporte.")
    children_ids = fields.One2many('hr.salary.rule.category','parent_id',
        string='Categorías hijas',help="Seleccione las categorías de reglas salariales hijas.")
    note = fields.Text(string='Descripción',help="Descripción de la categoría salarial.")
    company_id = fields.Many2one('res.company',string='Compañía',
        help="Seleccione la compañía.",default=lambda self: self.env['res.company']._company_default_get())

    @api.constrains('parent_id')
    def _check_parent_id(self):
        """Function to add constrains for parent_id field"""
        if not self._check_recursion():
            raise ValidationError(
                _('Error! You cannot create recursive '
                  'hierarchy of Salary Rule Category.'))
