# -*- codigo: utf-8 -*-
import copy
from html.parser import HTMLParser
from odoo import api, models, fields
from datetime import datetime
import logging
from odoo import exceptions
_logger = logging.getLogger(__name__)


class claveimpuesto(models.Model):
    _name = 'cfdi.claveimpuesto'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'Clave_impuesto'

    Clave_impuesto = fields.Char(string='Clave impuesto', required=True)
    Descripcion = fields.Char(string='Descripción')
    Retencion = fields.Boolean(string='Retención')
    Traslado = fields.Boolean(string='Traslado')
    Local_Federal = fields.Char(string='Local o federal')

    def name_get(self):
        result = []
        for registro in self:
            nam = '%s - %s' % (registro.Clave_impuesto, registro.Descripcion)
            result.append((registro.id, nam))
        return result

    @api.model
    def _name_search(self, name, args=None, operator='ilike', limit=100, name_get_uid=None, order=None):
        args = args or []
        domain = []
        if name:
            domain = ['|', ('Clave_impuesto', operator, name), ('Descripcion', operator, name)]
        return self._search(domain + args, limit=limit, access_rights_uid=name_get_uid)

