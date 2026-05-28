from odoo import models, fields

class StpEmpresa(models.Model):
    _name = 'stp.empresa'
    _description = 'Catálogo Empresas STP'
    _rec_name = 'nombre'

    nombre = fields.Char(required=True)
    activa = fields.Boolean(default=True)