
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.safe_eval import safe_eval



class HrSalaryRule(models.Model):
    """Create new model for Salary Rule"""
    _name = 'hr.salary.rule'
    _order = 'sequence, id'
    _description = 'Salary Rule'

    name = fields.Char(
        required=True,
        string="Nombre de la regla salarial",
        help="Introduce el nombre de la regla salarial",
    )
    code = fields.Char(
        required=True,
        string="Código de la regla salarial",
        help="El código de las reglas salariales puede usarse como referencia "
             "en el cálculo de otras reglas. Es sensible a mayúsculas y minúsculas.",
    )
    sequence = fields.Integer(
        required=True,
        index=True,
        default=5,
        string="Secuencia",
        help='Se utiliza para definir el orden de cálculo de las reglas.',
    )
    quantity = fields.Char(
        default='1.0',
        string='Cantidad',
        help="Se utiliza en el cálculo de porcentajes y montos fijos. "
             "Por ejemplo, una regla para vales de comida con un monto fijo "
             "de 1 € por día trabajado puede tener su cantidad definida "
             "en una expresión como worked_days.WORK100.number_of_days.",
    )
    category_id = fields.Many2one(
        'hr.salary.rule.category',
        string='Categoría',
        help="Selecciona la categoría de la regla salarial.",
        required=True,
    )
    active = fields.Boolean(
        default=True,
        help="Si se desactiva, la regla salarial quedará oculta sin eliminarla.",
    )
    appears_on_payslip = fields.Boolean(
        string='Aparece en la nómina',
        default=True,
        help="Determina si la regla salarial se mostrará en la nómina.",
    )
    parent_rule_id = fields.Many2one(
        'hr.salary.rule',
        string='Regla salarial padre',
        index=True,
        help="Selecciona la regla salarial principal.",
    )
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        help="Selecciona la compañía correspondiente.",
        default=lambda self: self.env['res.company']._company_default_get(),
    )
    condition_select = fields.Selection([
        ('none', 'Siempre verdadera'),
        ('range', 'Rango'),
        ('python', 'Expresión Python')
    ],
        string="Condición basada en",
        default='none',
        required=True,
        help="Selecciona la condición para aplicar la regla salarial.",
    )
    condition_range = fields.Char(
        string='Basada en rango',
        default='contract.wage',
        help='Se utiliza para calcular los valores de porcentaje. '
             'Por lo general, se basa en el salario básico, '
             'pero también puedes usar los códigos de categoría en minúsculas '
             '(por ejemplo: hra, ma, lta, etc.) y la variable "basic".',
    )
    condition_python = fields.Text(
        string='Condición en Python',
        required=True,
        default='''# Variables disponibles:
    #----------------------
    # payslip: objeto que contiene la nómina
    # employee: objeto hr.employee
    # contract: objeto hr.contract
    # rules: objeto con los códigos de reglas previamente calculadas
    # categories: objeto con las categorías de reglas salariales calculadas
    # worked_days: objeto con los días trabajados calculados
    # inputs: objeto con las entradas calculadas

    # Nota: el valor de retorno debe asignarse a la variable 'result'

    result = rules.NET > categories.NET * 0.10''',
        help='Aplica esta regla si la condición es verdadera. '
             'Por ejemplo: basic > 1000.',
    )
    condition_range_min = fields.Float(
        string='Rango mínimo',
        help="Monto mínimo para aplicar esta regla.",
    )
    condition_range_max = fields.Float(
        string='Rango máximo',
        help="Monto máximo para aplicar esta regla.",
    )
    amount_select = fields.Selection([
        ('percentage', 'Porcentaje (%)'),
        ('fix', 'Monto fijo'),
        ('code', 'Código Python'),
    ],
        string='Tipo de monto',
        index=True,
        required=True,
        default='fix',
        help="Método de cálculo del monto de la regla.",
    )
    amount_fix = fields.Float(
        string='Monto fijo',
        digits=(16, 2),
        help="Define un monto fijo para esta regla.",
    )
    amount_percentage = fields.Float(
        string='Porcentaje (%)',
        digits=(16, 2),
        help='Por ejemplo, introduce 50.0 para aplicar un 50 %.',
    )
    amount_python_compute = fields.Text(
        string='Código Python',
        default='''# Variables disponibles:
    #----------------------
    # payslip: objeto que contiene la nómina
    # employee: objeto hr.employee
    # contract: objeto hr.contract
    # rules: objeto con los códigos de reglas previamente calculadas
    # categories: objeto con las categorías de reglas salariales calculadas
    # worked_days: objeto con los días trabajados calculados
    # inputs: objeto con las entradas calculadas

    # Nota: el valor de retorno debe asignarse a la variable 'result'

    result = contract.wage * 0.10''',
    )
    amount_percentage_base = fields.Char(
        string='Porcentaje basado en',
        help='Variable sobre la cual se aplicará el porcentaje.',
    )
    child_ids = fields.One2many(
        'hr.salary.rule',
        'parent_rule_id',
        string='Reglas salariales hijas',
        copy=True,
    )
    register_id = fields.Many2one(
        'hr.contribution.register',
        string='Registro de contribuciones',
        help="Entidad o tercero involucrado en el pago de salarios.",
    )
    input_ids = fields.One2many(
        'hr.rule.input',
        'input_id',
        string='Entradas',
        copy=True,
        help="Selecciona las entradas de regla salarial.",
    )
    note = fields.Text(
        string='Descripción',
        help="Descripción de la regla salarial.",
    )

    @api.constrains('parent_rule_id')
    def _check_parent_rule_id(self):
        """Function to adding constrains for parent_rule_id field"""
        if not self._check_recursion(parent='parent_rule_id'):
            raise ValidationError(
                _('Error! You cannot create recursive hierarchy '
                  'of Salary Rules.'))

    def _recursive_search_of_rules(self):
        """
        @return: returns a list of tuple (id, sequence) which are all the
        children of the passed rule_ids
        """
        children_rules = []
        for rule in self.filtered(lambda rule: rule.child_ids):
            children_rules += rule.child_ids._recursive_search_of_rules()
        return [(rule.id, rule.sequence) for rule in self] + children_rules

    # TODO should add some checks on the type of result (should be float)
    def _compute_rule(self, localdict):
        """
        :param localdict: dictionary containing the environement in which to compute the rule
        :return: returns a tuple build as the base/amount computed, the quantity and the rate
        :rtype: (float, float, float)
        """
        for rec in self:
            rec.ensure_one()
            if rec.amount_select == 'fix':
                try:
                    return rec.amount_fix, float(
                        safe_eval(rec.quantity, localdict)), 100.0
                except:
                    raise UserError(
                        _('Wrong quantity defined for salary rule %s (%s).') % (
                            rec.name, rec.code))
            elif rec.amount_select == 'percentage':
                try:
                    return (
                        float(safe_eval(rec.amount_percentage_base, localdict)),
                        float(safe_eval(rec.quantity, localdict)),
                        rec.amount_percentage)
                except:
                    raise UserError(
                        _('Wrong percentage base or quantity defined '
                          'for salary rule %s (%s).') % (
                            rec.name, rec.code))
            else:
                try:
                    safe_eval(rec.amount_python_compute, localdict, mode='exec',
                              nocopy=True)
                    return (float(localdict['result']),
                            'result_qty' in localdict and
                            localdict['result_qty'] or 1.0, 'result_rate'
                            in localdict and localdict['result_rate'] or 100.0)
                except:
                    raise UserError(
                        _('Wrong python code defined for salary '
                          'rule %s (%s).') % (
                            rec.name, rec.code))

    def _satisfy_condition(self, localdict):
        """
        @param contract_id: id of hr_contract to be tested
        @return: returns True if the given rule match the condition for the
        given contract. Return False otherwise.
        """
        self.ensure_one()
        if self.condition_select == 'none':
            return True
        elif self.condition_select == 'range':
            try:
                result = safe_eval(self.condition_range, localdict)
                return (self.condition_range_min <= result and result <=
                        self.condition_range_max or False)
            except:
                raise UserError(
                    _('Wrong range condition defined for '
                      'salary rule %s (%s).') % (
                        self.name, self.code))
        else:  # python code
            try:
                safe_eval(self.condition_python, localdict, mode='exec',
                          nocopy=True)
                return 'result' in localdict and localdict['result'] or False
            except:
                raise UserError(
                    _('Wrong python condition defined for '
                      'salary rule %s (%s).') % (
                        self.name, self.code))
