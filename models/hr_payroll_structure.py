
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class HrPayrollStructure(models.Model):
    _name = 'hr.payroll.structure'
    _description = 'Salary Structure'

    @api.model
    def _get_parent(self):
        """Function for return parent."""
        return self.env.ref('hr_payroll_community.structure_base', False)

    name = fields.Char(required=True, string="Nombre",
                       help="Nombre para estructura salarial")
    code = fields.Char(string='Referencia', required=True,
                       help="Código para la Estructura de Nómina")
    company_id = fields.Many2one(
        comodel_name='res.company', string='Compañia', required=True,
        help="Empresa para la estructura de nómina", copy=False,
        default=lambda self: self.env['res.company']._company_default_get())
    note = fields.Text(string='Descripcion',
                       help="Descripcion para la estructura de nomina")
    parent_id = fields.Many2one('hr.payroll.structure',
                                string='Estructura padre',
                                default=_get_parent,
                                help="Estructura de nomina superior o principal")
    children_ids = fields.One2many('hr.payroll.structure',
                                   'parent_id',
                                   string='Estructuras hijas', copy=True,
                                   help="Estructuras de nómina dependientes")
    rule_ids = fields.Many2many('hr.salary.rule',
                                'hr_structure_salary_rule_rel',
                                'struct_id',
                                'rule_id', string='Reglas salariales',
                                help="Seleccion de reglas salariales asociadas")

    @api.constrains('parent_id')
    def _check_parent_id(self):
        """Function for check parent in Payroll Structure"""
        if not self._check_recursion():
            raise ValidationError(
                _('You cannot create a recursive salary structure.'))

    @api.returns('self', lambda value: value.id)
    def copy(self, default=None):
        """Function for return Payroll Structure"""
        self.ensure_one()
        default = dict(default or {}, code=_("%s (copy)") % (self.code))
        return super(HrPayrollStructure, self).copy(default)

    def get_all_rules(self):
        """
        @return: returns a list of tuple (id, sequence) of rules that are maybe
        to apply
        """
        all_rules = []
        for struct in self:
            all_rules += struct.rule_ids._recursive_search_of_rules()
        return all_rules

    def _get_parent_structure(self):
        """Function for getting Parent Structure"""
        parent = self.mapped('parent_id')
        if parent:
            parent = parent._get_parent_structure()
        return parent + self
