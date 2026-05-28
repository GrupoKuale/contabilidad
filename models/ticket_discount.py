from odoo import fields, models, api
from odoo.exceptions import ValidationError

class TicketDiscount(models.Model):
    _name = 'contabilidad_kuale.ticket_discount'
    _description = 'Discounts for ticket monitor details'

    clave = fields.Integer(string='Clave', required=True, readonly=True, default=0)

    company_ids = fields.Many2many(
        'res.company',
        'ticket_discount_company_rel',
        'discount_id',
        'company_id',
        string='Empresas',
        domain="[('parent_id','=',False)]",)

    branch_ids = fields.Many2many(
        'res.company',
        'ticket_discount_branch_rel',
        'discount_id',
        'branch_id',
        string='Sucursales',
        domain="['|', ('parent_id', 'in', company_ids), ('id', 'in', company_ids)]",)

    alliance = fields.Many2one('contabilidad_kuale.discount_alliance',string='Alianza',required=True)

    name = fields.Char(string='Nombre de tecla', required=True)
    discount_type = fields.Selection([
        ('percentage', 'Porcentaje'),
        ('amount', 'Monto')
    ], string='Tipo de descuento', required=True)

    discount_percentage = fields.Float(string='Porcentaje de descuento')
    discount_amount = fields.Float(string='Monto del descuento')
    department = fields.Many2one('hr.department', string='Departamento')
    details = fields.Html(string='Descripción adicional')
    active = fields.Boolean(string="Activo", default=True)
    usage_ids = fields.One2many(
        'contabilidad_kuale.ticket_discount_usage',
        'discount_id',
        string='Tickets donde se usó'
    )
    image_ids = fields.One2many(
        'contabilidad_kuale.discount_image',
        'discount_id',
        string='Identificadores'
    )
    apply_limitation = fields.Boolean(string='Aplica limitante',default=False)
    limitation = fields.Float(string='Monto maximo', help='Monto maximo de la cuenta a la que se aplica el descuento')
    limitation_amount = fields.Float(string='Monto maximo de la cuenta', compute='compute_limitation_amount')
    use_once_per_day = fields.Boolean(string='Solo una vez por día',
        help='Este descuento no puede aplicarse más de una vez al día por sucursal')

    @api.depends('apply_limitation', 'limitation', 'discount_percentage')
    def compute_limitation_amount(self):
        for rec in self:
            if rec.apply_limitation:
                rec.limitation_amount = (rec.limitation * rec.discount_percentage) / 100
            else:
                rec.limitation_amount = 0

    def name_get(self):
        result = []
        for registro in self:
            nam = '%s - %s' % (registro.clave, registro.name)
            result.append((registro.id, nam))
        return result

    @api.model
    def create(self, vals):
        if not vals.get('clave') or vals.get('clave') == 0:

            last_record = self.env[self._name].sudo().search(
                [], order='clave desc', limit=1)
            if last_record and last_record.clave:
                new_key = last_record.clave + 1
            else:
                new_key = 1001
            vals['clave'] = new_key

        return super(TicketDiscount, self).create(vals)

    @api.constrains('discount_percentage')
    def _check_discount_range(self):
        for record in self:
            if record.discount_type == 'percentage' and not (0 <= record.discount_percentage <= 100):
                raise ValidationError("El descuento debe estar entre 0 y 100% cuando es porcentaje.")


class TicketDiscountUsage(models.Model):
    _name = 'contabilidad_kuale.ticket_discount_usage'
    _description = 'Tickets que usaron el descuento'

    discount_id = fields.Many2one('contabilidad_kuale.ticket_discount', string='Descuento', ondelete='cascade')
    ticket_id = fields.Many2one('contabilidad_kuale.ticket_monitor', string='Ticket', required=True)
    date = fields.Datetime(related='ticket_id.date', string='Fecha', store=True)
    company_id = fields.Many2one(related='ticket_id.company_id', string='Empresa', store=True)
    branch_id = fields.Many2one(related='ticket_id.branch_id', string='Sucursal', store=True)
    discount_authorized = fields.Many2one(related='ticket_id.discount_authorized', string='Autorizado por', store=True)


class DiscountAlliance(models.Model):
    _name = 'contabilidad_kuale.discount_alliance'
    _description = 'Catalogo de alianzas para descuentos.'

    name = fields.Char(string='Nombre de la alianza', required=True)
    active = fields.Boolean(string='Activo', default=True)
    details = fields.Html(string='Descripción')

class DiscountImage(models.Model):
    _name = 'contabilidad_kuale.discount_image'
    _description = 'Imagenes asociadas para referencias en descuentos'

    discount_id = fields.Many2one(
        'contabilidad_kuale.ticket_discount',
        string='Descuento',
        ondelete='cascade',
        required=True
    )

    image = fields.Image(string='Imagen', required=True,max_width=256, max_height=256)
    name = fields.Char(string='Descripción')


