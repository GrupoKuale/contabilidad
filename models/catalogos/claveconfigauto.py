# -*- codigo: utf-8 -*-
import copy
from html.parser import HTMLParser
from odoo import api, models, fields
from datetime import datetime
import logging
from odoo import exceptions
_logger = logging.getLogger(__name__)


class claveconfigauto(models.Model):
    _name = 'cfdi.claveconfigauto'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'Descripcion'

    Clave_configauto = fields.Char(string='Clave configuracion autotransporte', required=True)
    Descripcion = fields.Char(string='Descripción', required=True)
    Numero_ejes = fields.Char(string='Número de ejes')
    Numero_llantas = fields.Char(string='Número de llantas')
    Remolque = fields.Selection(string='Remolque', selection=[('0', '0'),
                                                              ('1', '1'),
                                                              ('2', '0,1')])
