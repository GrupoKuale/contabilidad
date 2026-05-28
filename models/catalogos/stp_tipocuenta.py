from odoo import models, fields

class StpCatalogTipoCuenta(models.Model):
    _name = 'stp.tipo.cuenta'
    _description = 'Catálogo Tipo Cuenta STP'
    _rec_name = 'descripcion'

    clave = fields.Char(required=True, help="Clave STP (Ej: 40)")
    descripcion = fields.Char(required=True)
    activa = fields.Boolean(default=True)
