# -*- codigo: utf-8 -*-
import copy
from html.parser import HTMLParser
from odoo import api, models, fields
from datetime import datetime
import logging
from odoo import exceptions
_logger = logging.getLogger(__name__)


class claveformadepago(models.Model):
    _name = 'cfdi.claveformadepago'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'Descripcion'

    Clave_forma_de_pago = fields.Char(string='Clave forma de pago', required=True)
    third_party_id = fields.Char(string='ID campo de terceros',
                                 help='Campo de identificacion del metodo de pago en base al sistema de pixel',
                                 required=True)
    Descripcion = fields.Char(string='Descripción', required=True)


    @api.depends('Clave_forma_de_pago', 'Descripcion')
    def _compute_display_name(self):
        for registro in self:
            if registro.Clave_forma_de_pago and registro.Descripcion:
                registro.display_name = '{} - {}'.format(
                    registro.Clave_forma_de_pago,
                    registro.Descripcion
                )
            else:
                registro.display_name = registro.Clave_forma_de_pago or f"{registro._name},{registro.id}"

