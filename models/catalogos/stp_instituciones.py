from odoo import models, fields

class StpCatalogInstitucion(models.Model):
    _name = 'stp.institucion'
    _description = 'Catálogo Instituciones STP'
    _rec_name = 'participante'

    clave = fields.Char(required=True)
    participante = fields.Char(required=True)
    activa = fields.Boolean(default=True)