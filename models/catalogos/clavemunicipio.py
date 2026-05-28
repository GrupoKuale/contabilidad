# -*- codigo: utf-8 -*-
import copy
from html.parser import HTMLParser
from odoo import api, models, fields
from datetime import datetime
import logging
from odoo import exceptions
_logger = logging.getLogger(__name__)


class clavemunicipio(models.Model):
    _name = 'cfdi.clavemunicipio'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'Descripcion'

    Clave_municipio = fields.Char(string='Clave municipio', required=True)
    Clave_estado = fields.Char(string='Clave estado', required=True)
    Descripcion = fields.Char(string='Descripción', required=True)

    def name_get(self):
        result = []
        for registro in self:
            nam = '%s - %s' % (registro.Descripcion, registro.Clave_estado)
            result.append((registro.id, nam))
        return result
    
    @api.model
    def _name_search(self, name, args=None, operator='ilike', limit=100, name_get_uid=None, order=None):
        args = args or []
        domain = []
        if name:
            domain = ['|', ('Descripcion', operator, name), ('Clave_estado', operator, name)]
        return self._search(domain + args, limit=limit, access_rights_uid=name_get_uid)
