# -*- codigo: utf-8 -*-
import copy
from html.parser import HTMLParser
from odoo import api, models, fields
from datetime import datetime
import logging
from odoo import exceptions
_logger = logging.getLogger(__name__)


class claveprodservcp(models.Model):
    _name = 'cfdi.claveprodservcp'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'Clave_producto'

    Clave_producto = fields.Char(string='Clave producto', required=True)
    Descripcion = fields.Char(string='Descripción', required=True)
    Material_peligroso = fields.Selection(string="¿Es material peligroso?", selection=[('0,1', '0,1'),
                                                                                       ('0', '0'),
                                                                                       ('1', '1')])

    def name_get(self):
        result = []
        for registro in self:
            nam = '%s - %s' % (registro.Clave_producto, registro.Descripcion)
            result.append((registro.id, nam))
        return result

    @api.model
    def _name_search(self, name, args=None, operator='ilike', limit=100, name_get_uid=None, order=None):
        args = args or []
        domain = []
        if name:
            domain = ['|', ('Clave_producto', operator, name), ('Descripcion', operator, name)]
        return self._search(domain + args, limit=limit, access_rights_uid=name_get_uid)
