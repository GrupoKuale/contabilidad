# -*- codigo: utf-8 -*-
import copy
from html.parser import HTMLParser
from odoo import api, models, fields
from datetime import datetime
import logging
from odoo import exceptions
_logger = logging.getLogger(__name__)


class clavesubtiporemo(models.Model):
    _name = 'cfdi.clavesubtiporemo'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'Clave_subtiporemo'

    Clave_subtiporemo = fields.Char(string='Clave tipo remolque', required=True)
    Nombre_remolque = fields.Char(string='Remolque o semiremolque', required=True)

    def name_get(self):
        result = []
        for registro in self:
            nam = '%s - %s' % (registro.Clave_subtiporemo, registro.Nombre_remolque)
            result.append((registro.id, nam))
        return result

    @api.model
    def _name_search(self, name, args=None, operator='ilike', limit=100, name_get_uid=None, order=None):
        args = args or []
        domain = []
        if name:
            domain = ['|', ('Clave_subtiporemo', operator, name), ('Nombre_remolque', operator, name)]
        return self._search(domain + args, limit=limit, access_rights_uid=name_get_uid)
