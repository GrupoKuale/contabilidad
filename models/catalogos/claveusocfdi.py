# -*- codigo: utf-8 -*-
import copy
from html.parser import HTMLParser
from odoo import api, models, fields
from datetime import datetime
import logging
from odoo import exceptions
_logger = logging.getLogger(__name__)


class claveusocfdi(models.Model):
    _name = 'cfdi.claveusocfdi'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'Clave_UsoCFDI'

    Clave_UsoCFDI = fields.Char(string='Clave uso CFDI', required=True)
    Descripcion = fields.Char(string='Descripción')
    Fisica = fields.Boolean(string='Fisica')
    Moral = fields.Boolean(string='Moral')
    Regimen_fiscal_receptor = fields.Char(string='Regimen fiscal receptor')

    @api.depends('Clave_UsoCFDI', 'Descripcion')
    def _compute_display_name(self):
        for registro in self:
            if registro.Clave_UsoCFDI and registro.Descripcion:
                registro.display_name = '{} - {}'.format(
                    registro.Clave_UsoCFDI,
                    registro.Descripcion
                )
            else:
                registro.display_name = registro.Clave_UsoCFDI or f"{registro._name},{registro.id}"

    @api.model
    def _name_search(self, name, args=None, operator='ilike', limit=100, name_get_uid=None, order=None):
        args = args or []
        domain = []
        if name:
            domain = ['|', ('Clave_UsoCFDI', operator, name), ('Descripcion', operator, name)]
        return self._search(domain + args, limit=limit, access_rights_uid=name_get_uid)

