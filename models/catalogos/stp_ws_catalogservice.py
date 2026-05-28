from odoo import models, fields

class StpCatalogService(models.Model):
    _name = 'stp.ws.type.catalog'
    _description = 'Catálogo Tipo de Servicio para Pago Referenciados'
    _rec_name = 'type'

    id_catalog = fields.Char(required=True, help="id")
    type = fields.Char(string="Tipo de Servicio",required=True)
    activa = fields.Boolean(default=True)
