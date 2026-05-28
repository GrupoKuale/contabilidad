# -*- codigo: utf-8 -*-
import copy
from html.parser import HTMLParser
from odoo import api, models, fields
from datetime import datetime
import logging
from odoo import exceptions
_logger = logging.getLogger(__name__)


class claveregimenfiscal(models.Model):
    _name = 'cfdi.claveregimenfiscal'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'Clave_regimenFiscal'

    Clave_regimenFiscal = fields.Char(string='Clave regimen fiscal', required=True)
    Descripcion = fields.Char(string='Descripción')
    Fisica = fields.Boolean(string='Fisica')
    Moral = fields.Boolean(string='Moral')

    @api.depends('Clave_regimenFiscal', 'Descripcion')
    def _compute_display_name(self):
        for registro in self:
            if registro.Clave_regimenFiscal and registro.Descripcion:
                registro.display_name = '{} - {}'.format(
                    registro.Clave_regimenFiscal,
                    registro.Descripcion
                )
            else:
                registro.display_name = registro.Clave_regimenFiscal or f"{registro._name},{registro.id}"


    @api.model
    def _name_search(self, name, args=None, operator='ilike', limit=100, name_get_uid=None, order=None):
        args = args or []
        domain = []
        if name:
            domain = ['|', ('Clave_regimenFiscal', operator, name), ('Descripcion', operator, name)]
        return self._search(domain + args, limit=limit, access_rights_uid=name_get_uid)

