# -*- codigo: utf-8 -*-
import copy
from html.parser import HTMLParser
from odoo import api, models, fields
from datetime import datetime
import logging
from odoo import exceptions
_logger = logging.getLogger(__name__)


class clavecolonia(models.Model):
    _name = 'cfdi.clavecolonia'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'Codigo_postal'

    Clave_colonia = fields.Char(string='Clave colonia', required=True)
    Codigo_postal = fields.Char(string='Codigo postal', required=True)
    Nombre = fields.Char(string='Nombre del asentamiento', required=True)

    def name_get(self):
        result = []
        for registro in self:
            nam = '%s - %s' % (registro.Codigo_postal, registro.Nombre)
            result.append((registro.id, nam))
        return result

    @api.model
    def _name_search(self, name, args=None, operator='ilike', limit=100, name_get_uid=None, order=None):
        args = args or []
        domain = []
        if name:
            domain = ['|', ('Codigo_postal', operator, name), ('Nombre', operator, name)]
        return self._search(domain + args, limit=limit, access_rights_uid=name_get_uid)
