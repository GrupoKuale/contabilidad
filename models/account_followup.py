
from odoo import fields, models


class Followup(models.Model):
    _name = 'account.followup'
    _description = 'Account Follow-up'
    _rec_name = 'name'

    followup_line_ids = fields.One2many('followup.line',
                                        'followup_id',
                                        'Seguimiento', copy=True)
    company_id = fields.Many2one('res.company', 'Compañía',
                                 default=lambda self: self.env.company)
    name = fields.Char(related='company_id.name', readonly=True)


class FollowupLine(models.Model):
    _name = 'followup.line'
    _description = 'Follow-up Criteria'
    _order = 'delay'

    name = fields.Char('Acción de seguimiento', required=True, translate=True)
    sequence = fields.Integer(
        help="Da el orden de secuencia al mostrar una lista de líneas de seguimiento.")
    delay = fields.Integer('Días de vencimiento', required=True,
                           help="El número de días que deben transcurrir desde la fecha de vencimiento de la factura "
"para enviar el recordatorio. "
"Puede ser negativo si desea enviar una "
"alerta cortés con anticipación")
    followup_id = fields.Many2one('account.followup',
                                  'Seguimientos',
                                  ondelete="cascade")
